"""Owner-only browsing of source-owned queues; no access to execution controls."""

import asyncio
import json
import logging
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)


def button(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


log = logging.getLogger(__name__)


class ReviewUI:
    def __init__(self, app):
        self.app = app
        self.lock = asyncio.Lock()
        self.recipient = ContextVar("review_recipient", default=app.settings.allowed_user_id)
        self.app.store.db.execute("""CREATE TABLE IF NOT EXISTS review_screens(
            token TEXT PRIMARY KEY,source TEXT NOT NULL,mode TEXT NOT NULL,
            offset INTEGER NOT NULL,item TEXT NOT NULL,message_id INTEGER NOT NULL,
            parent TEXT NOT NULL DEFAULT 'housing',chat_id INTEGER NOT NULL,
            sort TEXT NOT NULL DEFAULT 'added',UNIQUE(chat_id,message_id))""")
        if "sort" not in {row[1] for row in app.store.db.execute("PRAGMA table_info(review_screens)")}:
            app.store.db.execute("ALTER TABLE review_screens ADD COLUMN sort TEXT NOT NULL DEFAULT 'added'")
        if not app.store.get("review_screens_migrated"):
            if app.store.one("SELECT name FROM sqlite_master WHERE name='review_views'"):
                self.app.store.db.execute(
                    "INSERT OR IGNORE INTO review_screens(token,source,mode,offset,item,message_id,parent,chat_id) SELECT token,source,mode,offset,item,message_id,parent,? FROM review_views",
                    (app.settings.allowed_user_id,),
                )
            app.store.set("review_screens_migrated", "1")
        self.app.store.db.commit()

    async def queue_request(self, source, mode="queue", offset=0, **kwargs):
        if self.recipient.get() != self.app.settings.allowed_user_id:
            kwargs["actor"] = str(self.recipient.get())
        return await self.app.feeds[source].queue_request(mode, offset, **kwargs)

    @property
    def sources(self):
        return {source.name: source for source in self.app.settings.sources if source.queue}

    def menu(self):
        source = next(iter(self.sources))
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [button("🛠 Vibecoding", "vibecoding")],
                [button("🏠 Housing", f"housing:{source}")],
            ]
        )

    async def summary(self, source, text, recipient=None):
        import re

        # Producer event text is a historical scan snapshot, for either recipient.
        # Read the same personal unviewed queue used by the carousel at delivery.
        if re.search(r"\d+ (?:in queue|waiting in your queue)", text):
            target = recipient or self.app.settings.allowed_user_id
            kwargs = {"actor": str(target)} if target != self.app.settings.allowed_user_id else {}
            page = await self.app.feeds[source].queue_request(**kwargs)
            if not page["total"]:
                return None
            text = re.sub(
                r"\d+ (in queue|waiting in your queue)", lambda match: f"{page['total']} {match[1]}", text
            )
        async with self.app.send_lock:
            return await self.app.bot.send_message(
                recipient or self.app.settings.allowed_user_id,
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
                    "DELETE FROM review_screens WHERE message_id=? AND chat_id=?",
                    (message.message_id, self.recipient.get()),
                )
        return sent

    async def housing(self, source, message=None):
        sent = await self.display(
            "<b>🏠 Housing</b>\n\nChoose a collection.",
            None,
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        button("📋 Queue", f"browse:{source}:queue"),
                        button("⭐ Favorites", f"browse:{source}:favorites"),
                    ],
                    [button("⬅️ Back", "home"), button("🏠 Deck", "home")],
                ]
            ),
            message,
        )
        if message:
            with self.app.store.db:
                self.app.store.db.execute(
                    "DELETE FROM review_screens WHERE message_id=? AND chat_id=?",
                    (message.message_id, self.recipient.get()),
                )
        return sent

    async def display(self, html, photo, markup, message=None):
        bot = self.app.bot
        owner = self.recipient.get()
        async with self.app.send_lock:
            sent = None
            if photo:
                try:
                    if message:
                        sent = await bot.edit_message_media(
                            chat_id=owner,
                            message_id=message.message_id,
                            media=InputMediaPhoto(
                                media=photo, caption=html, parse_mode="HTML", show_caption_above_media=False
                            ),
                            reply_markup=markup,
                        )
                    else:
                        sent = await bot.send_photo(
                            owner,
                            photo,
                            caption=html,
                            parse_mode="HTML",
                            show_caption_above_media=False,
                            reply_markup=markup,
                        )
                except TelegramBadRequest as error:
                    if "message is not modified" in str(error).lower():
                        sent = message
                    # Explicitly rejected media falls back to a genuine text screen.
                    # Ambiguous network failures propagate rather than duplicate sends.
            if sent is None:
                if message and not message.photo:
                    try:
                        sent = await bot.edit_message_text(
                            html,
                            chat_id=owner,
                            message_id=message.message_id,
                            parse_mode="HTML",
                            reply_markup=markup,
                            disable_web_page_preview=True,
                        )
                    except TelegramBadRequest as error:
                        if "message is not modified" not in str(error).lower():
                            raise
                        sent = message
                else:
                    sent = await bot.send_message(
                        owner,
                        html,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
                    if message:
                        # Telegram cannot remove photo media through an edit. Replace
                        # only that transition; never insert a fabricated menu image.
                        await bot.delete_message(owner, message.message_id)
            if not isinstance(sent, Message):
                raise ValueError("Missing Telegram screen identity")
            if not sent.reply_markup or not sent.reply_markup.inline_keyboard:
                repaired = await bot.edit_message_reply_markup(
                    chat_id=owner, message_id=sent.message_id, reply_markup=markup
                )
                if not isinstance(repaired, Message) or not repaired.reply_markup:
                    raise ValueError("Telegram did not retain the screen keyboard")
                sent = repaired
            return sent

    async def browse(self, source, mode, offset=0, message=None, parent="housing", page=None, sort=None):
        sort = sort or self.app.store.get(f"housing_sort:{self.recipient.get()}:{source}:{mode}", "added")
        page = page if page is not None else await self.queue_request(source, mode, offset, sort=sort)
        item = page["item"]
        token = uuid.uuid4().hex[:16]
        rows = []
        photo = None
        if item:
            card = item["presentation"]
            html = card["html"]
            photo = card.get("photo_url")
            rows.append(
                [
                    button("↩ Unview" if item["viewed"] else "✓ Viewed", f"view:{token}:viewed"),
                    button("★ Favorite" if item["favorite"] else "☆ Favorite", f"view:{token}:favorite"),
                ]
            )
            host = urlsplit(item["url"]).hostname or "listing"
            platform = "OLX" if host.endswith("olx.pl") else "Otodom" if host.endswith("otodom.pl") else host
            rows[0].append(InlineKeyboardButton(text=platform, url=item["url"]))
            if card.get("copy_text"):
                rows.append(
                    [
                        InlineKeyboardButton(
                            text="📋 Copy phone", copy_text=CopyTextButton(text=card["copy_text"])
                        )
                    ]
                )
        else:
            html = (
                "No favorites yet." if mode == "favorites" else "No unviewed listings. You're all caught up."
            )
        label = "Favorites" if mode == "favorites" else "Queue"
        position = page["offset"] + 1 if item else 0
        html += f"\n\n──────────\n{label} · {position} / {page['total']}"
        if page.get("last_refresh"):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            try:
                stamp = datetime.fromisoformat(page["last_refresh"].replace("Z", "+00:00"))
                if stamp.tzinfo is not None:
                    local = stamp.astimezone(ZoneInfo("Europe/Warsaw"))
                    html += "\nLast refresh: " + local.strftime("%d.%m %H:%M %Z")
            except (ValueError, TypeError, AttributeError):
                pass
        if item:
            label = {"added": "Published ↓", "updated": "Updated ↓", "price": "Rent ↑"}[sort]
            rows.append([button("↕️ Sort: " + label, f"view:{token}:sort")])
        # Navigation is always the final row, including Home in empty states.
        nav = []
        if item and page["offset"] > 0:
            nav.append(button("⬅️", f"view:{token}:prev"))

        if item and page["offset"] + 1 < page["total"]:
            nav.append(button("➡️", f"view:{token}:next"))
        if nav:
            rows.append(nav)
        rows.append([button("⬅️ Back", f"back:{source}:housing"), button("🏠 Deck", "home")])
        sent = await self.display(html, photo, InlineKeyboardMarkup(inline_keyboard=rows), message)
        if not hasattr(sent, "message_id"):
            raise ValueError("Missing review message identity")
        with self.app.store.db:
            if message:
                self.app.store.db.execute(
                    "DELETE FROM review_screens WHERE message_id=? AND chat_id=?",
                    (message.message_id, self.recipient.get()),
                )
            if item:
                self.app.store.db.execute(
                    "INSERT INTO review_screens(token,source,mode,offset,item,message_id,parent,chat_id,sort) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        token,
                        source,
                        mode,
                        page["offset"],
                        json.dumps(item),
                        sent.message_id,
                        parent,
                        self.recipient.get(),
                        sort,
                    ),
                )
        return sent

    async def handle(self, update):
        if not self.sources:
            return
        callback = update.callback_query
        message = callback.message if callback else update.message
        sender = callback.from_user if callback else message.from_user if message else None
        if (
            not sender
            or not isinstance(message, Message)
            or not self.app.audience.authorize(sender, message, callback)
        ):
            return
        token = self.recipient.set(sender.id)
        try:
            log.info(
                "review.open recipient=%s operation=%s", sender.id, "callback" if callback else "command"
            )
            await self._handle(update, message, callback)
        finally:
            self.recipient.reset(token)

    async def _handle(self, update, message, callback):
        async with self.lock:
            if not callback:
                command = (message.text or "").split("@", 1)[0]
                source = next(iter(self.sources))
                if command == "/start" and self.recipient.get() != self.app.settings.allowed_user_id:
                    if not await self.app.housing_guide(self.recipient.get()):
                        await self.home()
                elif command in ("/start", "/menu"):
                    await self.home()
                elif command == "/vibecoding":
                    await self.display("Under construction", None, self.menu())
                elif command == "/housing":
                    await self.housing(source)
                elif command in ("/queue", "/favorites"):
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
                if (
                    len(parts) != 3
                    or parts[1] not in self.sources
                    or parts[2] not in ("home", "queue", "housing")
                ):
                    return
                await self.app.bot.answer_callback_query(callback.id)
                if parts[2] in ("queue", "housing"):
                    await self.housing(parts[1], message)
                else:
                    await self.home(message)
                return
            if data == "home":
                await self.app.bot.answer_callback_query(callback.id)
                await self.home(message)
                with self.app.store.db:
                    self.app.store.db.execute(
                        "DELETE FROM review_screens WHERE message_id=? AND chat_id=?",
                        (message.message_id, self.recipient.get()),
                    )
                return
            if data.startswith("housing:"):
                source = data.split(":", 1)[1]
                if source in self.sources:
                    await self.app.bot.answer_callback_query(callback.id)
                    await self.housing(source, message)
                return
            if data.startswith("browse:"):
                parts = data.split(":")
                if len(parts) != 3 or parts[1] not in self.sources or parts[2] not in ("queue", "favorites"):
                    return
                await self.app.bot.answer_callback_query(callback.id)
                await self.browse(parts[1], parts[2], message=message)
                return
            parts = data.split(":")
            if (
                len(parts) != 3
                or parts[0] != "view"
                or parts[2]
                not in ("prev", "next", "viewed", "favorite", "favorites", "queue", "position", "sort")
            ):
                return
            view = self.app.store.one(
                "SELECT * FROM review_screens WHERE token=? AND message_id=? AND chat_id=?",
                (parts[1], message.message_id, self.recipient.get()),
            )
            if not view or view["source"] not in self.sources:
                await self.app.bot.answer_callback_query(
                    callback.id, text="Card changed. Open the queue again."
                )
                return
            await self.app.bot.answer_callback_query(callback.id)
            offset = view["offset"]
            action = parts[2]
            if action == "sort":
                choices = ("added", "updated", "price")
                sort = choices[(choices.index(view["sort"]) + 1) % len(choices)]
                self.app.store.set(
                    f"housing_sort:{self.recipient.get()}:{view['source']}:{view['mode']}", sort
                )
                await self.browse(view["source"], view["mode"], message=message, sort=sort)
                return
            if action == "position":
                return
            if action in ("favorites", "queue"):
                await self.browse(
                    view["source"],
                    action,
                    message=message,
                    parent="queue" if action == "favorites" else "home",
                )
                return
            item = json.loads(view["item"])
            if action in ("prev", "next"):
                # Removing the displayed favorite shifts its successor into this
                # offset. The detached card remains undoable until navigation.
                step = 0 if action == "next" and item.get("_detached") else 1 if action == "next" else -1
                offset = max(0, offset + step)
            else:
                await self.queue_request(
                    view["source"], item=(item["connector"], item["id"]), changes={action: not item[action]}
                )
                if view["mode"] == "favorites":
                    item[action] = not item[action]
                    item["_detached"] = not item["favorite"]
                    current = await self.queue_request(view["source"], "favorites", offset, sort=view["sort"])
                    total = current["total"] + int(item["_detached"])
                    await self.browse(
                        view["source"],
                        "favorites",
                        message=message,
                        sort=view["sort"],
                        page={
                            "item": item,
                            "total": total,
                            "offset": min(offset, total - 1),
                            "last_refresh": current.get("last_refresh"),
                        },
                    )
                    return
            await self.browse(
                view["source"], view["mode"], offset, message, parent=view["parent"], sort=view["sort"]
            )
