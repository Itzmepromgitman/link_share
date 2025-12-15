import re
import pyrogram.utils
from pyrogram import Client, filters
from pyrogram.errors import ChannelPrivate, ChatAdminRequired, RPCError
from pyrogram.errors.pyromod.listener_timeout import ListenerTimeout
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    CallbackQuery,
    Message
)

from config import LOGGER
from database.database import get_variable, set_variable
from plugins.work import FSUB_CACHE

# Monkey patching MIN_CHANNEL_ID if needed
pyrogram.utils.MIN_CHANNEL_ID = -10091474836474
pyrogram.utils.MAX_CHANNEL_ID = -1000000000000

log = LOGGER(__name__)



@Client.on_chat_join_request()
async def onreq(client, join_request):
    """Handle join requests for tracked links."""
    invite_link_str = join_request.invite_link.invite_link
    req_link = await get_variable("req_link", []) or []

    if invite_link_str in req_link:
        # User requested to join via a tracked link
        link_members = await get_variable(f"{invite_link_str}", []) or []
        user_id = join_request.from_user.id

        if user_id not in link_members:
            link_members.append(user_id)
            await set_variable(f"{invite_link_str}", link_members)

            # Increment request counter
            count_key = f"req{invite_link_str}"
            current_count = await get_variable(count_key, 0)
            try:
                current_count = int(current_count)
            except (ValueError, TypeError):
                current_count = 0

            await set_variable(count_key, current_count + 1)



@Client.on_message(filters.command("fsub") & filters.private)
async def fsub1(client, message):
    """
    Main Force Sub Settings Menu
    """
    status_msg = await message.reply_text("processing...")

    # Fetch data
    raw_fsub = await get_variable("F_sub", "-1002374561133 -1002252580234 -1002359972599")
    FORCE_SUB_CHANNELS = [int(x.strip()) for x in raw_fsub.split() if x.strip()]

    raw_rsub = await get_variable("r_sub", "")
    rsub_channels = []
    if raw_rsub:
        for entry in raw_rsub.split(","):
            entry = entry.strip()
            if entry and "||" in entry:
                try:
                    cid, link = entry.split("||")
                    rsub_channels.append((int(cid), link.strip()))
                except ValueError:
                    continue

    # Build Text
    fsub_text = "<blockquote>⚜ 𝐅𝐨𝐫𝐜𝐞 𝐒𝐮𝐛 𝐒𝐞𝐭𝐭𝐢𝐧𝐠𝐬 ♻️</blockquote>\n"

    # Normal Fsub Section
    fsub_text += "<blockquote expandable>┏━━━•❅•°•❈ 𝐍𝐨𝐫𝐦𝐚𝐥 𝐅𝐬𝐮𝐛 •°•❅•━━┓\n\n"
    owner_ids = await get_variable("owner", [])
    if isinstance(owner_ids, str):
         # Just in case it's stored as string
         owner_ids = [int(x) for x in owner_ids.split() if x.strip()]

    for index, channel_id in enumerate(FORCE_SUB_CHANNELS, start=1):
        try:
            chat = await client.get_chat(channel_id)
            fsub_text += (
                f"{index}. {chat.title}\n"
                f"   ├─ Total Subscribers: {chat.members_count}\n"
                f"   └─ ID: <code>{channel_id}</code>\n\n"
            )
        except Exception:
             fsub_text += f"{index}. ❌ Cannot access channel (ID: <code>{channel_id}</code>)\n"

    fsub_text += "┗━━━━━━━━━━━━━━━━━━━━━┛</blockquote>\n"

    # Request Sub Section
    fsub_text += "<blockquote expandable>┏━━━•❅•°•❈ 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐅𝐬𝐮𝐛 •°•❅•━━┓\n\n"
    for index, (channel_id, link) in enumerate(rsub_channels, start=1):
        req_count = await get_variable(f"req{link}", 0)
        clean_link = re.sub(r"^https://", "", link)
        try:
            chat = await client.get_chat(channel_id)
            fsub_text += (
                f"{index}. {chat.title}\n"
                f"   ├─ Total Subscribers: {chat.members_count}\n"
                f"   ├─ ID: <code>{channel_id}</code>\n"
                f"   ├─ Link: <code>{clean_link}</code>\n"
                f"   └─ Requests: {req_count}\n\n"
            )
        except Exception:
             fsub_text += f"{index}. ❌ Cannot access channel (ID: <code>{channel_id}</code>)\n"

    fsub_text += "┗━━━━━━━━━━━━━━━━━━━━━┛</blockquote>\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("𝐀𝐃𝐃 𝐅𝐒𝐔𝐁", callback_data="fsub_add"),
            InlineKeyboardButton("𝐑𝐄𝐌𝐎𝐕𝐄 𝐅𝐒𝐔𝐁", callback_data="fsub_rem"),
        ],
        [
            InlineKeyboardButton("𝐀𝐃𝐃 𝐑𝐒𝐔𝐁", callback_data="rsub_add"),
            InlineKeyboardButton("𝐑𝐄𝐌𝐎𝐕𝐄 𝐑𝐒𝐔𝐁", callback_data="rsub_rem"),
        ],
        [
            InlineKeyboardButton("ϲℓοѕє", callback_data="close"),
        ],
    ])

    await status_msg.delete()
    await message.reply_photo(
        photo="https://i.ibb.co/YBLs424Q/x.jpg",
        caption=fsub_text,
        reply_markup=keyboard,
    )


