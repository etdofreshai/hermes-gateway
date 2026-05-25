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

    # Patch 1: make prepare_tts_text summarize/truncate long responses for voice.
    old_prepare = '''\
    def prepare_tts_text(self, text: str) -> str:
        """Prepare text for TTS. Override to filter tool output, code, etc.

        Default strips markdown formatting and truncates to 4000 chars.
        """
        return re.sub(r'[*_`#\\[\\]()]', '', text)[:4000].strip()
'''

    new_prepare = '''\
    def prepare_tts_text(self, text: str) -> str:
        """Prepare text for TTS.

        Strip markdown/control syntax. Short answers are spoken directly. Long
        answers get a short, punchy spoken version while the full text still
        lands in chat.
        """
        cleaned = re.sub(r'```[\\s\\S]*?```', ' ', text)
        cleaned = re.sub(r'`([^`]+)`', r'\\1', cleaned)
        cleaned = re.sub(r'\\[([^\\]]+)\\]\\([^)]+\\)', r'\\1', cleaned)
        cleaned = re.sub(r'https?://\\S+', '', cleaned)
        cleaned = re.sub(r'[*_#>\\[\\]()]', '', cleaned)
        cleaned = re.sub(r'\\s+', ' ', cleaned).strip()
        if len(cleaned) <= 650:
            return cleaned

        # Keep the spoken version short. Prefer complete early sentences;
        # otherwise fall back to a clean character boundary.
        sentences = re.split(r'(?<=[.!?])\\s+', cleaned)
        summary_parts = []
        total = 0
        for sentence in sentences:
            if not sentence:
                continue
            if total + len(sentence) > 420:
                break
            summary_parts.append(sentence)
            total += len(sentence) + 1
            if len(summary_parts) >= 2:
                break
        summary = ' '.join(summary_parts).strip()
        if not summary:
            summary = cleaned[:420].rsplit(' ', 1)[0].strip()
        return ("Quick version: " + summary).strip()
'''

    if new_prepare in content:
        print("  [1] prepare_tts_text already patched")
        patches_applied += 1
    elif old_prepare in content:
        content = content.replace(old_prepare, new_prepare, 1)
        print("  [1] prepare_tts_text patched ✓")
        patches_applied += 1
    else:
        print("  [1] prepare_tts_text anchor not found — skipping")

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
