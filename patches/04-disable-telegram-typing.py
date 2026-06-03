#!/usr/bin/env python3
"""Disable Telegram typing indicators in the installed Hermes source.

Telegram Desktop can show stale "Hermes Agent is typing" across multiple groups
when Hermes has long-running/queued sessions. Bot API typing actions expire once
we stop sending them, so no-op TelegramAdapter.send_typing while preserving normal
message delivery.
"""
from __future__ import annotations

from pathlib import Path

path = Path('/usr/local/lib/hermes-agent/gateway/platforms/telegram.py')
text = path.read_text()
old = '''    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Send typing indicator."""
        if self._bot:
            _is_dm_topic: bool = False
            message_thread_id: Optional[int] = None
            try:
                _typing_thread = self._metadata_thread_id(metadata)
                _is_dm_topic = bool(metadata and metadata.get("telegram_dm_topic_reply_fallback"))
                message_thread_id = self._message_thread_id_for_typing(_typing_thread)
                await self._bot.send_chat_action(
                    chat_id=int(chat_id),
                    action="typing",
                    message_thread_id=message_thread_id,
                )
            except Exception as e:
                # For DM topic lanes, Telegram may reject message_thread_id.
                # Fall back to sending typing without thread_id so the typing
                # indicator at least appears in the main DM view.
                if _is_dm_topic and message_thread_id is not None:
                    try:
                        await self._bot.send_chat_action(
                            chat_id=int(chat_id),
                            action="typing",
                        )
                        return
                    except Exception:
                        pass
                # Typing failures are non-fatal; log at debug level only.
                logger.debug(
                    "[%s] Failed to send Telegram typing indicator: %s",
                    self.name,
                    e,
                    exc_info=True,
                )
'''
new = '''    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Send typing indicator.

        Disabled locally: Telegram Desktop can show stale "Hermes Agent is typing"
        across groups for very long-running/queued Hermes sessions. Telegram chat
        actions expire quickly once the bot stops sending them, so no-op here keeps
        the UI quiet while preserving normal message delivery.
        """
        return None
'''
if new in text:
    print('Telegram typing already disabled')
elif old in text:
    path.write_text(text.replace(old, new, 1))
    print('Disabled Telegram typing indicators')
else:
    raise SystemExit('target send_typing block not found')