async def listen_for_target_channel(client, user_id, prompt_msg):
    """
    Helper to listen for a forwarded message or ID from the user.
    Returns (chat_id, message_object, error_text)
    """
    txt = (
        "<blockquote expandable>⚠️ <b>𝖣𝗈 𝖮𝗇𝖾 𝖡𝖾𝗅𝗈𝗐</b>  ⚠️</blockquote>\n"
        "<blockquote expandable><i>🔱 𝖥𝗈𝗋𝗐𝖺𝗋𝖽 𝖠 𝖬𝖾𝗌𝗌𝖺𝗀𝖾 𝖥𝗋𝗈𝗆 𝖳𝖺𝗋𝗀𝖾𝗍 𝖢𝗁𝖺𝗇𝗇𝖾𝗅</i></blockquote>\n"
        "<blockquote expandable><i>💠 𝖲𝖾𝗇𝖽 𝖬𝖾 𝖳𝖺𝗋𝗀𝖾𝗍 𝖢𝗁𝖺𝗇𝗇𝖾𝗅 𝖨𝖽</i></blockquote>"
        "<blockquote>♨️ 𝗠𝗔𝗞𝗘 𝗦𝗨𝗥𝗘 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗗𝗠𝗜𝗡  ♨️</blockquote>"
    )

    prompt = await client.send_message(
        user_id,
        text=txt,
        reply_markup=ReplyKeyboardMarkup(
            [["❌ Cancel"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    try:
        response = await client.listen(user_id=user_id, timeout=30, chat_id=user_id)
    except ListenerTimeout:
        await client.send_message(user_id, "⏳ Timeout!", reply_markup=ReplyKeyboardRemove())
        await prompt.delete()
        return None, None, "TIMEOUT"

    if response.text and response.text.lower() == "❌ cancel":
        await client.send_message(user_id, "❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
        await prompt.delete()
        return None, None, "CANCELLED"

    target_chat_id = None

    if response.forward_from_chat:
        target_chat_id = response.forward_from_chat.id
    elif response.text:
        try:
            target_chat_id = int(response.text.strip())
        except ValueError:
            pass

    await prompt.delete()

    if not target_chat_id:
         await client.send_message(user_id, "❌ Invalid input. Please forward channel message or send ID.", reply_markup=ReplyKeyboardRemove())
         return None, None, "INVALID"

    return target_chat_id, response, None

async def verify_admin_status(client, channel_id, user_id, check_invite_perm=False):
    """
    Verifies bot is admin and has permissions.
    """
    try:
        member = await client.get_chat_member(channel_id, "me")
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await client.send_message(user_id, f"❌ I am not admin in {channel_id}. Please promote me.", reply_markup=ReplyKeyboardRemove())
            return False, member

        if check_invite_perm and not member.privileges.can_invite_users:
             await client.send_message(user_id, f"❌ I need 'Invite Users' permission in {channel_id}.", reply_markup=ReplyKeyboardRemove())
             return False, member

        return True, member
    except Exception as e:
        await client.send_message(user_id, f"❌ Error checking status in {channel_id}: {e}", reply_markup=ReplyKeyboardRemove())
        return False, None


async def fsub_handler(client, query, mode):
    """
    Generic handler for all fsub actions.
    mode: 'add_fsub', 'rem_fsub', 'add_rsub', 'rem_rsub'
    """
    uid = query.from_user.id

    # Auth check
    admin_str = await get_variable("owner", "-1002374561133 -1002252580234 -1002359972599 5426061889")
    admins = [int(x.strip()) for x in admin_str.split() if x.strip()]

    if uid not in admins:
         await query.answer("❌ You are not authorized.", show_alert=True)
         return

    await query.message.delete() # Clean up menu

    while True:
        chat_id, response_msg, error = await listen_for_target_channel(client, uid, query.message)
        if error:
            break # Exit loop

        # For Add operations, we need to verify bot is admin
        if mode in ['add_fsub', 'add_rsub']:
            is_valid, _ = await verify_admin_status(client, chat_id, uid, check_invite_perm=(mode=='add_rsub'))
            if not is_valid:
                continue # Ask again

        # Perform Action
        if mode == 'add_fsub':
            # Logic for adding normal fsub
            raw = await get_variable("F_sub", "-1002374561133 -1002252580234 -1002359972599")
            current_ids = [int(x.strip()) for x in raw.split() if x.strip()]

            if chat_id in current_ids:
                await client.send_message(uid, "❌ Already in Fsub list.", reply_markup=ReplyKeyboardRemove())
            else:
                current_ids.append(chat_id)
                new_str = " ".join(map(str, current_ids))
                await set_variable("F_sub", new_str)
                FSUB_CACHE['last_updated'] = 0 # Invalidate cache
                await client.send_message(uid, "✅ Fsub Added Successfully!", reply_markup=ReplyKeyboardRemove())
                break

        elif mode == 'rem_fsub':
             # Logic for removing normal fsub
            raw = await get_variable("F_sub", "")
            current_ids = [int(x.strip()) for x in raw.split() if x.strip()]

            if chat_id not in current_ids:
                await client.send_message(uid, "❌ Not in Fsub list.", reply_markup=ReplyKeyboardRemove())
            else:
                current_ids.remove(chat_id)
                new_str = " ".join(map(str, current_ids))
                await set_variable("F_sub", new_str)
                FSUB_CACHE['last_updated'] = 0 # Invalidate cache
                await client.send_message(uid, "✅ Fsub Removed Successfully!", reply_markup=ReplyKeyboardRemove())
                break

        elif mode == 'add_rsub':
            # Logic for adding request sub
            # Must check if already exists
            raw = await get_variable("r_sub", "")
            if f"{chat_id}||" in raw:
                 await client.send_message(uid, "❌ Already in Rsub list.", reply_markup=ReplyKeyboardRemove())
                 continue

            # Check public
            try:
                chat = await client.get_chat(chat_id)
                if chat.username:
                    await client.send_message(uid, "❌ Public channels cannot be used for Request Sub (Rsub).\nRsub is for forcing users to send Join Request.", reply_markup=ReplyKeyboardRemove())
                    continue
            except Exception:
                pass

            # Create Link
            try:
                # invites must have creates_join_request=True
                invite = await client.create_chat_invite_link(chat_id, creates_join_request=True)
                new_entry = f"{chat_id}||{invite.invite_link}"

                # Update r_sub string
                new_raw = f"{raw},{new_entry}" if raw else new_entry
                await set_variable("r_sub", new_raw)

                # Initialize tracking list
                req_links = await get_variable("req_link", [])
                req_links.append(invite.invite_link)
                await set_variable("req_link", req_links)

                await client.send_message(uid, "✅ Rsub Added Successfully!", reply_markup=ReplyKeyboardRemove())
                break
            except Exception as e:
                await client.send_message(uid, f"❌ Error creating link: {e}", reply_markup=ReplyKeyboardRemove())

        elif mode == 'rem_rsub':
            # Logic for removing rsub
            raw = await get_variable("r_sub", "")
            entries = [x.strip() for x in raw.split(",") if x.strip()]
            found = False
            new_entries = []
            removed_link = None

            for entry in entries:
                if entry.startswith(f"{chat_id}||"):
                    found = True
                    removed_link = entry.split("||")[1]
                else:
                    new_entries.append(entry)

            if not found:
                 await client.send_message(uid, "❌ Not in Rsub list.", reply_markup=ReplyKeyboardRemove())
            else:
                await set_variable("r_sub", ",".join(new_entries))
                if removed_link:
                    # Cleanup
                    await set_variable(removed_link, None)
                    await set_variable(f"req{removed_link}", 0)
                    req_links = await get_variable("req_link", [])
                    if removed_link in req_links:
                        req_links.remove(removed_link)
                        await set_variable("req_link", req_links)

                await client.send_message(uid, "✅ Rsub Removed Successfully!", reply_markup=ReplyKeyboardRemove())
                break

    # Return to menu
    await fsub1(client, query.message)


# Entry points mapping (aliases to match existing callback data if needed, or update callback data)
# Existing used callbacks: fsub_add, fsub_rem, rsub_add, rsub_rem

@Client.on_callback_query(filters.regex(r"^fsub_add$"))
async def fsub2(client, query):
    await fsub_handler(client, query, 'add_fsub')

@Client.on_callback_query(filters.regex(r"^fsub_rem$"))
async def fsub3(client, query):
    await fsub_handler(client, query, 'rem_fsub')

@Client.on_callback_query(filters.regex(r"^rsub_add$"))
async def fsub4(client, query):
    await fsub_handler(client, query, 'add_rsub')

@Client.on_callback_query(filters.regex(r"^rsub_rem$"))
async def fsub5(client, query):
    await fsub_handler(client, query, 'rem_rsub')
