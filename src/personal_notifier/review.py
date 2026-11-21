"""Owner-only browsing of source-owned queues; no access to execution controls."""

import asyncio
import json
import logging
import time
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputRichMessage,
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
        self.previews: dict[int, tuple[str, dict[int, tuple[float, asyncio.Task]]]] = {}
        self.tasks: set[asyncio.Task] = set()
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
        if source not in self.sources:
            raise PermissionError("Subscription required")
        if self.recipient.get() != self.app.settings.allowed_user_id:
            kwargs["actor"] = str(self.recipient.get())
        return await self.app.feeds[source].queue_request(mode, offset, **kwargs)

    def background(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.previews.clear()

    def discard_previews(self, recipient):
        window = self.previews.pop(recipient, None)
        if window:
            for _, task in window[1].values():
                task.cancel()

    async def preview(self, source, mode, offset, sort):
        try:
            page = await self.queue_request(source, mode, offset, sort=sort)
            if page["item"] and page["offset"] == offset:
                return page
        except Exception as error:
            log.debug("review.preview_unavailable error=%s", type(error).__name__)
        return None

    async def acknowledge(self, callback_id):
        try:
            await self.app.bot.answer_callback_query(callback_id, request_timeout=2)
        except Exception as error:
            log.debug("review.acknowledgement_unavailable error=%s", type(error).__name__)

    @property
    def sources(self):
        return {
            source.name: source
            for source in self.app.settings.sources
            if source.queue and self.app.audience.subscriptions.allowed(self.recipient.get(), source.topic)
        }

    def menu(self):
        rows = []
        for source, config in self.sources.items():
            if config.topic == "housing":
                rows.append([button("🏠 Housing", f"housing:{source}")])
        if any(config.topic.startswith("market.") for config in self.sources.values()):
            rows.append([button("🛍 Market", "market")])
        if self.app.settings.home_socket and self.app.audience.subscriptions.allowed(
            self.recipient.get(), "home.temperature"
        ):
            rows.append([button("🌡 Home", "home:temperature")])
        if self.recipient.get() == self.app.settings.allowed_user_id:
            rows.append([button("⚙️ Management", "manage:home")])
        return InlineKeyboardMarkup(inline_keyboard=rows or [[button("🔄 Refresh", "home")]])

    async def management(self, data, message):
        if self.recipient.get() != self.app.settings.allowed_user_id:
            return
        from personal_notifier.subscriptions import TOPICS

        parts = data.split(":")
        topics = list(TOPICS)
        users = self.app.store.rows("SELECT * FROM product_users ORDER BY user_id")
        rows = []
        title = "⚙️ Management"
        if parts == ["manage", "home"]:
            rows = [[button("🔔 Topics", "manage:topics"), button("👥 Users", "manage:users")]]
        elif parts == ["manage", "topics"]:
            rows = [[button(label, f"manage:topic:{index}")] for index, label in enumerate(TOPICS.values())]
        elif parts == ["manage", "users"]:
            rows = [[button(user["label"], f"manage:user:{user['user_id']}")] for user in users]
        elif len(parts) == 3 and parts[1] in ("topic", "user"):
            if parts[1] == "topic":
                index = int(parts[2])
                if not 0 <= index < len(topics):
                    return
                title = TOPICS[topics[index]]
                rows = [
                    [
                        button(
                            (
                                "✅ "
                                if self.app.audience.subscriptions.allowed(user["user_id"], topics[index])
                                else "⬜ "
                            )
                            + user["label"],
                            f"manage:set:{user['user_id']}:{index}:{int(not self.app.audience.subscriptions.allowed(user['user_id'], topics[index]))}:topic",
                        )
                    ]
                    for user in users
                ]
            else:
                user_id = int(parts[2])
                if not any(user["user_id"] == user_id for user in users):
                    return
                title = "👤 User " + str(user_id)
                rows = [
                    [
                        button(
                            ("✅ " if self.app.audience.subscriptions.allowed(user_id, topic) else "⬜ ")
                            + label,
                            f"manage:set:{user_id}:{index}:{int(not self.app.audience.subscriptions.allowed(user_id, topic))}:user",
                        )
                    ]
                    for index, (topic, label) in enumerate(TOPICS.items())
                ]
        elif len(parts) == 6 and parts[1] == "set":
            user_id, index, enabled = map(int, parts[2:5])
            if not 0 <= index < len(topics) or enabled not in (0, 1) or parts[5] not in ("topic", "user"):
                return
            heads = None
            if enabled and not self.app.audience.subscriptions.allowed(user_id, topics[index]):
                try:
                    heads = await self.app.subscription_heads(topics[index])
                except Exception as error:
                    log.warning("subscription.source_unavailable error=%s", type(error).__name__)
                    await self.display(
                        "Source unavailable. Subscription unchanged. Please retry.",
                        None,
                        self.menu(),
                        message,
                    )
                    return
            self.app.audience.subscriptions.set(
                self.recipient.get(), user_id, topics[index], bool(enabled), heads=heads
            )
            self.discard_previews(user_id)
            log.info(
                "subscription.changed actor=%s recipient=%s topic=%s enabled=%s",
                self.recipient.get(),
                user_id,
                topics[index],
                enabled,
            )
            return await self.management(
                f"manage:{parts[5]}:{index if parts[5] == 'topic' else user_id}", message
            )
        else:
            return
        rows.append(
            [
                button("⬅️ Back", "manage:home" if parts != ["manage", "home"] else "home"),
                button("🏠 Deck", "home"),
            ]
        )
        await self.display(title, None, InlineKeyboardMarkup(inline_keyboard=rows), message)

    async def summary(self, source, text, recipient=None, event_id=None, new_listing=None):
        if text.startswith(("🏠 Housing reminder", "Housing reminder")):
            return None
        import re

        # Producer event text is a historical scan snapshot, for either recipient.
        # Read the same personal unviewed queue used by the carousel at delivery.
        if new_listing or re.search(r"\d+ (?:in queue|waiting in your queue)", text):
            target = recipient or self.app.settings.allowed_user_id
            if not self.app.audience.subscriptions.allowed(
                target, next(config.topic for config in self.app.settings.sources if config.name == source)
            ):
                return None
            kwargs = {"actor": str(target)} if target != self.app.settings.allowed_user_id else {}
            is_new = new_listing if new_listing is not None else re.search(r"\d+ new ·", text) is not None
            if is_new:
                if event_id is None:
                    return None
                kwargs["event_id"] = event_id
            page = await self.app.feeds[source].queue_request(**kwargs)
            if not page["total"]:
                return None
            if is_new:
                fresh = page.get("new_total", 0)
                if not fresh:
                    return None
                text = re.sub(r"\d+ new ·", f"{fresh} new ·", text)
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
        self.discard_previews(self.recipient.get())
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

    async def market(self, message=None):
        from personal_notifier.subscriptions import TOPICS

        self.discard_previews(self.recipient.get())
        rows = [
            [button(TOPICS[config.topic], f"housing:{name}")]
            for name, config in self.sources.items()
            if config.topic.startswith("market.")
        ]
        rows.append([button("⬅️ Back", "home"), button("🏠 Deck", "home")])
        return await self.display(
            "🛍 Market\n\nChoose a collection.", None, InlineKeyboardMarkup(inline_keyboard=rows), message
        )

    async def housing(self, source, message=None):
        from personal_notifier.subscriptions import TOPICS

        self.discard_previews(self.recipient.get())
        config = self.sources[source]
        sent = await self.display(
            "<b>" + TOPICS[config.topic] + "</b>\n\nChoose a collection.",
            None,
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        button("📋 Queue", f"browse:{source}:queue"),
                        button("⭐ Favorites", f"browse:{source}:favorites"),
                    ],
                    [
                        button("⬅️ Back", "market" if config.topic.startswith("market.") else "home"),
                        button("🏠 Deck", "home"),
                    ],
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

    async def display(self, html, photo, markup, message=None, photos=None):
        bot = self.app.bot
        owner = self.recipient.get()
        async with self.app.send_lock:
            sent = None
            photos = list(dict.fromkeys(photos or ([photo] if photo else [])))[:10]
            if len(photos) > 1 or (photo and message and message.rich_message):
                from html import escape

                gallery = "".join(f'<img src="{escape(url, quote=True)}"/>' for url in photos)
                if len(photos) > 1:
                    gallery = "<tg-slideshow>" + gallery + "</tg-slideshow>"
                rich = InputRichMessage(
                    html=gallery
                    + "".join("<p>" + part.replace("\n", "<br/>") + "</p>" for part in html.split("\n\n"))
                )
                try:
                    if message and not message.photo:
                        return await bot.edit_message_text(
                            chat_id=owner,
                            message_id=message.message_id,
                            rich_message=rich,
                            reply_markup=markup,
                        )
                    sent = await bot.send_rich_message(
                        owner, rich_message=rich, reply_markup=markup, disable_notification=True
                    )
                    if message:
                        await bot.delete_message(owner, message.message_id)
                    return sent
                except TelegramBadRequest as error:
                    if "message is not modified" in str(error).lower():
                        return message
                    log.warning("review.gallery_rejected recipient=%s", owner)
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

    async def browse(
        self,
        source,
        mode,
        offset=0,
        message=None,
        parent="housing",
        page=None,
        sort=None,
        navigation_token=None,
    ):
        recipient = self.recipient.get()
        sort = sort or self.app.store.get(f"housing_sort:{recipient}:{source}:{mode}", "added")
        window = self.previews.get(recipient)
        if window and window[0] != navigation_token:
            self.discard_previews(recipient)
            window = None
        previews = window[1] if window else {}
        now = time.monotonic()
        for index, (expires, task) in list(previews.items()):
            if expires <= now:
                task.cancel()
                del previews[index]
        if page is None and offset in previews:
            _, task = previews.pop(offset)
            page = await task
        if page is None:
            page = await self.queue_request(source, mode, offset, sort=sort)
        item = page["item"]
        token = uuid.uuid4().hex[:16]
        rows = []
        photo = None
        photos = None
        if item:
            card = item["presentation"]
            html = card["html"]
            photo = card.get("photo_url")
            photos = card.get("photo_urls")
            rows.append(
                [
                    button("↩ Unview" if item["viewed"] else "✓ Viewed", f"view:{token}:viewed"),
                    button("★ Favorite" if item["favorite"] else "☆ Favorite", f"view:{token}:favorite"),
                ]
            )
            host = urlsplit(item["url"]).hostname or "listing"
            platform = (
                "OLX"
                if host.endswith("olx.pl")
                else "Otodom"
                if host.endswith("otodom.pl")
                else "Allegro Lokalnie"
                if host.endswith("allegrolokalnie.pl")
                else host
            )
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
            label = {
                "added": "Published ↓",
                "updated": "Updated ↓",
                "price": "Rent ↑" if self.sources[source].topic == "housing" else "Price ↑",
            }[sort]
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
        # Fetch while Telegram publishes the current card, carrying over any
        # pending or ready successor when the user advances by one.
        detached = bool(item and item.get("_detached"))
        start = page["offset"] if detached else page["offset"] + 1
        ahead = range(start, min(start + 2, page["total"] - int(detached)))
        for index in list(previews):
            if index not in ahead:
                _, task = previews.pop(index)
                task.cancel()
        for index in ahead:
            if index not in previews:
                previews[index] = (
                    time.monotonic() + 15,
                    self.background(self.preview(source, mode, index, sort)),
                )
        if previews:
            self.previews[recipient] = (token, previews)
        else:
            self.previews.pop(recipient, None)
        try:
            sent = await self.display(
                html, photo, InlineKeyboardMarkup(inline_keyboard=rows), message, photos=photos
            )
        except BaseException:
            self.discard_previews(recipient)
            raise
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
        if (
            not any(source.queue for source in self.app.settings.sources)
            and not self.app.settings.home_socket
        ):
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
            pending = self.app.store.rows(
                "SELECT topic FROM subscription_pending WHERE user_id=?", (self.recipient.get(),)
            )
            for row in pending:
                try:
                    heads = await self.app.subscription_heads(row["topic"])
                except Exception as error:
                    log.warning(
                        "subscription.enrollment_pending recipient=%s error=%s",
                        self.recipient.get(),
                        type(error).__name__,
                    )
                    await self.display("Source unavailable. Please try /start again.", None, self.menu())
                    return
                self.app.audience.subscriptions.set(
                    self.app.settings.allowed_user_id, self.recipient.get(), row["topic"], True, heads=heads
                )
            if not callback:
                command = (message.text or "").split("@", 1)[0]
                source = next(
                    (name for name, config in self.sources.items() if config.topic == "housing"), None
                )
                if command == "/start" and self.recipient.get() != self.app.settings.allowed_user_id:
                    if not await self.app.housing_guide(self.recipient.get()):
                        await self.home()
                elif command in ("/start", "/menu"):
                    await self.home()
                elif command == "/vibecoding":
                    await self.display(
                        "Technical outcomes are available in @node_radar_bot.", None, self.menu()
                    )
                elif command == "/housing" and source:
                    await self.housing(source)
                elif command in ("/queue", "/favorites") and source:
                    await self.browse(
                        source,
                        "favorites" if command == "/favorites" else "queue",
                        sort="added" if command == "/queue" else None,
                    )
                return
            data = callback.data or ""
            if data == "market":
                if not any(config.topic.startswith("market.") for config in self.sources.values()):
                    return
                self.background(self.acknowledge(callback.id))
                await self.market(message)
                return
            if data == "home:temperature":
                if not self.app.settings.home_socket or not self.app.audience.subscriptions.allowed(
                    self.recipient.get(), "home.temperature"
                ):
                    return
                self.background(self.acknowledge(callback.id))
                state = self.app.home.state
                sample = state.get("sample")
                text = "🌡 Home\n\nNo fresh measurement available."
                if sample:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    measured = datetime.fromtimestamp(sample["at"] / 1000, ZoneInfo("Europe/Warsaw"))
                    text = f"🌡 Home\n\n{sample['temperature'] / 1000:g} °C\nMeasured: {measured:%d.%m.%Y %H:%M %Z}\n"
                    text += "Alarm active" if state.get("active") else "No active alarm"
                    if not state.get("fresh") or __import__("time").time() * 1000 > sample.get(
                        "valid_until", sample["at"] + 360000
                    ):
                        text += "\nLast known reading · stale"
                await self.display(
                    text,
                    None,
                    InlineKeyboardMarkup(
                        inline_keyboard=[[button("⬅️ Back", "home"), button("🏠 Deck", "home")]]
                    ),
                    message,
                )
                return
            if data.startswith("manage:"):
                if self.recipient.get() == self.app.settings.allowed_user_id:
                    self.background(self.acknowledge(callback.id))
                    try:
                        await self.management(data, message)
                    except (ValueError, PermissionError):
                        return
                return
            if data == "vibecoding":
                await self.app.bot.answer_callback_query(
                    callback.id, text="Technical outcomes are available in @node_radar_bot.", show_alert=True
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
                self.background(self.acknowledge(callback.id))
                if parts[2] in ("queue", "housing"):
                    await self.housing(parts[1], message)
                else:
                    await self.home(message)
                return
            if data == "home":
                self.background(self.acknowledge(callback.id))
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
                    self.background(self.acknowledge(callback.id))
                    await self.housing(source, message)
                return
            if data.startswith("browse:"):
                parts = data.split(":")
                if len(parts) != 3 or parts[1] not in self.sources or parts[2] not in ("queue", "favorites"):
                    return
                self.background(self.acknowledge(callback.id))
                await self.browse(
                    parts[1], parts[2], message=message, sort="added" if parts[2] == "queue" else None
                )
                return
            parts = data.split(":")
            if (
                len(parts) != 3
                or parts[0] != "view"
                or parts[2]
                not in (
                    "prev",
                    "next",
                    "viewed",
                    "favorite",
                    "favorites",
                    "queue",
                    "position",
                    "sort",
                    "photos",
                )
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
            self.background(self.acknowledge(callback.id))
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
                self.discard_previews(self.recipient.get())
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
                view["source"],
                view["mode"],
                offset,
                message,
                parent=view["parent"],
                sort=view["sort"],
                navigation_token=view["token"] if action in ("prev", "next") else None,
            )
