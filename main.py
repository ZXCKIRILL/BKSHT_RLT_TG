# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
"""Buckshot Roulette Telegram Bot"""
import logging
import asyncio
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

TOKEN = "7504881712:AAHe7X6SMzuZyuTkVpP3zaNgblEZ-B8dN6U"

bot = Bot(token=TOKEN)
dp = Dispatcher()

class GameState(StatesGroup):
    """Состояния игры"""
    gameplay = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "\nГотов?\n"
        "Правила:\n"
        "- В обойме боевой или холостой\n"
        "- Думаю, игра тебе уже ясна.\n"
        "- У каждого по 2 жизни\n"
        "- Кто последний дышит - забирает деньги. Удачи.\n"
        "- /startgame"
    )

@dp.message(Command("startgame"))
async def cmd_start_game(message: types.Message, state: FSMContext):
    """Начало новой игры"""
    await start_new_round(message, state)

async def start_new_round(message: types.Message, state: FSMContext):
    """Запускает новый раунд с новой загрузкой патронов"""
    count = random.randint(2, 6)
    live = count // 2
    blank = count - live
    bullets = [True] * live + [False] * blank
    random.shuffle(bullets)
    
    await state.update_data(
        bullets=bullets,
        current_index=0,
        player_hp=2,
        dealer_hp=2,
        current_turn=random.choice(["player", "dealer"]),
        live_count=live,
        blank_count=blank
    )
    
    data = await state.get_data()
    await message.answer(
        f"{count} патронов\n"
        f"Боевых: {data['live_count']}\n"
        f"Холостых: {data['blank_count']}\n"
        f"Первым ходит {data['current_turn'].capitalize()}!\n",
        reply_markup=get_game_keyboard()
    )
    await state.set_state(GameState.gameplay)
    await handle_turn(message, state)

def get_game_keyboard():
    """Создает игровую клавиатуру"""
    buttons = [
        KeyboardButton(text="РИСКНУТЬ"),
        KeyboardButton(text="УБИТЬ"),
    ]
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[buttons],
        one_time_keyboard=False
    )

async def handle_turn(message: types.Message, state: FSMContext):
    """Обрабатывает ход игрока или дилера"""
    data = await state.get_data()
    
    if data["current_turn"] == "dealer":
        await dealer_shot(message, state)
    else:
        await message.answer(
            "Твой черед:",
            reply_markup=get_game_keyboard()
        )

@dp.message(lambda message: message.text in ["РИСКНУТЬ", "УБИТЬ"])
async def handle_shot_buttons(message: types.Message, state: FSMContext):
    """Обработчик кнопок выстрела"""
    current_state = await state.get_state()
    if current_state != GameState.gameplay:
        await message.answer("⚠️ Сначала начните игру /startgame")
        return

    data = await state.get_data()
    if data["current_turn"] != "player":
        await message.answer("Сейчас не твой ход.")
        return

    new_turn_needed = True
    
    while True:
        data = await state.get_data()
        if data["current_index"] >= len(data["bullets"]):
            break
            
        bullet = data["bullets"][data["current_index"]]
        target = "self" if message.text == "РИСКНУТЬ" else "dealer"
        
        game_over = await process_bullet(message, state, bullet, target)
        if game_over:
            return
            
        # Проверяем возможность дополнительного хода
        if not bullet and target == "self":
            await message.answer("Повезло. В этот раз.")
            new_turn_needed = False
            # Автовыбор для доп хода
            message.text = "РИСКНУТЬ"  
        else:
            break
    
    if new_turn_needed:
        await switch_turn(message, state)

async def process_bullet(
    message: types.Message, 
    state: FSMContext, 
    bullet: bool, 
    target: str
) -> bool:
    """Обрабатывает результат выстрела"""
    data = await state.get_data()
    new_index = data["current_index"] + 1
    new_data = {**data, "current_index": new_index}
    
    if bullet:
        if target == "self":
            new_data["player_hp"] -= 1
            msg = "💥"
        else:
            new_data["dealer_hp"] -= 1
            msg = "💥"
    else:
        msg = "Щелчок. К счастью..." if target == "self" \
            else "Щелчок. Зараза..."
    
    await state.update_data(**new_data)
    await message.answer(
        f"{msg}\n"
        f"Сколько тебе осталось: {new_data['player_hp']}\n"
        f"Диллер: {new_data['dealer_hp']}"
    )
    
    return await check_winner(message, state)

async def dealer_shot(message: types.Message, state: FSMContext):
    """Обрабатывает ход дилера"""
    while True:
        data = await state.get_data()
        if data["current_index"] >= len(data["bullets"]):
            break
            
        bullet = data["bullets"][data["current_index"]]
        target = random.choice(["self", "player"])
        
        new_index = data["current_index"] + 1
        new_data = {**data, "current_index": new_index}
        
        if bullet:
            if target == "self":
                new_data["dealer_hp"] -= 1
                msg = "💥"
            else:
                new_data["player_hp"] -= 1
                msg = "💥"
        else:
            msg = f"Щелчок в {target.upper()} ..."
        
        await state.update_data(**new_data)
        await message.answer(
            f"{msg}\n"
            f"Сколько тебе осталось: {new_data['player_hp']}\n"
            f"Диллер: {new_data['dealer_hp']}"
        )
        
        if await check_winner(message, state):
            return
            
        # Если холостой в себя - продолжаем цикл
        if not bullet and target == "self":
            await message.answer("Он ходит снова...")
            await asyncio.sleep(1)
        else:
            break
    
    await switch_turn(message, state)

async def switch_turn(message: types.Message, state: FSMContext):
    """Переключает ход между игроком и дилером"""
    data = await state.get_data()
    new_turn = "dealer" if data["current_turn"] == "player" else "player"
    await state.update_data(current_turn=new_turn)
    await handle_turn(message, state)

async def check_winner(message: types.Message, state: FSMContext) -> bool:
    """Проверяет условия победы"""
    data = await state.get_data()
    
    player_dead = data["player_hp"] <= 0
    dealer_dead = data["dealer_hp"] <= 0
    
    if player_dead:
        await message.answer("Вы проснулись в темном месте. Пред вами лишь черные врата. Конец..?", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return True
    if dealer_dead:
        await message.answer("Вы первый кто смог. Вы выиграли. Конец.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return True

    # Проверка на окончание патронов
    data = await state.get_data()
    if data["current_index"] >= len(data["bullets"]):
        await message.answer("Магазин пуст. Вкалываем по морфину, и продолжим...")
        await start_new_round(message, state)
        return True

    return False


async def main():
    """Основная функция"""
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())