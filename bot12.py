import telebot
import json
import os
import sys
import time
import math
import requests
from telebot import types
from telebot.util import escape
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GISMETEO_TOKEN = os.environ.get('GISMETEO_API_TOKEN')

if not API_TOKEN:
    print("Критическая ошибка: Переменная окружения TELEGRAM_BOT_TOKEN не установлена.")
    sys.exit("Пожалуйста, установите переменную окружения TELEGRAM_BOT_TOKEN")
if not GISMETEO_TOKEN:
    print("Критическая ошибка: Переменная окружения GISMETEO_API_TOKEN не установлена.")
    sys.exit("Пожалуйста, установите переменную окружения GISMETEO_API_TOKEN")
print("Токены успешно загружены из переменных окружения.")

GISMETEO_API_WEATHER_CURRENT = 'https://api.gismeteo.net/v3/weather/current/'
DATA_FILE = 'user_tasks.json'
TASKS_PER_PAGE = 5
LAST_TASKS_COUNT = 10

def load_data():
    try:
        if not os.path.exists(DATA_FILE): return {}
        with open(DATA_FILE, 'r', encoding='utf-8') as f: content = f.read();
        if not content: return {}
        data = json.loads(content)
        if not isinstance(data, dict): print(f"Ошибка: Ожидалась структура dict в {DATA_FILE}, найдено {type(data)}."); return {}
        return data
    except json.JSONDecodeError: print(f"Ошибка декодирования JSON в файле {DATA_FILE}."); return {}
    except Exception as e: print(f"Неожиданная ошибка при загрузке данных: {e}"); return {}

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e: print(f"Ошибка сохранения данных в файл {DATA_FILE}: {e}")

def get_user_data(chat_id):
    global all_user_data
    chat_id_str = str(chat_id)
    if chat_id_str not in all_user_data or not isinstance(all_user_data[chat_id_str], dict) or \
            'tasks' not in all_user_data[chat_id_str] or 'next_id' not in all_user_data[chat_id_str]:
        all_user_data[chat_id_str] = {'tasks': [], 'next_id': 1}
    return all_user_data[chat_id_str]

def get_coordinates_by_city_name(city_name):
    try:
        geolocator = Nominatim(user_agent="my_telegram_task_weather_bot/1.0")
        location = geolocator.geocode(city_name, language='ru', timeout=10)
        if location:
            print(f"Геокодинг для '{city_name}': {location.latitude}, {location.longitude} ({location.address})")
            return location.latitude, location.longitude, location.address
        else:
            print(f"Геокодинг не нашел: '{city_name}'")
            return None, None, f"Не удалось найти координаты для города '{escape(city_name)}'."
    except GeocoderTimedOut: return None, None, "Сервис геокодинга не ответил вовремя."
    except GeocoderServiceError as e: return None, None, f"Ошибка сервиса геокодинга: {e}"
    except Exception as e: print(f"Неожиданная ошибка геокодинга '{city_name}': {e}"); return None, None, "Внутренняя ошибка поиска координат."

def get_weather_by_coords(latitude, longitude):
    if not GISMETEO_TOKEN: return None, "Токен API погоды не настроен."
    headers = {'X-Gismeteo-Token': GISMETEO_TOKEN, 'Accept-Encoding': 'gzip'}
    params = {'latitude': latitude, 'longitude': longitude, 'lang': 'ru'}
    url = GISMETEO_API_WEATHER_CURRENT
    print(f"Запрос погоды: URL={url}, Params={params}")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"Ответ API Gismeteo: Статус={response.status_code}")
        response.raise_for_status()
        data = response.json(); meta = data.get('meta', {})
        if meta.get('status_code') != 200 or meta.get('status') is False:
            error_detail = f"API Gismeteo ошибка (статус {meta.get('status_code')})"
            if 'errors' in meta and meta['errors']: error_detail += f": {meta['errors'][0].get('detail', 'Нет деталей')}"
            print(error_detail); return None, error_detail
        weather_data = data.get('data')
        if not weather_data: return None, "API Gismeteo вернул пустые данные о погоде."
        return weather_data, None
    except requests.exceptions.HTTPError as e:
        error_message = f"Ошибка получения погоды: {e.response.status_code}"
        try:
            error_data = e.response.json(); meta_error = error_data.get('meta', {}).get('errors', [])
            if meta_error: error_message += f" ({meta_error[0].get('detail', 'Нет деталей')})"
        except Exception: pass
        print(f"HTTP ошибка запроса Gismeteo: {e}"); return None, error_message
    except requests.exceptions.RequestException as e: print(f"Сетевая ошибка запроса Gismeteo: {e}"); return None, f"Сетевая ошибка: {e}"
    except Exception as e: print(f"Ошибка в get_weather_by_coords: {e}"); return None, "Внутренняя ошибка получения погоды."

