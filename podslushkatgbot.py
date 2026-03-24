import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

# ====== ЛОГИ ======
logging.basicConfig(level=logging.INFO)

TOKEN = "8592428729:AAHMWz-Mn7EhpAeKJ3sy5xVDM_esoUwucxA"
CHANNEL_ID = -1003856412254
MODERATORS = {7991967172}

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====== СТАН ======
user_state = {}
posts = {}
post_id = 0

# ====== КЛАВІАТУРИ ======
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📝 Новий пост")]],
    resize_keyboard=True
)

anon_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎭 Анонімно")],
        [KeyboardButton(text="👤 Не анонімно")]
    ],
    resize_keyboard=True
)

confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Підтвердити")],
        [KeyboardButton(text="❌ Скасувати")]
    ],
    resize_keyboard=True
)

# ====== ДОСТУП ======
async def check_access(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning(f"Access error: {e}")
        return False

# ====== START ======
@dp.message(CommandStart())
async def start(message: Message):
    if not await check_access(message.from_user.id):
        await message.answer("🚫 Немає доступу до каналу")
        return

    await message.answer(
        "👋 <b>Бот «Підслухано»</b>\n📝 Натисни «Новий пост»",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb
    )

# ====== НОВИЙ ПОСТ ======
@dp.message(F.text == "📝 Новий пост")
async def new_post(message: Message):
    if not await check_access(message.from_user.id):
        return

    user_state[message.from_user.id] = {"step": "content"}
    await message.answer("📨 Надішли пост (текст, фото, відео тощо)")

# ====== ОСНОВНИЙ ХЕНДЛЕР ======
@dp.message()
async def handler(message: Message):
    try:
        if not message.from_user:
            return

        uid = message.from_user.id
        if not await check_access(uid):
            return
        if uid not in user_state:
            return

        state = user_state[uid]

        # 1. Контент
        if state["step"] == "content":
            state["msg"] = message
            state["step"] = "anon"
            await message.answer("❓ Опублікувати анонімно?", reply_markup=anon_kb)

        # 2. Анонімність
        elif state["step"] == "anon":
            if not message.text:
                return
            state["anon"] = (message.text == "🎭 Анонімно")
            state["step"] = "confirm"
            await message.answer("❗ Підтвердити публікацію?", reply_markup=confirm_kb)

        # 3. Підтвердження
        elif state["step"] == "confirm":
            if message.text == "❌ Скасувати":
                user_state.pop(uid, None)
                await message.answer("❌ Скасовано", reply_markup=main_kb)
                return
            if message.text == "✅ Підтвердити":
                global post_id
                post_id += 1
                posts[post_id] = {
                    "msg": state["msg"],
                    "anon": state["anon"],
                    "author": message.from_user,
                    "user_id": uid,
                    "status": "pending",
                    "mods": []
                }
                await message.answer("📨 Пост відправлено на модерацію", reply_markup=main_kb)
                await send_to_mods(post_id)
                user_state.pop(uid, None)
    except Exception as e:
        logging.error(f"Handler error: {e}")

# ====== МОДЕРАЦІЯ ======
async def send_to_mods(pid: int):
    try:
        data = posts[pid]
        msg = data["msg"]

        u = data["author"]
        username = f"@{u.username}" if u.username else "без username"

        # На этапе модерации аноним → виден юзернейм
        if data["anon"]:
            author_text = f"👤 Анонім ({username})"
        else:
            author_text = f"👤 {u.full_name} ({username})"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=author_text, callback_data="noop")],
            [
                InlineKeyboardButton(text="✅ Прийняти", callback_data=f"ok_{pid}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"no_{pid}")
            ]
        ])

        for mod in MODERATORS:
            try:
                m1 = await bot.copy_message(mod, msg.chat.id, msg.message_id)
                m2 = await bot.send_message(mod, "👀 Модерація поста", reply_markup=kb)
                posts[pid]["mods"].append((mod, m1.message_id, m2.message_id))
            except Exception as e:
                logging.warning(f"Mod send error: {e}")
    except Exception as e:
        logging.error(f"send_to_mods error: {e}")

# ====== ПРИЙНЯТИ ======
@dp.callback_query(F.data.startswith("ok_"))
async def accept(call: CallbackQuery):
    try:
        pid = int(call.data.split("_")[1])
        data = posts.get(pid)
        if not data or data["status"] != "pending":
            await call.answer("Вже оброблено")
            return
        data["status"] = "accepted"
        msg = data["msg"]

        # В канале аноним → просто "Анонім"
        if data["anon"]:
            author_text = "Анонім"
        else:
            u = data["author"]
            username = f"@{u.username}" if u.username else "без username"
            author_text = f"{u.full_name} ({username})"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=author_text, callback_data="noop")]]
        )

        await bot.copy_message(CHANNEL_ID, msg.chat.id, msg.message_id, reply_markup=kb)
        await bot.send_message(data["user_id"], "✅ Пост опубліковано!")

        for mod, m1, m2 in data["mods"]:
            try:
                await bot.delete_message(mod, m1)
                await bot.delete_message(mod, m2)
            except:
                pass

        await call.message.delete()
        await call.answer("Прийнято")
    except Exception as e:
        logging.error(f"Accept error: {e}")

# ====== ВІДХИЛИТИ ======
@dp.callback_query(F.data.startswith("no_"))
async def reject(call: CallbackQuery):
    try:
        pid = int(call.data.split("_")[1])
        data = posts.get(pid)
        if not data or data["status"] != "pending":
            await call.answer("Вже оброблено")
            return
        data["status"] = "rejected"
        await bot.send_message(data["user_id"], "❌ Ваш пост відхилено")
        for mod, m1, m2 in data["mods"]:
            try:
                await bot.delete_message(mod, m1)
                await bot.delete_message(mod, m2)
            except:
                pass
        await call.message.delete()
        await call.answer("Відхилено")
    except Exception as e:
        logging.error(f"Reject error: {e}")

# ====== NOOP ======
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()

# ====== MAIN LOOP ======
async def main():
    while True:
        try:
            logging.info("Бот запущено")
            await dp.start_polling(bot, skip_updates=True)
        except Exception as e:
            logging.error(f"BOT CRASHED: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
