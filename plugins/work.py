import random
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    RPCError,
    UserNotParticipant,
)
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import LOGGER, images
from database.database import add_user, get_variable, present_user, set_variable

log = LOGGER(__name__)

# Cache Globals
AUTH_CACHE = {}  # {user_id: expire_timestamp}
FSUB_CACHE = {'last_updated': 0, 'fsub': [], 'rsub': [], 'req_links': []}

async def get_cached_fsub_config(client):
    """Get FSub config with 60s cache and verify bot admin status."""
    now = datetime.utcnow().timestamp()
    if now - FSUB_CACHE['last_updated'] < 60:
        return FSUB_CACHE['fsub'], FSUB_CACHE['rsub'], FSUB_CACHE['req_links']

    # Refresh - Remove Defaults!
    raw_fsub = await get_variable("F_sub", "")
    fsub_ids = [int(x.strip()) for x in raw_fsub.split() if x.strip()]

    # Verify Admin Status for F_Sub
    valid_fsub_ids = []
    for chat_id in fsub_ids:
        try:
            member = await client.get_chat_member(chat_id, "me")
            if member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
                valid_fsub_ids.append(chat_id)
            else:
                log.warning(f"Bot is not admin in F_SUB channel {chat_id}, skipping.")
        except Exception as e:
            log.warning(f"Could not verify admin status for F_SUB {chat_id}: {e}")

    raw_data = await get_variable("r_sub", "")
    rsub_entries = [x.strip() for x in raw_data.split(",") if x.strip()]
    parsed_rsub = []

    # Verify Admin Status for R_Sub
    for entry in rsub_entries:
        try:
            if "||" in entry:
                chan_id_str, invite_link = entry.split("||")
                chat_id = int(chan_id_str.strip())

                # Verify Bot Admin
                is_admin = False
                try:
                    member = await client.get_chat_member(chat_id, "me")
                    if member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
                        is_admin = True
                    else:
                        log.warning(f"Bot is not admin in R_SUB channel {chat_id}, skipping.")
                except Exception as e:
                     log.warning(f"Could not verify admin status for R_SUB {chat_id}: {e}")

                if is_admin:
                    parsed_rsub.append((chat_id, invite_link.strip(), entry))
        except ValueError:
            continue

    req_links = await get_variable("req_link", [])

    FSUB_CACHE['last_updated'] = now
    FSUB_CACHE['fsub'] = valid_fsub_ids
    FSUB_CACHE['rsub'] = parsed_rsub
    FSUB_CACHE['req_links'] = req_links

    return valid_fsub_ids, parsed_rsub, req_links


async def get_force_sub_ids():
    """Retrieve forced subscription channel IDs."""
    raw_fsub = await get_variable(
        "F_sub", ""
    )
    return [int(x.strip()) for x in raw_fsub.split() if x.strip()]


async def get_req_sub_data():
    """Retrieve requested subscription data."""
    raw_data = await get_variable("r_sub", "")
    entries = [x.strip() for x in raw_data.split(",") if x.strip()]
    parsed_entries = []
    for entry in entries:
        try:
            if "||" in entry:
                chan_id_str, invite_link = entry.split("||")
                parsed_entries.append((int(chan_id_str.strip()), invite_link.strip(), entry))
        except ValueError:
            continue
    return parsed_entries


async def is_user_joined(client, channel_id, user_id):
    """Check if a user is a member of a channel."""
    try:
        user = await client.get_chat_member(channel_id, user_id)
        if user.status in {
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.RESTRICTED,
        }:
            return True
    except (UserNotParticipant, ChatAdminRequired, RPCError, ChannelPrivate):
        pass
    return False