def format_weather_message(weather_data, location_name):
    if not weather_data: return "Не удалось получить данные о погоде."
    try:
        temp_air = weather_data.get('temperature', {}).get('air', {}).get('C', 'н/д')
        temp_comfort = weather_data.get('temperature', {}).get('comfort', {}).get('C', 'н/д')
        description = weather_data.get('description', 'Нет описания')
        humidity = weather_data.get('humidity', {}).get('percent', 'н/д')
        pressure = weather_data.get('pressure', {}).get('mm_hg_atm', 'н/д')
        wind_speed = weather_data.get('wind', {}).get('speed', {}).get('m_s', 'н/д')
        wind_dir_code = weather_data.get('wind', {}).get('direction', {}).get('scale_8')
        cloud_perc = weather_data.get('cloudiness', {}).get('percent', 'н/д')
        prec_type_code = weather_data.get('precipitation', {}).get('type')
        weather_emoji = weather_data.get('icon', {}).get('emoji', '❓')
        wind_dir_map = {0: "Штиль", 1: "С", 2: "СВ", 3: "В", 4: "ЮВ", 5: "Ю", 6: "ЮЗ", 7: "З", 8: "СЗ", None: "-"}
        wind_dir = wind_dir_map.get(wind_dir_code, '-')
        prec_type_map = {0: "Без осадков", 1: "Дождь", 2: "Снег", 3: "Смешанные", None: "-"}
        precipitation = prec_type_map.get(prec_type_code, '-')
        message = f"*{escape(location_name)}* | Сейчас {weather_emoji}\n\n" \
                  f"🌡️ *Темп.*: {temp_air}°C ({temp_comfort}°C ощущ.)\n" \
                  f"📝 *Описание*: {description}\n" \
                  f"💧 *Влажн.*: {humidity}%\n" \
                  f"🧭 *Давл.*: {pressure} мм рт.ст.\n" \
                  f"💨 *Ветер*: {wind_dir}, {wind_speed} м/с\n" \
                  f"☁️ *Облачн.*: {cloud_perc}%\n" \
                  f"☔ *Осадки*: {precipitation}"
        return message
    except Exception as e: print(f"Ошибка форматирования погоды v3: {e}"); return "Ошибка обработки данных о погоде."

def generate_task_list_message(chat_id, page=1, context="list"):
    user_data = get_user_data(chat_id); tasks = user_data.get('tasks', [])
    if not tasks: return "📭 Твой список задач пуст.", None
    sorted_tasks = sorted(tasks, key=lambda t: (t.get('status', 'pending') != 'pending', -t.get('id', 0)))
    list_title = f"📋 *Твои задачи*"; total_tasks = len(sorted_tasks); total_pages = math.ceil(total_tasks / TASKS_PER_PAGE)
    page = max(1, min(page, total_pages if total_pages > 0 else 1)); start_index = (page - 1) * TASKS_PER_PAGE; end_index = start_index + TASKS_PER_PAGE
    tasks_on_page = sorted_tasks[start_index:end_index]
    if not tasks_on_page: return f"{list_title}\n\n🤔 Задач на этой странице нет.", None
    message_text = f"{list_title} (Страница {page}/{total_pages}):\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2); task_buttons = []
    for task in tasks_on_page:
        status_icon = "⏳" if task.get('status', 'pending') == 'pending' else "✔️"; task_id = task.get('id'); task_text = escape(task.get('text', 'Нет текста'))
        message_text += f"{status_icon} `[ID: {task_id}]` {task_text}\n"; buttons_row = []
        if task.get('status', 'pending') == 'pending': buttons_row.append(types.InlineKeyboardButton(f"✅ Выполнить {task_id}", callback_data=f"{context}_done_{task_id}_{page}"))
        else: buttons_row.append(types.InlineKeyboardButton(f"↩️ Вернуть {task_id}", callback_data=f"{context}_undo_{task_id}_{page}"))
        buttons_row.append(types.InlineKeyboardButton(f"❌ Удалить {task_id}", callback_data=f"{context}_delete_{task_id}_{page}"))
        task_buttons.extend(buttons_row)
    markup.add(*task_buttons); nav_buttons = []
    if page > 1: nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"{context}_page_{page - 1}"))
    if page < total_pages: nav_buttons.append(types.InlineKeyboardButton("Вперед ➡️", callback_data=f"{context}_page_{page + 1}"))
    if nav_buttons: markup.row(*nav_buttons)
    return message_text, markup

