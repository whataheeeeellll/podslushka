import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

TOKEN = "8592428729:AAFn7KK5Ixp5y02rfMXgBr34fL9BNe2GD5E"
CHANNEL_ID = -1003856412254  # ID канала
MODERATORS = {7991967172, 1811346319}     # ID модераторов

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====== Стейты ======
user_state = {}
posts = {}
post_id = 0

# ====== Клавиатуры ======
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📝 Новый пост")]],
    resize_keyboard=True
)
anon_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🎭 Анонимно")],[KeyboardButton(text="👤 Не анонимно")]],
    resize_keyboard=True
)
confirm_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Подтвердить")],[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# ====== START ======
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 <b>Подслушано бот</b>\n\n📝 Нажми «Новый пост», чтобы создать запись",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb
    )

# ====== Новый пост ======
@dp.message(F.text == "📝 Новый пост")
async def new_post(message: Message):
    user_state[message.from_user.id] = {"step": "content"}
    await message.answer("📨 Отправь пост (текст / фото / видео / файл)")

# ====== Хендлер универсальный ======
@dp.message()
async def handler(message: Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    state = user_state[uid]

    # 1. Контент
    if state["step"] == "content":
        state["msg"] = message
        state["step"] = "anon"
        await message.answer("❓ Пост анонимный?", reply_markup=anon_kb)

    # 2. Анонимность
    elif state["step"] == "anon":
        state["anon"] = (message.text == "🎭 Анонимно")
        state["step"] = "confirm"
        await message.answer("❗ Подтвердить отправку?", reply_markup=confirm_kb)

    # 3. Подтверждение
    elif state["step"] == "confirm":
        if message.text == "❌ Отмена":
            user_state.pop(uid, None)
            await message.answer("❌ Отменено", reply_markup=main_kb)
            return
        if message.text == "✅ Подтвердить":
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
            await message.answer("📨 <b>Отправка подтверждена</b>\n⏳ Ожидайте модерации...", parse_mode=ParseMode.HTML, reply_markup=main_kb)
            await send_to_mods(post_id)
            user_state.pop(uid, None)

# ====== Отправка модераторам ======
async def send_to_mods(pid: int):
    data = posts[pid]
    msg = data["msg"]

    if data["anon"]:
        author_text = "👤 Автор: Аноним"
    else:
        u = data["author"]
        username = f"@{u.username}" if u.username else "без username"
        author_text = f"👤 Автор: {u.full_name} ({username})"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=author_text, callback_data="noop")],
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"ok_{pid}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no_{pid}")
        ]
    ])

    for mod in MODERATORS:
        m1 = await bot.copy_message(chat_id=mod, from_chat_id=msg.chat.id, message_id=msg.message_id)
        m2 = await bot.send_message(mod, "👀 Модерация поста", reply_markup=kb)
        posts[pid]["mods"].append((mod, m1.message_id, m2.message_id))

# ====== Проверка ======
def closed(pid):
    return posts.get(pid, {}).get("status") != "pending"

# ====== Принять ======
@dp.callback_query(F.data.startswith("ok_"))
async def accept(call: CallbackQuery):
    pid = int(call.data.split("_")[1])
    data = posts.get(pid)
    if not data or closed(pid):
        await call.answer("Уже обработано ❌", show_alert=True)
        return
    data["status"] = "accepted"
    msg = data["msg"]

    if data["anon"]:
        author_text = "👤 Автор: Аноним"
    else:
        u = data["author"]
        username = f"@{u.username}" if u.username else "без username"
        author_text = f"👤 Автор: {u.full_name} ({username})"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=author_text, callback_data="noop")]])
    await bot.copy_message(chat_id=CHANNEL_ID, from_chat_id=msg.chat.id, message_id=msg.message_id, reply_markup=kb)
    await bot.send_message(data["user_id"], "✅ Пост прошёл модерацию и опубликован!")

    # Очистка модераторов
    for mod, msg_id, text_id in data["mods"]:
        try:
            await bot.delete_message(mod, msg_id)
            await bot.delete_message(mod, text_id)
        except:
            pass

    await call.message.delete()
    await call.answer("Принято")

# ====== Отклонить ======
@dp.callback_query(F.data.startswith("no_"))
async def reject(call: CallbackQuery):
    pid = int(call.data.split("_")[1])
    data = posts.get(pid)
    if not data or closed(pid):
        await call.answer("Уже обработано ❌", show_alert=True)
        return
    data["status"] = "rejected"
    await bot.send_message(data["user_id"], "❌ Пост прошёл модерацию и не был опубликован!")

    for mod, msg_id, text_id in data["mods"]:
        try:
            await bot.delete_message(mod, msg_id)
            await bot.delete_message(mod, text_id)
        except:
            pass

    await call.message.delete()
    await call.answer("Отклонено")

# ====== “Ничего не делать” для кнопки автора ======
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()  # просто заглушка

# ====== RUN ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())