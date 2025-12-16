# +++ Modified By [telegram username: @Codeflix_Bots
import asyncio
import sys
from datetime import datetime
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand
from config import API_HASH, APP_ID, LOGGER, TG_BOT_TOKEN, TG_BOT_WORKERS, PORT, OWNER_ID
from plugins import web_server
import pyrogram.utils
from aiohttp import web
from database.database import get_variable, set_variable

pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

name = """
Links Sharing Started
"""

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
        )
        self.LOGGER = LOGGER

    async def start(self, *args, **kwargs):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()


        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info("Bot Running..!\n\nCreated by \nhttps://t.me/ProObito")
        self.LOGGER(__name__).info(f"{name}")
        self.username = usr_bot_me.username

        # Register Commands
        try:
            await self.set_bot_commands([
                BotCommand("start", "Start the bot"),
                BotCommand("addch", "Add a channel (Admin)"),
                BotCommand("delch", "Remove a channel (Admin)"),
                BotCommand("channels", "Show connected channels"),
                BotCommand("reqlink", "Show request links"),
                BotCommand("links", "Show channel links"),
                BotCommand("bulklink", "Generate multiple links"),
                BotCommand("genlink", "Encode external link"),
                BotCommand("reqtime", "Set auto-approve timer"),
                BotCommand("reqmode", "Toggle auto-approve"),
                BotCommand("approveon", "Enable auto-approve for channel"),
                BotCommand("approveoff", "Disable auto-approve for channel"),
                BotCommand("approveall", "Approve all requests"),
            ])
        except Exception as e:
            self.LOGGER(__name__).warning(f"Failed to set bot commands: {e}")

        # Sync Owner ID to Database
        try:
            current_owners_str = await get_variable("owner", "")
            current_owners = [int(x.strip()) for x in current_owners_str.split() if x.strip()]

            if OWNER_ID not in current_owners:
                current_owners.append(OWNER_ID)
                new_owner_str = " ".join(map(str, current_owners))
                await set_variable("owner", new_owner_str)
                self.LOGGER(__name__).info(f"Added Config Owner ID {OWNER_ID} to Database 'owner' variable.")
        except Exception as e:
             self.LOGGER(__name__).warning(f"Failed to sync owner ID to DB: {e}")

        # Web-response
        try:
            app = web.AppRunner(await web_server())
            await app.setup()
            bind_address = "0.0.0.0"
            await web.TCPSite(app, bind_address, PORT).start()
            self.LOGGER(__name__).info(f"Web server started on {bind_address}:{PORT}")
        except Exception as e:
            self.LOGGER(__name__).error(f"Failed to start web server: {e}")

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

# Global cancel flag for broadcast
is_canceled = False
cancel_lock = asyncio.Lock()

if __name__ == "__main__":
    Bot().run()