def generate_completed_list_message(chat_id, page=1):
    user_data = get_user_data(chat_id); completed_tasks = [t for t in user_data.get('tasks', []) if t.get('status') == 'completed']
    if not completed_tasks: return "✅ У тебя пока нет выполненных задач.", None
    sorted_tasks = sorted(completed_tasks, key=lambda t: -t.get('id', 0)); list_title = "✔️ *Выполненные задачи*"; context = "completed"
    total_tasks = len(sorted_tasks); total_pages = math.ceil(total_tasks / TASKS_PER_PAGE)
    page = max(1, min(page, total_pages if total_pages > 0 else 1)); start_index = (page - 1) * TASKS_PER_PAGE; end_index = start_index + TASKS_PER_PAGE
    tasks_on_page = sorted_tasks[start_index:end_index]
    if not tasks_on_page: return f"{list_title}\n\n🤔 Выполненных задач на этой странице нет.", None
    message_text = f"{list_title} (Страница {page}/{total_pages}):\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2); task_buttons = []
    for task in tasks_on_page:
        task_id = task.get('id'); task_text = escape(task.get('text', 'Нет текста')); message_text += f"✔️ `[ID: {task_id}]` {task_text}\n"
        buttons_row = [types.InlineKeyboardButton(f"↩️ Вернуть {task_id}", callback_data=f"{context}_undo_{task_id}_{page}"),
                       types.InlineKeyboardButton(f"❌ Удалить {task_id}", callback_data=f"{context}_delete_{task_id}_{page}")]
        task_buttons.extend(buttons_row)
    markup.add(*task_buttons); nav_buttons = []
    if page > 1: nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"{context}_page_{page - 1}"))
    if page < total_pages: nav_buttons.append(types.InlineKeyboardButton("Вперед ➡️", callback_data=f"{context}_page_{page + 1}"))
    if nav_buttons: markup.row(*nav_buttons)
    return message_text, markup

def generate_last_tasks_message(chat_id):
    user_data = get_user_data(chat_id); tasks = user_data.get('tasks', [])
    if not tasks: return f"🕙 У тебя пока нет задач.", None
    sorted_tasks = sorted(tasks, key=lambda t: -t.get('id', 0))[:LAST_TASKS_COUNT]
    list_title = f"🕙 *Последние {len(sorted_tasks)} задач:*"; context = "last10"
    message_text = f"{list_title}\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2); task_buttons = []
    for task in sorted_tasks:
        status_icon = "⏳" if task.get('status', 'pending') == 'pending' else "✔️"; task_id = task.get('id'); task_text = escape(task.get('text', 'Нет текста'))
        message_text += f"{status_icon} `[ID: {task_id}]` {task_text}\n"; buttons_row = []
        if task.get('status', 'pending') == 'pending': buttons_row.append(types.InlineKeyboardButton(f"✅ Выполнить {task_id}", callback_data=f"{context}_done_{task_id}_0"))
        else: buttons_row.append(types.InlineKeyboardButton(f"↩️ Вернуть {task_id}", callback_data=f"{context}_undo_{task_id}_0"))
        buttons_row.append(types.InlineKeyboardButton(f"❌ Удалить {task_id}", callback_data=f"{context}_delete_{task_id}_0"))
        task_buttons.extend(buttons_row)
    markup.add(*task_buttons)
    return message_text, markup

