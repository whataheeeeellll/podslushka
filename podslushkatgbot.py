import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

TOKEN = "8592428729:AAFn7KK5Ixp5y02rfMXgBr34fL9BNe2GD5E"
CHANNEL_ID = -1003856412254
MODERATORS = {7991967172, 1811346319}

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====== STATE ======
user_state = {}
posts = {}
post_id = 0

# ====== КЛАВИАТУРЫ ======
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
        [KeyboardButton(text="❌ Відміна")]
    ],
    resize_keyboard=True
)

# ====== ДОСТУП К КАНАЛУ ======
async def check_access(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


# ====== START ======
@dp.message(CommandStart())
async def start(message: Message):
    if not await check_access(message.from_user.id):
        await message.answer("🚫 Немає доступа")
        return

    await message.answer(
        "👋 <b>Подслушано бот</b>\n📝 Нажми «Новий пост»",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb
    )


# ====== НОВЫЙ ПОСТ ======
@dp.message(F.text == "📝 Новый пост")
async def new_post(message: Message):
    if not await check_access(message.from_user.id):
        await message.answer("🚫 Немає доступа")
        return

    user_state[message.from_user.id] = {"step": "content"}
    await message.answer("📨 Відправ пост (фото, відео, т. д.)")


# ====== ОБЩИЙ ХЕНДЛЕР ======
@dp.message()
async def handler(message: Message):
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
        await message.answer("❓ Анонімний пост?", reply_markup=anon_kb)

    # 2. Анонимность
    elif state["step"] == "anon":
        state["anon"] = (message.text == "🎭 Анонімно")
        state["step"] = "confirm"
        await message.answer("❗ Підтвердити відправку?", reply_markup=confirm_kb)

    # 3. Подтверждение
    elif state["step"] == "confirm":

        if message.text == "❌ Відмінити":
            user_state.pop(uid, None)
            await message.answer("❌ Відмінено", reply_markup=main_kb)
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

            await message.answer(
                "📨 Відправка підтвержена\n⏳ Чекайте на рішення модерації",
                reply_markup=main_kb
            )

            await send_to_mods(post_id)
            user_state.pop(uid, None)


# ====== ОТПРАВКА МОДЕРАЦИИ ======
async def send_to_mods(pid: int):
    data = posts[pid]
    msg = data["msg"]

    if data["anon"]:
        author_text = "👤 Аноним"
    else:
        u = data["author"]
        username = f"@{u.username}" if u.username else "без username"
        author_text = f"{u.full_name} ({username})"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👤 {author_text}", callback_data="noop")],
        [
            InlineKeyboardButton(text="✅ Приняти", callback_data=f"ok_{pid}"),
            InlineKeyboardButton(text="❌ Відклонити", callback_data=f"no_{pid}")
        ]
    ])

    for mod in MODERATORS:
        m1 = await bot.copy_message(mod, msg.chat.id, msg.message_id)
        m2 = await bot.send_message(mod, "👀 Модерация", reply_markup=kb)
        posts[pid]["mods"].append((mod, m1.message_id, m2.message_id))


# ====== ПРОВЕРКА ======
def is_closed(pid):
    return posts.get(pid, {}).get("status") != "pending"


# ====== ПРИНЯТЬ ======
@dp.callback_query(F.data.startswith("ok_"))
async def accept(call: CallbackQuery):
    if not await check_access(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    pid = int(call.data.split("_")[1])
    data = posts.get(pid)

    if not data or is_closed(pid):
        await call.answer("Вже опрацьовано")
        return

    data["status"] = "accepted"
    msg = data["msg"]

    if data["anon"]:
        author_text = "👤 Аноним"
    else:
        u = data["author"]
        username = f"@{u.username}" if u.username else "без username"
        author_text = f"{u.full_name} ({username})"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=author_text, callback_data="noop")]]
    )

    await bot.copy_message(CHANNEL_ID, msg.chat.id, msg.message_id, reply_markup=kb)
    await bot.send_message(data["user_id"], "✅ Пост опублікований!")

    for mod, m1, m2 in data["mods"]:
        try:
            await bot.delete_message(mod, m1)
            await bot.delete_message(mod, m2)
        except:
            pass

    await call.message.delete()
    await call.answer("Прийнято")


# ====== ОТКЛОНИТЬ ======
@dp.callback_query(F.data.startswith("no_"))
async def reject(call: CallbackQuery):
    if not await check_access(call.from_user.id):
        await call.answer("Немає доступа", show_alert=True)
        return

    pid = int(call.data.split("_")[1])
    data = posts.get(pid)

    if not data or is_closed(pid):
        await call.answer("Вже опрацьовано")
        return

    data["status"] = "rejected"

    await bot.send_message(data["user_id"], "❌ Пост відклонений")

    for mod, m1, m2 in data["mods"]:
        try:
            await bot.delete_message(mod, m1)
            await bot.delete_message(mod, m2)
        except:
            pass

    await call.message.delete()
    await call.answer("Відхилено")


# ====== CALLBACK ЗАГЛУШКА ======
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ====== RUN ======
async def main():
    print("bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
