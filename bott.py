import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
# Конфигурация бота
API_TOKEN = "7172003076:AAH9csf6FrFa0jj4M2V0wrjwI5nMJl2WdXM"
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Путь к базе данных
DB_PATH = "bot_db.db"

# --- Работа с базой данных ---

def get_connection():
    """Устанавливает соединение с базой данных."""
    return sqlite3.connect(DB_PATH)

def initialize_database():
    """Создает таблицы пользователей и команд, если они не существуют."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Таблица пользователей
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            role TEXT CHECK (role IN ('Руководитель', 'Участник')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Таблица команд
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Teams (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            leader_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (leader_id) REFERENCES Users(id)
        );
        """)
        # Таблица участников команд
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS TeamMembers (
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (team_id) REFERENCES Teams(id),
            FOREIGN KEY (user_id) REFERENCES Users(id),
            PRIMARY KEY (team_id, user_id)
        );
        """)
        conn.commit()
        print("База данных инициализирована.")


def add_user(user_id, username, role):
    """Добавляет пользователя в базу данных."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Users (id, username, role) VALUES (?, ?, ?)",
            (user_id, username, role)
        )
        conn.commit()

def is_user_registered(user_id):
    """Проверяет, зарегистрирован ли пользователь."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Users WHERE id = ?", (user_id,))
        return cursor.fetchone() is not None

def add_team(leader_id, team_name):
    """Создает команду."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Teams (name, leader_id) VALUES (?, ?)",
            (team_name, leader_id)
        )
        conn.commit()

def get_teams_by_leader(leader_id):
    """Получает все команды, принадлежащие руководителю."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM Teams WHERE leader_id = ?", (leader_id,))
        return cursor.fetchall()

def add_member_to_team(team_id, user_id):
    """Добавляет участника в команду."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO TeamMembers (team_id, user_id) VALUES (?, ?)",
            (team_id, user_id)
        )
        conn.commit()

