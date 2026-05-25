#!/usr/bin/env python3
"""
Telegram voice transcript echo — patch gateway/run.py to send an immediate
🎤 transcript bubble to Telegram before the agent processes the voice message.

Usage: python3 01-telegram-voice-echo.py <hermes_src_dir>
"""
import sys, os

def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/hermes-agent"
    filepath = os.path.join(src_dir, "gateway", "run.py")

    with open(filepath, "r") as f:
        content = f.read()

    patches_applied = 0

    # --- Patch 1: Call site — pass source and event to _enrich_message_with_transcription ---
    call_site_old = """\
            if audio_paths:
                message_text = await self._enrich_message_with_transcription(
                    message_text,
                    audio_paths,
                )\
"""

    call_site_new = """\
            if audio_paths:
                message_text = await self._enrich_message_with_transcription(
                    message_text,
                    audio_paths,
                    source=source,
                    event=event,
                )\
"""

    if call_site_new in content:
        print(f"  [1] Call site already patched")
        patches_applied += 1
    elif call_site_old in content:
        content = content.replace(call_site_old, call_site_new, 1)
        print(f"  [1] Call site patched ✓")
        patches_applied += 1
    else:
        print(f"  [1] Call site anchor not found — skipping")

    # --- Patch 2: Function signature — add keyword-only source/event params ---
    sig_old = """\
    async def _enrich_message_with_transcription(
        self,
        user_text: str,
        audio_paths: List[str],
    ) -> str:
        \"\"\"
        Auto-transcribe user voice/audio messages using the configured STT provider
        and prepend the transcript to the message text.

        Args:
            user_text:   The user's original caption / message text.
            audio_paths: List of local file paths to cached audio files.

        Returns:
            The enriched message string with transcriptions prepended.
        \"\"\"\
"""

    sig_new = """\
    async def _enrich_message_with_transcription(
        self,
        user_text: str,
        audio_paths: List[str],
        *,
        source: Optional[Any] = None,
        event: Optional[Any] = None,
    ) -> str:
        \"\"\"
        Auto-transcribe user voice/audio messages using the configured STT provider
        and prepend the transcript to the message text.

        Args:
            user_text:   The user's original caption / message text.
            audio_paths: List of local file paths to cached audio files.
            source:      Optional SessionSource — if Telegram, sends immediate mic-emoji echo.
            event:       Optional MessageEvent — for Telegram reply-thread metadata.

        Returns:
            The enriched message string with transcriptions prepended.
        \"\"\"\
"""

    if sig_new in content:
        print(f"  [2] Function signature already patched")
        patches_applied += 1
    elif sig_old in content:
        content = content.replace(sig_old, sig_new, 1)
        print(f"  [2] Function signature patched ✓")
        patches_applied += 1
    else:
        print(f"  [2] Function signature anchor not found — skipping")

    # --- Patch 3: After successful transcription — send 🎤 echo for Telegram ---
    echo_old = """\
                if result["success"]:
                    transcript = result["transcript"]
                    enriched_parts.append(
                        f'[The user sent a voice message~ '
                        f'Here\\'s what they said: "{transcript}"]'
                    )
                else:\
"""

    echo_new = """\
                if result["success"]:
                    transcript = result["transcript"]
                    enriched_parts.append(
                        f'[The user sent a voice message~ '
                        f'Here\\'s what they said: "{transcript}"]'
                    )
                    # Telegram voice UX: send immediate transcript echo
                    if source is not None and event is not None:
                        try:
                            from gateway.session import Platform as _Platform
                            if getattr(source, 'platform', None) == _Platform.TELEGRAM:
                                _echo_adapter = self.adapters.get(source.platform)
                                _echo_meta = self._thread_metadata_for_source(
                                    source, self._reply_anchor_for_event(event)
                                )
                                if _echo_adapter:
                                    await _echo_adapter.send(
                                        source.chat_id,
                                        "\\xf0\\x9f\\x8e\\xa4 " + transcript,
                                        metadata=_echo_meta,
                                    )
                        except Exception as _echo_err:
                            logger.debug("Failed to send Telegram transcript echo: %s", _echo_err)
                else:\
"""

    if echo_new in content:
        print(f"  [3] Echo logic already patched")
        patches_applied += 1
    elif echo_old in content:
        content = content.replace(echo_old, echo_new, 1)
        print(f"  [3] Echo logic patched ✓")
        patches_applied += 1
    else:
        print(f"  [3] Echo logic anchor not found — skipping")

    if patches_applied == 0:
        print(f"  No patches applied — all anchors missing. Source may have changed.")
        sys.exit(1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"  Wrote {len(content)} bytes to {filepath}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
