"""Owner-only browsing of source-owned queues; no access to execution controls."""

import asyncio
import json
import uuid
from urllib.parse import urlsplit

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message


def button(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


class ReviewUI:
    def __init__(self, app):
        self.app = app
        self.lock = asyncio.Lock()
        self.app.store.db.execute("""CREATE TABLE IF NOT EXISTS review_views(
            token TEXT PRIMARY KEY,source TEXT NOT NULL,mode TEXT NOT NULL,
            offset INTEGER NOT NULL,item TEXT NOT NULL,message_id INTEGER UNIQUE NOT NULL,parent TEXT NOT NULL DEFAULT 'home')""")
        self.app.store.db.commit()

    @property
    def sources(self):
        return {source.name: source for source in self.app.settings.sources if source.queue}

    def menu(self):
        source = next(iter(self.sources))
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [button("Vibecoding", "vibecoding")],
                [button("Housing", f"browse:{source}:queue")],
            ]
        )

    async def summary(self, source, text):
        async with self.app.send_lock:
            return await self.app.bot.send_message(
                self.app.settings.allowed_user_id,
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[button("View queue", f"browse:{source}:queue")]]
                ),
            )

    async def home(self, message=None):
        sent = await self.display(
            "Personal Notifier · Home deck\n\nChoose an operation.", None, self.menu(), message
        )
        if message:
            with self.app.store.db:
                self.app.store.db.execute(
                    "DELETE FROM review_views WHERE message_id=?", (message.message_id,)
                )
        return sent

    async def display(self, html, photo, markup, message=None):
        bot = self.app.bot
        owner = self.app.settings.allowed_user_id
        async with self.app.send_lock:
            if photo:
                try:
                    if message:
                        return await bot.edit_message_media(
                            chat_id=owner,
                            message_id=message.message_id,
                            media=InputMediaPhoto(
                                media=photo, caption=html, parse_mode="HTML", show_caption_above_media=True
                            ),
                            reply_markup=markup,
                        )
                    return await bot.send_photo(
                        owner,
                        photo,
                        caption=html,
                        parse_mode="HTML",
                        show_caption_above_media=True,
                        reply_markup=markup,
                    )
                except TelegramBadRequest:
                    # Explicit rejection did not send the requested media.
                    pass
            if message and not message.photo:
                try:
                    return await bot.edit_message_text(
                        html,
                        chat_id=owner,
                        message_id=message.message_id,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
                except TelegramBadRequest as error:
                    if "message is not modified" in str(error).lower():
                        return message
                    raise
            sent = await bot.send_message(
                owner, html, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True
            )
            if message:
                # Telegram cannot remove a photo through editMessageMedia.
                await bot.delete_message(owner, message.message_id)
            return sent

    async def browse(self, source, mode, offset=0, message=None, parent="home"):
        page = await self.app.feeds[source].queue_request(mode, offset)
        item = page["item"]
        token = uuid.uuid4().hex[:16]
        rows = []
        photo = None
        if item:
            card = item["presentation"]
            html = card["html"] + f"\n\n{mode.title()} · {page['offset'] + 1} / {page['total']}"
            photo = card.get("photo_url")
            rows.append(
                [
                    button("↩ Unview" if item["viewed"] else "✓ Viewed", f"view:{token}:viewed"),
                    button("★ Saved" if item["favorite"] else "☆ Favorite", f"view:{token}:favorite"),
                ]
            )
            host = urlsplit(item["url"]).hostname or "listing"
            platform = "OLX" if host.endswith("olx.pl") else "Otodom" if host.endswith("otodom.pl") else host
            links = [InlineKeyboardButton(text=platform, url=item["url"])]
            if card.get("copy_text"):
                links.append(
                    InlineKeyboardButton(
                        text="📋 Copy phone", copy_text=CopyTextButton(text=card["copy_text"])
                    )
                )
            rows.append(
                [
                    button(
                        "View queue" if mode == "favorites" else "★ Favorites",
                        f"view:{token}:queue" if mode == "favorites" else f"view:{token}:favorites",
                    )
                ]
            )
            rows.append(links)
        else:
            html = (
                "No favorites yet." if mode == "favorites" else "No unviewed listings. You're all caught up."
            )
        # Navigation is always the final row, including Home in empty states.
        nav = []
        if item and page["offset"] > 0:
            nav.append(button("← Previous", f"view:{token}:prev"))

        if item and page["offset"] + 1 < page["total"]:
            nav.append(button("Next →", f"view:{token}:next"))
        if nav:
            rows.append(nav)
        rows.append([button("← Back", f"back:{source}:{parent}"), button("🏠 Deck", "home")])
        sent = await self.display(html, photo, InlineKeyboardMarkup(inline_keyboard=rows), message)
        if not hasattr(sent, "message_id"):
            raise ValueError("Missing review message identity")
        with self.app.store.db:
            if message:
                self.app.store.db.execute(
                    "DELETE FROM review_views WHERE message_id=?", (message.message_id,)
                )
            if item:
                self.app.store.db.execute(
                    "INSERT INTO review_views(token,source,mode,offset,item,message_id,parent) VALUES(?,?,?,?,?,?,?)",
                    (token, source, mode, page["offset"], json.dumps(item), sent.message_id, parent),
                )
        return sent

    async def handle(self, update):
        if not self.sources:
            return
        callback = update.callback_query
        message = callback.message if callback else update.message
        sender = callback.from_user if callback else message.from_user if message else None
        owner = self.app.settings.allowed_user_id
        # Both checks precede any source reads, writes or Telegram response.
        if (
            not sender
            or sender.id != owner
            or not isinstance(message, Message)
            or message.chat.type != "private"
            or message.chat.id != owner
        ):
            return
        async with self.lock:
            if not callback:
                command = (message.text or "").split("@", 1)[0]
                source = next(iter(self.sources))
                if command in ("/start", "/menu"):
                    await self.home()
                elif command == "/vibecoding":
                    await self.app.send("Under construction")
                elif command in ("/housing", "/queue", "/favorites"):
                    await self.browse(source, "favorites" if command == "/favorites" else "queue")
                return
            data = callback.data or ""
            if data == "vibecoding":
                await self.app.bot.answer_callback_query(
                    callback.id, text="Under construction", show_alert=True
                )
                return
            if data.startswith("back:"):
                parts = data.split(":")
                if len(parts) != 3 or parts[1] not in self.sources or parts[2] not in ("home", "queue"):
                    return
                await self.app.bot.answer_callback_query(callback.id)
                if parts[2] == "queue":
                    await self.browse(parts[1], "queue", message=message)
                else:
                    await self.home(message)
                return
            if data == "home":
                await self.app.bot.answer_callback_query(callback.id)
                await self.home(message)
                with self.app.store.db:
                    self.app.store.db.execute(
                        "DELETE FROM review_views WHERE message_id=?", (message.message_id,)
                    )
                return
            if data.startswith("browse:"):
                parts = data.split(":")
                if len(parts) != 3 or parts[1] not in self.sources or parts[2] not in ("queue", "favorites"):
                    return
                await self.app.bot.answer_callback_query(callback.id)
                # Keep digest/menu as a reusable entry point; navigation edits one new card.
                await self.browse(parts[1], parts[2])
                return
            parts = data.split(":")
            if (
                len(parts) != 3
                or parts[0] != "view"
                or parts[2] not in ("prev", "next", "viewed", "favorite", "favorites", "queue")
            ):
                return
            view = self.app.store.one(
                "SELECT * FROM review_views WHERE token=? AND message_id=?", (parts[1], message.message_id)
            )
            if not view or view["source"] not in self.sources:
                await self.app.bot.answer_callback_query(
                    callback.id, text="Card changed. Open the queue again."
                )
                return
            await self.app.bot.answer_callback_query(callback.id)
            offset = view["offset"]
            action = parts[2]
            if action in ("favorites", "queue"):
                await self.browse(
                    view["source"],
                    action,
                    message=message,
                    parent="queue" if action == "favorites" else "home",
                )
                return
            if action in ("prev", "next"):
                offset = max(0, offset + (1 if action == "next" else -1))
            else:
                item = json.loads(view["item"])
                await self.app.feeds[view["source"]].queue_request(
                    item=(item["connector"], item["id"]), changes={action: not item[action]}
                )
            await self.browse(view["source"], view["mode"], offset, message, parent=view["parent"])