def remove_member_from_team(team_id, user_id):
    """Удаляет участника из команды."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM TeamMembers WHERE team_id = ? AND user_id = ?",
            (team_id, user_id)
        )
        conn.commit()

# --- Логика бота ---

# Генерация клавиатуры для выбора роли
def get_role_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("Руководитель"))
    keyboard.add(KeyboardButton("Участник"))
    return keyboard

# Генерация клавиатуры для команд
def get_team_keyboard(teams):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for team in teams:
        keyboard.add(KeyboardButton(team[1]))  # Название команды
    return keyboard

# Генерация клавиатуры для команды
def get_team_actions_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("Создать команду"))
    keyboard.add(KeyboardButton("Мои команды"))
    return keyboard

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username

    if not is_user_registered(user_id):
        # Предлагаем пользователю выбрать роль
        await message.answer(
            "Добро пожаловать! Выберите свою роль:",
            reply_markup=get_role_keyboard()
        )
    else:
        await message.answer("Вы уже зарегистрированы!")

@dp.message_handler(lambda message: message.text in ["Руководитель", "Участник"])
async def handle_role_selection(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    role = message.text

    if not is_user_registered(user_id):
        # Сохраняем данные пользователя в базу
        add_user(user_id, username, role)
        await message.answer(f"Вы успешно зарегистрированы как {role}.")
    else:
        await message.answer("Вы уже зарегистрированы. Если вам нужно изменить роль, обратитесь к администратору.")

@dp.message_handler(lambda message: message.text == "Возможности")
async def show_leader_menu(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_team_actions_keyboard())

##################################################################################################################

@dp.message_handler(lambda message: message.text == "Создать команду")
async def create_team(message: types.Message):
    # Запросим название команды у руководителя
    await message.answer("Введите название команды:")

    # Сохраняем шаг в контексте
    await dp.current_state(user=message.from_user.id).set_state("awaiting_team_name")

@dp.message_handler(state="awaiting_team_name")
async def process_team_name(message: types.Message, state: FSMContext):
    team_name = message.text
    leader_id = message.from_user.id

    # Проверяем, не существует ли уже такая команда
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Teams WHERE name = ?", (team_name,))
        if cursor.fetchone():
            await message.answer("Команда с таким названием уже существует. Попробуйте другое.")
            return
    
    # Создаем команду
    add_team(leader_id, team_name)
    await message.answer(f"Команда '{team_name}' успешно создана!")

    # Завершаем шаг
    await state.finish()
#############################################################################################################

# Функция отправки утреннего уведомления для голосования
def send_morning_notifications():
    users = session.query(User).all()
    for user in users:
        if user.role == Role.EMPLOYEE:
            send_vote_request(user.telegram_id)

# Функция запуска планировщика в отдельном потоке
def run_scheduler():
    schedule.every().day.at("09:00").do(send_morning_notifications)  # Уведомление в 9:00 утра
    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск планировщика в отдельном потоке
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()


#############################################################################################################

# Генерация клавиатуры для выбора действий с командой
def get_team_management_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("Добавить участника"))
    keyboard.add(KeyboardButton("Удалить участника"))
    return keyboard

class Form(StatesGroup):
    awaiting_role = State()  # Состояние для выбора роли
    awaiting_team_name = State()  # Состояние для создания команды
    awaiting_member_selection = State()  # Состояние для выбора действия с участниками
    awaiting_member_username = State()  # Состояние для ввода username участника
    awaiting_team_action = State()


@dp.message_handler(lambda message: message.text == "Мои команды")
async def show_teams(message: types.Message):
    leader_id = message.from_user.id
    teams = get_teams_by_leader(leader_id)

    if teams:
        await message.answer("Выберите команду:", reply_markup=get_team_keyboard(teams))
        await Form.awaiting_team_action.set()
    else:
        await message.answer("У вас еще нет команд. Создайте команду.")

@dp.message_handler(state=Form.awaiting_team_action)
async def team_action(message: types.Message, state: FSMContext):
    team_name = message.text
    leader_id = message.from_user.id

    # Получаем ID выбранной команды
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Teams WHERE name = ? AND leader_id = ?", (team_name, leader_id))
        team = cursor.fetchone()

    if team:
        team_id = team[0]
        await message.answer("Выберите действие:", reply_markup=get_team_management_keyboard())
        await state.update_data(team_id=team_id)
        await Form.awaiting_member_selection.set()
    else:
        await message.answer("Вы не являетесь руководителем этой команды.")


@dp.message_handler(lambda message: message.text in ["Добавить участника", "Удалить участника"], state=Form.awaiting_member_selection)
async def manage_members(message: types.Message, state: FSMContext):
    # Получаем team_id из состояния
    data = await state.get_data()
    team_id = data.get("team_id")

    # Если пользователь выбирает "Добавить участника", запрашиваем username
    if message.text == "Добавить участника":
        await message.answer("Введите username пользователя для добавления в команду:")
        await Form.awaiting_member_username.set()  # Переходим в состояние для ввода username

    # Если пользователь выбирает "Удалить участника", выводим список участников
    elif message.text == "Удалить участника":
        # Получаем список участников
        members = get_team_members(team_id)
        if members:
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for member in members:
                user_id = member[0]
                cursor = get_connection().cursor()
                cursor.execute("SELECT username FROM Users WHERE id = ?", (user_id,))
                username = cursor.fetchone()[0]
                keyboard.add(KeyboardButton(username))
            await message.answer("Выберите участника для удаления:", reply_markup=keyboard)
            await Form.awaiting_member_username.set()  # Переходим к состоянию для удаления участника
        else:
            await message.answer("В вашей команде нет участников.")

# Обрабатываем ввод username для добавления или удаления участника
@dp.message_handler(state=Form.awaiting_member_username)
async def process_member_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    team_id = data.get("team_id")
    username = message.text.strip()  # Получаем введенный username

    if not username:
        await message.answer("Пожалуйста, введите username участника.")
        return

    try:
        # Проверяем, существует ли пользователь с таким username
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Users WHERE username = ?", (username,))
            user = cursor.fetchone()

        if user:
            user_id = user[0]

            if message.text == "Добавить участника":
                # Проверяем, является ли пользователь уже участником команды
                cursor.execute("SELECT 1 FROM TeamMembers WHERE team_id = ? AND user_id = ?", (team_id, user_id))
                member_exists = cursor.fetchone()

                if member_exists:
                    await message.answer(f"Пользователь {username} уже является участником этой команды.")
                else:
                    # Добавляем участника в команду
                    add_member_to_team(team_id, user_id)
                    await message.answer(f"Пользователь {username} успешно добавлен в команду.")

            elif message.text == "Удалить участника":
                # Проверяем, является ли пользователь участником команды
                cursor.execute("SELECT 1 FROM TeamMembers WHERE team_id = ? AND user_id = ?", (team_id, user_id))
                member_exists = cursor.fetchone()

                if member_exists:
                    # Удаляем участника из команды
                    remove_member_from_team(team_id, user_id)
                    await message.answer(f"Пользователь {username} успешно удален из команды.")
                else:
                    await message.answer(f"{username} не является участником этой команды.")
        else:
            await message.answer("Пользователь с таким username не найден.")
    except Exception as e:
        await message.answer(f"Произошла ошибка: {e}")

    await state.finish()

# --- Запуск бота ---
if __name__ == "__main__":
    initialize_database()  # Инициализация базы данных
    executor.start_polling(dp, skip_updates=True)
