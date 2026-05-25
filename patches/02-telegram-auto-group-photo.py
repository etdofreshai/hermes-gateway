#!/usr/bin/env python3
"""
Telegram auto group photo — patch gateway/platforms/telegram.py so when Hermes is
added to a group (or a new group is created with Hermes already included), it
automatically starts a background agent task with the telegram-group-icon skill.

Usage: python3 02-telegram-auto-group-photo.py <hermes_src_dir>
"""
import os
import sys


def _replace_once(content: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in content:
        print(f"  [{label}] already patched")
        return content, True
    if old in content:
        print(f"  [{label}] patched ✓")
        return content.replace(old, new, 1), True
    print(f"  [{label}] anchor not found — skipping")
    return content, False


def main() -> int:
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/hermes-agent"
    filepath = os.path.join(src_dir, "gateway", "platforms", "telegram.py")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    applied = 0

    # Patch 1: register a status-update handler for new_chat_members / chat-created messages.
    register_old = """\
            self._app.add_handler(TelegramMessageHandler(
                filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.Sticker.ALL,
                self._handle_media_message
            ))
            # Handle inline keyboard button callbacks (update prompts)\
"""
    register_new = """\
            self._app.add_handler(TelegramMessageHandler(
                filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.Sticker.ALL,
                self._handle_media_message
            ))
            # Auto group photo workflow: service/status updates are not text/media.
            try:
                _status_filter = getattr(getattr(filters, "StatusUpdate", None), "ALL", None)
                if _status_filter is not None:
                    self._app.add_handler(TelegramMessageHandler(
                        _status_filter,
                        self._handle_group_photo_status_update
                    ))
            except Exception as _status_handler_err:
                logger.debug("[%s] Failed to register Telegram status update handler: %s", self.name, _status_handler_err)
            # Handle inline keyboard button callbacks (update prompts)\
"""
    content, ok = _replace_once(content, register_old, register_new, "1 register status handler")
    applied += int(ok)

    # Patch 2: add helper methods before _handle_text_message.
    methods_old = """\
    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
"""
    methods_insert = r'''
    async def _handle_group_photo_status_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Trigger automatic Telegram group-photo generation on bot join/group create."""
        msg = getattr(update, "message", None)
        if not msg or not getattr(msg, "chat", None):
            return
        if not self.config.extra.get("suggest_group_photo_on_join", True):
            return
        chat = msg.chat
        chat_type = str(getattr(chat, "type", "")).split(".")[-1].lower()
        if chat_type not in {"group", "supergroup"}:
            return

        bot_id = getattr(self._bot, "id", None)
        new_members = getattr(msg, "new_chat_members", None) or []
        bot_added = any(getattr(member, "id", None) == bot_id for member in new_members)
        chat_created = bool(
            getattr(msg, "group_chat_created", False)
            or getattr(msg, "supergroup_chat_created", False)
        )
        if not (bot_added or chat_created):
            return

        title = getattr(chat, "title", None) or str(getattr(chat, "id", "this group"))
        logger.info("[Telegram] Group photo workflow triggered for %s (%s)", title, getattr(chat, "id", ""))
        asyncio.create_task(self._run_group_photo_workflow(msg, update_id=getattr(update, "update_id", None)))

    async def _run_group_photo_workflow(self, msg: Message, update_id: Optional[int] = None) -> None:
        """Run the group icon workflow as a background bot-authored agent message."""
        try:
            grace = self.config.extra.get("group_photo_admin_grace_seconds", 30)
            try:
                grace = max(0, min(int(grace), 120))
            except Exception:
                grace = 30
            if grace:
                await asyncio.sleep(grace)

            chat = msg.chat
            title = getattr(chat, "title", None) or str(getattr(chat, "id", "this group"))
            event = self._build_message_event(msg, MessageType.TEXT, update_id=update_id)
            # Preserve the original human actor from Telegram's service message.
            # Overwriting source.user_id with the bot id makes gateway auth reject
            # the synthetic workflow unless the bot itself is allowlisted.
            event.auto_skill = "telegram-group-icon"
            event.text = (
                f"A Telegram group named {title!r} was just created or Hermes was just added.\n\n"
                "Use the telegram-group-icon workflow to generate one square modern no-border group icon based on the group name. "
                "If config/admin permissions allow, set it as the Telegram group photo; otherwise send it as a suggested group photo and explain that Hermes needs admin permission with Change group info. "
                "Keep the final message short. Do not ask the user for confirmation for this automatic join workflow."
            )
            await self.handle_message(event)
        except Exception as exc:
            logger.warning("[Telegram] Group photo workflow failed: %s", exc, exc_info=True)

'''
    methods_new = methods_insert + methods_old
    content, ok = _replace_once(content, methods_old, methods_new, "2 group photo methods")
    applied += int(ok)

    if applied == 0:
        print("  No patches applied — source may have changed.")
        return 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Wrote {len(content)} bytes to {filepath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
