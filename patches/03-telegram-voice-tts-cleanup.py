#!/usr/bin/env python3
"""
Telegram voice TTS cleanup — patch gateway/platforms/base.py so voice-input
responses send clean Telegram voice replies without quoting the user's original
voice message, and keep long spoken replies short/punchy.

Usage: python3 03-telegram-voice-tts-cleanup.py <hermes_src_dir>
"""
import os
import sys


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/hermes-agent"
    filepath = os.path.join(src_dir, "gateway", "platforms", "base.py")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    patches_applied = 0

    # Patch 1: make prepare_tts_text always generate a compact spoken summary.
    new_prepare = '''\
    def prepare_tts_text(self, text: str) -> str:
        """Prepare text for TTS.

        Strip markdown/control syntax and always produce a compact spoken
        version. The full response still lands in chat; voice should be a short
        summary: normally 1-2 sentences, hard-capped at 4 short sentences.
        """
        cleaned = re.sub(r'```[\s\S]*?```', ' ', text)
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
        cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cleaned)
        cleaned = re.sub(r'https?://\S+', '', cleaned)
        cleaned = re.sub(r'[*_#>\[\]()]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            return cleaned

        # Always keep the spoken version compact. Prefer complete sentences.
        # Use 1-2 sentences normally; allow up to 4 only when the first few are
        # very short. This is intentionally extractive and deterministic: the
        # text response is the source of truth, TTS is just the quick version.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if s.strip()]
        summary_parts = []
        total = 0
        for sentence in sentences:
            if total + len(sentence) > 520:
                break
            summary_parts.append(sentence)
            total += len(sentence) + 1
            if len(summary_parts) >= 2 and total >= 180:
                break
            if len(summary_parts) >= 4:
                break
        summary = ' '.join(summary_parts).strip()
        if not summary:
            summary = cleaned[:520].rsplit(' ', 1)[0].strip()
        return ("Quick version: " + summary).strip()
'''

    if new_prepare in content:
        print("  [1] prepare_tts_text already patched")
        patches_applied += 1
    else:
        fn_start = content.find("    def prepare_tts_text(self, text: str) -> str:\n")
        fn_end = content.find("\n\n    async def play_tts", fn_start if fn_start >= 0 else 0)
        if fn_start >= 0 and fn_end >= 0:
            content = content[:fn_start] + new_prepare + content[fn_end:]
            print("  [1] prepare_tts_text patched ✓")
            patches_applied += 1
        else:
            print("  [1] prepare_tts_text function boundary not found — skipping")

    # Patch 2: for voice-input auto-TTS, do not pass Telegram reply metadata
    # that renders as a quoted "voice message" header above the returned voice.
    old_play = '''\
                        tts_result = await self.play_tts(
                            chat_id=event.source.chat_id,
                            audio_path=_tts_path,
                            caption=telegram_tts_caption,
                            metadata=_thread_metadata,
                        )
'''

    new_play = '''\
                        _tts_metadata = _thread_metadata
                        if self.platform == Platform.TELEGRAM and _tts_metadata is not None:
                            _tts_metadata = dict(_tts_metadata)
                            _tts_metadata.pop("telegram_reply_to_message_id", None)
                            _tts_metadata.pop("telegram_dm_topic_reply_fallback", None)
                            _tts_metadata["notify"] = True
                        tts_result = await self.play_tts(
                            chat_id=event.source.chat_id,
                            audio_path=_tts_path,
                            caption=telegram_tts_caption,
                            metadata=_tts_metadata,
                        )
'''

    if new_play in content:
        print("  [2] TTS metadata cleanup already patched")
        patches_applied += 1
    elif old_play in content:
        content = content.replace(old_play, new_play, 1)
        print("  [2] TTS metadata cleanup patched ✓")
        patches_applied += 1
    else:
        print("  [2] TTS metadata cleanup anchor not found — skipping")

    if patches_applied == 0:
        print("  No patches applied — all anchors missing. Source may have changed.")
        sys.exit(1)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  Wrote {len(content)} bytes to {filepath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