def create_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    tasks_btn = types.KeyboardButton("📋 Задачи")
    weather_btn = types.KeyboardButton("☀️ Погода")
    help_btn = types.KeyboardButton("ℹ️ Помощь")
    markup.add(tasks_btn, weather_btn, help_btn)
    return markup

bot = telebot.TeleBot(API_TOKEN)

def set_bot_commands(bot_instance):
    commands = [
        types.BotCommand("start", "🚀 Запуск / Приветствие"),
        types.BotCommand("menu", "📌 Показать главное меню"),
        types.BotCommand("help", "ℹ️ Справка по командам"),
        types.BotCommand("add", "➕ Добавить задачу (<текст>)"),
        types.BotCommand("list", "📋 Показать все задачи"),
        types.BotCommand("last", "🕙 Показать последние задачи"),
        types.BotCommand("completed", "✅ Показать выполненные"),
        types.BotCommand("weather", "☀️ Узнать погоду (<город>)")
    ]
    try:
        bot_instance.set_my_commands(commands)
        print("Команды бота успешно установлены.")
    except Exception as e:
        print(f"Ошибка при установке команд бота: {e}")

def set_bot_description(bot_instance):
    description = "Ваш личный помощник для управления задачами и просмотра погоды. Умеет добавлять, показывать и отмечать задачи. Запрашивает погоду по названию города."
    try:
        bot_instance.set_my_description(description=description, language_code="ru")
        print("Описание бота успешно установлено.")
    except Exception as e:
        print(f"Ошибка при установке описания бота: {e}")

set_bot_commands(bot)
set_bot_description(bot)

print("Загрузка данных пользователей...")
all_user_data = load_data()
print(f"Данные для {len(all_user_data)} пользователей загружены.")
print("Бот запускается...")

@bot.message_handler(commands=['start', 'menu'])
def send_welcome_or_menu(message):
    if message.text.startswith('/start'):
        welcome_text = (f"👋 *Привет, {escape(message.from_user.first_name)}! Я твой бот-помощник.*\n\n"
                        "Используй кнопки внизу или команду /help для справки.")
        bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(), parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "📌 Главное меню:", reply_markup=create_main_keyboard())

@bot.message_handler(commands=['help'])
def send_structured_help(message):
    help_text = (
        "📖 *Справка по командам:*\n"
        "(Список команд также доступен через кнопку '/' или 'Меню')\n\n"
        "🚀 `/start` - Запуск / Приветствие\n"
        "📌 `/menu` - Показать главное меню с кнопками\n"
        "ℹ️ `/help` - Показать эту справку\n\n"
        "*Задачи:*\n"
        "➕ `/add <текст>` - Добавить новую задачу\n"
        "📋 `/list` - Показать все задачи\n"
        "🕙 `/last` - Показать последние {lc} задач\n"
        "✅ `/completed` - Показать выполненные\n\n"
        "*Погода:*\n"
        "☀️ `/weather <город>` - Узнать текущую погоду"
    ).format(lc=LAST_TASKS_COUNT)
    try:
        bot.reply_to(message, help_text, parse_mode='Markdown')
    except Exception as e: print(f"Ошибка /help: {e}")

@bot.message_handler(func=lambda message: message.text == "📋 Задачи")
def handle_tasks_button(message):
    tasks_info_text = ("📁 *Раздел 'Задачи'*\n\n"
                       "Выбери команду:\n"
                       "▪️ `/list`\n▪️ `/last`\n▪️ `/completed`\n▪️ `/add <текст>`")
    bot.send_message(message.chat.id, tasks_info_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "☀️ Погода")