async def get_missing_channels(client, user_id):
    """
    Identify which channels the user needs to join.
    Returns a list of tuples: (channel_id, invite_link, channel_name_or_id)
    """
    missing = []

    # Check Force Subs
    fsub_ids, req_subs, req_links = await get_cached_fsub_config(client)

    for channel_id in fsub_ids:
        if not await is_user_joined(client, channel_id, user_id):
            # Generate or get link
            try:
                chat = await client.get_chat(channel_id)
                name = chat.title
                if str(channel_id).startswith("-100"):
                     # Try to create decent one time link if possible or fallback
                    try:
                        expire = datetime.utcnow() + timedelta(minutes=5)
                        invite = await client.create_chat_invite_link(channel_id, expire_date=expire)
                        link = invite.invite_link
                    except Exception:
                        link = f"https://t.me/c/{str(channel_id)[4:]}"
                else:
                    link = f"https://t.me/{channel_id}"
            except Exception:
                name = "Channel"
                link = f"https://t.me/c/{str(channel_id)[4:]}" if str(channel_id).startswith("-100") else f"https://t.me/{channel_id}"

            missing.append({'name': name, 'url': link, 'type': 'fsub'})

    # Check Request Subs (req_subs and req_links come from cache now)
    # req_subs = await get_req_sub_data()
    # req_links = await get_variable("req_link", [])

    # Optimization: Get all request links user is already 'sada' (approved/tracked) in, to skip db calls inside loop if possible
    # But usually 'sada' is per link.

    for chan_id, invite_link, entry in req_subs:
        # User is valid if:
        # 1. In the channel
        # 2. OR In the invite list for that link ('sada')

        is_in_channel = await is_user_joined(client, chan_id, user_id)

        is_in_invite_list = False
        if invite_link in req_links:
            sada = await get_variable(f"{invite_link}", [])
            if user_id in sada:
                is_in_invite_list = True

        if not (is_in_channel or is_in_invite_list):
            # Need to fetch name
            try:
                chat = await client.get_chat(chan_id)
                name = chat.title
            except Exception:
                name = "Join Channel"

            missing.append({'name': name, 'url': invite_link, 'type': 'rsub'})

    return missing


async def not_subscribed(c, a, message):
    """
    Check if user is NOT subscribed.
    Returns True if user is missing channels (and deletes 'checking' msg).
    Returns False if user is all good.
    """
    user_id = message.from_user.id

    # Check User Cache
    now = datetime.now().timestamp()
    if user_id in AUTH_CACHE:
        if now < AUTH_CACHE[user_id]:
            return False

    ab = await message.reply_text("❗️ Checking subscription...")

    missing = await get_missing_channels(c, user_id)

    if missing:
        await ab.delete()
        return True

    # Success - Cache User
    AUTH_CACHE[user_id] = now + 300 # 5 minutes

    await ab.delete()
    return False

@Client.on_message(filters.private & filters.incoming, group=-1)
async def must_join_channel(client: Client, message: Message):
    """
    This handler runs first (group=-1).
    If the user is NOT subscribed, it handles the UI and stops propagation.
    If the user IS subscribed, it lets the update pass to the next group.
    """
    user_id = message.from_user.id
    now = datetime.now().timestamp()

    # Check Cache First
    if user_id in AUTH_CACHE and now < AUTH_CACHE[user_id]:
        return # Letting propagation continue

    # Using helper which might hit DB/API if not cached
    if await not_subscribed(client, client, message):
        # User is missing channels.
        # 'not_subscribed' sent "Checking..." then deleted it.
        # We MUST show the Buttons UI.
        await force_subs(client, message)
        message.stop_propagation()
    else:
        # User is fine (and cache was updated in not_subscribed)
        pass

@Client.on_message(filters.private)
async def subscribed(c, message, q=0):
    """
    Checks subscription.
    Returns True if subscribed to everything.
    Returns False if missing something.
    """
    # 'q' seems to be callback_query if present, 'message' is message
    # If called from button click (check_subscription), q is the callback query
    user_id = q.from_user.id if q else message.from_user.id

    # Use message object for replying
    target_msg = q.message if q else message

    if not q:
        # If not a callback, we might want to show a 'checking' message
        status_msg = await target_msg.reply_text("❗️ Checking subscription...")

    missing = await get_missing_channels(c, user_id)

    if not missing:
        if not q:
            await status_msg.delete()
        return True

    if not q:
        await status_msg.delete()
    return False


