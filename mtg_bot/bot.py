import re
from contextlib import asynccontextmanager

import aiohttp as aiohttp
from aiolimiter import AsyncLimiter
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, InlineQueryHandler
from pyrogram.types import InputMediaPhoto, InlineQueryResultPhoto, InlineQueryResultArticle, InputTextMessageContent


class Bot:
    def __init__(self, config):
        auth = config["auth"]
        self.client = Client("mtg_bot", api_id=auth["api_id"], api_hash=auth["api_hash"], bot_token=auth["bot_token"])
        self.limiter = AsyncLimiter(max_rate=10, time_period=1)

    def run(self):

        self.add_reply_handler()
        self.add_inline_handler()
        self.client.run()

    async def start(self):
        await self.client.start()
        await self.client.send_message(chat_id=20422120, text="henlo")
        await self.client.stop()

    def add_reply_handler(self):
        reply_filter = filters.regex(r"\[.+\]")
        reply_handler = MessageHandler(self.process_message, filters=reply_filter)
        self.client.add_handler(reply_handler)

    def add_inline_handler(self):
        inline_handler = InlineQueryHandler(self.process_inline_query)
        self.client.add_handler(inline_handler)

    async def process_message(self, client, message):
        card_names = [match.group(1) for match in re.finditer(r"\[(.+?)]", message.text)]
        for card in card_names:
            card_json = await self.find_card(card)
            if card_json["object"] == "error":
                await message.reply(card_json["details"], quote=True)
            else:
                await self.post_card_from_json(card_json, message)

    async def process_inline_query(self, client, inline_query):
        print(f"recieved inline query: {inline_query.query}")
        if not inline_query.query:
            return
        search_results = await self.search_card_from_scryfall(inline_query.query)
        query_results = []
        if "data" not in search_results:
            await inline_query.answer(
                [
                    InlineQueryResultArticle(
                        title=f"No results found for query {inline_query.query}",
                        input_message_content=InputTextMessageContent(
                            message_text=f"query {inline_query.query} returned no results")
                    )
                ]
            )
            return
        for result in search_results["data"]:
            if "image_uris" in result:
                img_url = result["image_uris"]["normal"]
            else:
                img_url = result["card_faces"][0]["image_uris"]["normal"]
            caption = result["name"] + "\n"
            buttons = []
            if "gatherer" in result["related_uris"]:
                buttons.append(["(G)", result["related_uris"]["gatherer"]])
            buttons.extend(
                [
                    ["(SF)", result["scryfall_uri"]],
                    ["(EDHREC)", result["related_uris"]["edhrec"]]
                ]
            )

            for button in buttons:
                caption += f"<a href=\"{button[1]}\">{button[0]}</a> "
            card_text = []
            rulings = []

            query_results.append(InlineQueryResultPhoto(img_url, title=result["name"], caption=caption))
            print(f"name={result['name']}, imgurl = {img_url}")

        await inline_query.answer(results=query_results[:50], is_gallery=True)

    async def find_card(self, card):
        edition = ""
        if "|" in card:
            card_split = card.split("|")
            card = card_split[0]
            edition = card_split[1]

        card_json = await self.get_card_from_scryfall(card, edition)

        return card_json

    async def get_card_from_scryfall(self, card, edition):
        url = f"https://api.scryfall.com/cards/named?fuzzy={card}&set={edition}"
        async with self.limited_fetch(url) as resp:
            card_json = await resp.json()
        return card_json

    async def search_card_from_scryfall(self, query):
        url = f"https://api.scryfall.com/cards/search?&q={query}"
        async with self.limited_fetch(url) as resp:
            search_json = await resp.json()
        return search_json

    async def post_card_from_json(self, card, message):
        caption = card["name"] + "\n"
        buttons = []
        if "gatherer" in card["related_uris"]:
            buttons.append(["(G)", card["related_uris"]["gatherer"]])
        buttons.extend(
            [
                ["(SF)", card["scryfall_uri"]],
                ["(EDHREC)", card["related_uris"]["edhrec"]]
            ]
        )

        for button in buttons:
            caption += f"<a href=\"{button[1]}\">{button[0]}</a> "
        card_text = []
        rulings = []

        if "card_faces" in card:
            image = [InputMediaPhoto(x["image_uris"]["png"]) for x in card["card_faces"]]
            image[0].caption = caption
            await self.client.send_media_group(
                chat_id=message.chat.id, media=image, reply_to_message_id=message.id
            )
        else:
            image = card["image_uris"]["png"]
            await self.client.send_photo(
                chat_id=message.chat.id, photo=image, caption=caption, reply_to_message_id=message.id
            )

        pass

    @asynccontextmanager
    async def limited_fetch(self, url):
        async with self.limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    yield resp