def handle_weather_button(message):
    weather_prompt_text = "🌍 Введите название города:"
    markup = types.ForceReply(selective=True)
    bot.send_message(message.chat.id, weather_prompt_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Помощь")
def handle_help_button(message):
    send_structured_help(message)

@bot.message_handler(commands=['add'])
def handle_add_task(message):
    global all_user_data
    try:
        user_data = get_user_data(message.chat.id)
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2 or not command_parts[1].strip():
            prompt_text = "📝 Введите текст новой задачи:"
            markup = types.ForceReply(selective=True)
            bot.reply_to(message, prompt_text, reply_markup=markup)
            return
        task_text = command_parts[1].strip()
        current_id = user_data['next_id']
        new_task = {'id': current_id, 'text': task_text, 'status': 'pending', 'added_at': time.time()}
        user_data['tasks'].append(new_task)
        user_data['next_id'] += 1
        save_data(all_user_data)
        bot.reply_to(message, f"✅ Задача добавлена! (ID: `{current_id}`)", parse_mode='Markdown')
    except Exception as e:
        print(f"Ошибка /add: {e}")
        bot.reply_to(message, "❌ Ошибка при добавлении задачи.")

@bot.message_handler(commands=['list'])
def handle_list_tasks(message):
    try:
        chat_id = message.chat.id; message_text, markup = generate_task_list_message(chat_id, page=1, context="list")
        bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')
    except Exception as e: print(f"Ошибка /list: {e}"); bot.reply_to(message, "❌ Не удалось показать список.")

@bot.message_handler(commands=['last', 'last10'])
def handle_last_tasks(message):
    try:
        chat_id = message.chat.id; message_text, markup = generate_last_tasks_message(chat_id)
        bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')
    except Exception as e: print(f"Ошибка /last: {e}"); bot.reply_to(message, "❌ Не удалось показать последние задачи.")

@bot.message_handler(commands=['completed'])
def handle_completed_tasks(message):
    try:
        chat_id = message.chat.id; message_text, markup = generate_completed_list_message(chat_id, page=1)
        bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')
    except Exception as e: print(f"Ошибка /completed: {e}"); bot.reply_to(message, "❌ Не удалось показать выполненные задачи.")

@bot.message_handler(commands=['weather'])
def handle_weather_command(message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2 or not command_parts[1].strip():
            prompt_text = "🌍 Введите название города:"
            markup = types.ForceReply(selective=True)
            bot.reply_to(message, prompt_text, reply_markup=markup)
            return
        city_name_query = command_parts[1].strip()
        processing_msg = bot.reply_to(message, f"🌍 Ищу '{escape(city_name_query)}'...")
        latitude, longitude, full_address = get_coordinates_by_city_name(city_name_query)
        if full_address and not latitude:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=f"⚠️ {full_address}")
            return
        location_display_name = full_address if full_address else city_name_query
        bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=f"📍 Найдены координаты. Запрашиваю погоду...")
        bot.send_chat_action(message.chat.id, 'typing')
        weather_data, error_msg = get_weather_by_coords(latitude, longitude)
        if error_msg:
            bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=f"⚠️ Ошибка погоды: {error_msg}")
            return
        weather_message = format_weather_message(weather_data, location_display_name)
        bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text=weather_message, parse_mode='Markdown')
    except Exception as e:
        print(f"Критич. ошибка handle_weather_command: {e}")
        try:
            if 'processing_msg' in locals() and processing_msg: bot.edit_message_text(chat_id=message.chat.id, message_id=processing_msg.message_id, text="❌ Внутр. ошибка погоды.")
            else: bot.reply_to(message, "❌ Внутр. ошибка погоды.")
        except Exception as inner_e: print(f"Не удалось отправить сообщение об ошибке погоды: {inner_e}"); bot.send_message(message.chat.id, "❌ Внутр. ошибка погоды.")

@bot.message_handler(func=lambda message: message.reply_to_message is not None and "Введите текст новой задачи" in message.reply_to_message.text)
def handle_task_text_reply(message):
    task_text = message.text.strip()
    if not task_text:
        bot.reply_to(message, "Вы отправили пустой текст. Задача не добавлена. Попробуйте /add <текст>.")
        return
    print(f"Получен ответ на запрос текста задачи: '{task_text}'")
    fake_command_message = message
    fake_command_message.text = f"/add {task_text}"
    handle_add_task(fake_command_message)