async def force_subs(client, message):
    """
    Entry point for checking subs. If missing, sends the UI.
    """
    user_id = message.from_user.id
    text = message.text

    # Store user
    if not await present_user(user_id):
        await add_user(user_id)

    # Extract start parameter if any
    string = ""
    if len(text) > 7:
        try:
             string = text.split(" ", 1)[1]
        except Exception:
            pass

    # Initial loading
    a = await message.reply_text("♻️")

    missing = await get_missing_channels(client, user_id)

    if not missing:
        await a.delete()
        return # Should probably continue to normal flow if called, but this function implies "force subs UI"

    # Build Buttons
    buttons = []
    for m in missing:
        buttons.append([InlineKeyboardButton(text=f"• ᴊᴏɪɴ {m['name']} •", url=m['url'])])

    buttons.append([
        InlineKeyboardButton(
            text="• ᴊᴏɪɴᴇᴅ •", callback_data=f"check_subscription{string}"
        )
    ])

    await a.delete()

    image_url = random.choice(images) if images else "https://telegra.ph/file/f3d3aff9ec422158feb05-d2180e3665e0ac4d32.jpg"

    total_req = len(await get_force_sub_ids()) + len(await get_variable("req_link", [])) # Approximate
    # Better to just use len(missing) for "You currently haven't joined X channels"

    caption = (
        f"<blockquote>💠 𝙔𝙊𝙊, {message.from_user.mention} ❗️</blockquote>\n\n"
        f" 𝙔𝙊𝙐 𝙃𝘼𝙑𝙀𝙉'𝙏 𝙅𝙊𝙄𝙉𝙀𝘿 𝘼𝙇𝙇 𝙏𝙃𝙀 𝘾𝙃𝘼𝙉𝙉𝙀𝙇𝙎 𝙍𝙀𝙌𝙐𝙄𝙍𝙀𝘿 𝙏𝙊 𝙐𝙎𝙀 𝙏𝙃𝙀 𝘽𝙊𝙏.. ♻️💤\n\n"
        f"<blockquote>📵 ᴊᴏɪɴ ɴᴏᴡ ᴛᴏ ᴜꜱᴇ ᴛʜᴇ ʙᴏᴛ ‼️</blockquote>"
    )

    await message.reply_photo(
        photo=image_url,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex(r"^check_subscription"))
async def check_subscription(client, callback_query: CallbackQuery):
    try:
        string = callback_query.data.split("check_subscription", 1)[1]
    except IndexError:
        string = ""
    """
    Callback handler for 'Joined' button.
    """
    user_id = callback_query.from_user.id
    missing = await get_missing_channels(client, user_id)

    if not missing:
        # Success
        new_text = "<blockquote><b><i>Please Click Button Below 👇 to get your file 💠</i></b></blockquote>"
        key = None
        if string:
             key = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    text="• ɴᴏᴡ ᴄʟɪᴄᴋ ʜᴇʀᴇ •",
                    url=f"https://t.me/{client.username}?start={string}",
                )]
            ])
        else:
            new_text = "**ʏᴏᴜ ʜᴀᴠᴇ ᴊᴏɪɴᴇᴅ ᴀʟʟ ᴛʜᴇ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs. ᴛʜᴀɴᴋ ʏᴏᴜ! 😊 /start ɴᴏᴡ**"
            key = None

        if callback_query.message.caption != new_text:
            await callback_query.message.edit_caption(
                caption=new_text,
                reply_markup=key
            )
        return

    # Still missing channels, refresh UI
    buttons = []
    for m in missing:
        buttons.append([InlineKeyboardButton(text=f"• ᴊᴏɪɴ {m['name']} •", url=m['url'])])

    buttons.append([
        InlineKeyboardButton(
            text="• ᴊᴏɪɴᴇᴅ •", callback_data=f"check_subscription{string}"
        )
    ])

    alert_text = "Bete I like your smartness But Channel to join karna padega 🪬💀"
    await callback_query.answer(alert_text, show_alert=True)

    # Update buttons if changed
    try:
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        pass


@Client.on_message(filters.command("vars") & filters.private)
async def varsa(client, message: Message):
    """
    /var variable-name - variable-value
    """
    try:
        text = message.text.split(maxsplit=1)
        if len(text) < 2:
            return await message.reply_text("Usage: /Vars variable-name - variable-value")

        args = text[1]
        if " - " not in args:
             return await message.reply_text("Separator ' - ' not found.\nUsage: /Vars variable-name - variable-value")

        var_name, var_value = args.split(" - ", 1)
        var_name = var_name.strip()
        var_value = var_value.strip()

        if not var_name or not var_value:
             return await message.reply_text("Empty name or value.")

        if var_name == "admin":
            current_admins = await get_variable("admin", [])
            if not isinstance(current_admins, list):
                current_admins = []
            try:
                new_id = int(var_value)
                if new_id not in current_admins:
                    current_admins.append(new_id)
                    await set_variable("admin", current_admins)
                    await message.reply_text(f"Added {new_id} to admins.")
                else:
                    await message.reply_text(f"{new_id} is already in admins.")
            except ValueError:
                await message.reply_text("Admin value must be an integer (User ID).")
        else:
            await set_variable(var_name, var_value)
            await message.reply_text(f"Variable '{var_name}' set to '{var_value}'")

    except Exception as e:
        log.error(f"Error in varsa: {e}", exc_info=True)
        await message.reply_text(f"An error occurred: {e}")