@bot.message_handler(func=lambda message: message.reply_to_message is not None and "Введите название города" in message.reply_to_message.text)
def handle_city_name_reply(message):
    city_name = message.text.strip()
    if not city_name:
        bot.reply_to(message, "Вы отправили пустое название. Попробуйте /weather <город>.")
        return
    print(f"Получен ответ на запрос города: '{city_name}'")
    fake_command_message = message
    fake_command_message.text = f"/weather {city_name}"
    handle_weather_command(fake_command_message)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    global all_user_data; chat_id = call.message.chat.id; message_id = call.message.message_id; callback_data = call.data
    try:
        parts = callback_data.split('_');
        if len(parts) < 2: bot.answer_callback_query(call.id, "Ошибка данных.", show_alert=True); return
        context = parts[0]; action = parts[1]
        if action == "page":
            try:
                current_page = int(parts[2])
                if context == "list": message_text, markup = generate_task_list_message(chat_id, page=current_page, context=context)
                elif context == "completed": message_text, markup = generate_completed_list_message(chat_id, page=current_page)
                else: bot.answer_callback_query(call.id, "Неизвестный список."); return
                bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message_text, reply_markup=markup, parse_mode='Markdown')
                bot.answer_callback_query(call.id, text=f"Стр. {current_page}")
            except (ValueError, IndexError): bot.answer_callback_query(call.id, "Ошибка стр.", show_alert=True)
            except Exception as e: print(f"Ошибка пагинации ({context}): {e}"); bot.answer_callback_query(call.id, "Ошибка обновления", show_alert=True)
        elif action in ["done", "undo", "delete"]:
            try:
                task_id_to_act = int(parts[2]); current_page = int(parts[3]) if len(parts) > 3 else 1
                user_data = get_user_data(chat_id); task_found = False; task_index = -1
                for i, task in enumerate(user_data.get('tasks', [])):
                    if task.get('id') == task_id_to_act: task_found = True; task_index = i; break
                if not task_found: bot.answer_callback_query(call.id, f"❓ Задача {task_id_to_act} не найдена.", show_alert=True); update_task_view(context, chat_id, message_id, current_page); return
                alert_text = ""
                if action == "done": user_data['tasks'][task_index]['status'] = 'completed'; alert_text = f"✅ Задача {task_id_to_act} выполнена!"
                elif action == "undo": user_data['tasks'][task_index]['status'] = 'pending'; alert_text = f"↩️ Задача {task_id_to_act} возвращена!"
                elif action == "delete": del user_data['tasks'][task_index]; alert_text = f"🗑️ Задача {task_id_to_act} удалена!"
                save_data(all_user_data); bot.answer_callback_query(call.id, text=alert_text)
                update_task_view(context, chat_id, message_id, current_page)
            except (ValueError, IndexError): bot.answer_callback_query(call.id, "Ошибка ID/Page", show_alert=True)
            except Exception as e: print(f"Ошибка '{action}' ({context}): {e}"); bot.answer_callback_query(call.id, "Ошибка обработки", show_alert=True)
        else: bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"Критич. ошибка callback: {e}, data: {callback_data}")
        try: bot.answer_callback_query(call.id, "Внутр. ошибка", show_alert=True)
        except Exception: pass

def update_task_view(context, chat_id, message_id, page):
    try:
        if context == "list": message_text, markup = generate_task_list_message(chat_id, page=page, context=context)
        elif context == "completed": message_text, markup = generate_completed_list_message(chat_id, page=page)
        elif context == "last10": message_text, markup = generate_last_tasks_message(chat_id)
        else: print(f"Неизвестный контекст: {context}"); return
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message_text, reply_markup=markup, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' in str(e): print(f"Сообщение {message_id} не изменено.")
        elif 'Too Many Requests' in str(e): print(f"Слишком много запросов {message_id}."); time.sleep(1)
        else: print(f"Ошибка API при обновлении ({context}): {e}")
    except Exception as e: print(f"Ошибка обновления ({context}): {e}")

if __name__ == '__main__':
    print("Запуск polling...")
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=10)
    except Exception as e:
        print(f"Критическая ошибка polling: {e}")
        time.sleep(15)
    finally:
        print("Сохранение данных перед остановкой...")
        save_data(all_user_data)
        print("Бот остановлен.")