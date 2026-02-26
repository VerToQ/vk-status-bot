import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import psycopg2
import os
from datetime import datetime
import time

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('VK_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
CHAT_ID = os.environ.get('CHAT_ID')
ADMIN_IDS = os.environ.get('ADMIN_IDS', '').split(',')

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            vk_id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            status TEXT DEFAULT 'offline',
            level INTEGER DEFAULT 1,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            vk_id TEXT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ База данных создана")

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С УРОВНЯМИ ==========
def get_user_level(vk_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT level FROM users WHERE vk_id = %s", (str(vk_id),))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 0

def can_register(registrar_vk_id, target_level):
    registrar_level = get_user_level(registrar_vk_id)
    
    if str(registrar_vk_id) in ADMIN_IDS:
        return True
        
    if registrar_level == 3:
        return True
    elif registrar_level == 2:
        return target_level == 1
    else:
        return False

# ========== ФУНКЦИИ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========
def register_user(registrar_vk_id, target_vk_id, nickname, level=1):
    if not can_register(registrar_vk_id, level):
        return False, "У вас недостаточно прав для регистрации этого уровня!"
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT nickname FROM users WHERE vk_id = %s", (str(target_vk_id),))
    if cur.fetchone():
        cur.close()
        conn.close()
        return False, "Пользователь уже зарегистрирован!"
    
    cur.execute(
        "INSERT INTO users (vk_id, nickname, status, level) VALUES (%s, %s, %s, %s)",
        (str(target_vk_id), nickname, 'offline', level)
    )
    
    cur.execute(
        "INSERT INTO logs (vk_id, action, details) VALUES (%s, %s, %s)",
        (str(registrar_vk_id), 'register', f'Зарегистрировал {nickname} (уровень {level})')
    )
    
    conn.commit()
    cur.close()
    conn.close()
    return True, f"Пользователь {nickname} (уровень {level}) зарегистрирован!"

def update_status(vk_id, new_status):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT nickname, status FROM users WHERE vk_id = %s", (str(vk_id),))
    result = cur.fetchone()
    
    if not result:
        cur.close()
        conn.close()
        return None, None
    
    nickname, old_status = result
    
    cur.execute(
        "UPDATE users SET status = %s, last_update = CURRENT_TIMESTAMP WHERE vk_id = %s",
        (new_status, str(vk_id))
    )
    
    conn.commit()
    cur.close()
    conn.close()
    return nickname, old_status

def get_user_info(vk_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT nickname, status, level FROM users WHERE vk_id = %s", (str(vk_id),))
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    if result:
        return {"nickname": result[0], "status": result[1], "level": result[2]}
    return None

def get_users_by_status(status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT vk_id, nickname, level FROM users WHERE status = %s ORDER BY nickname",
        (status,)
    )
    results = cur.fetchall()
    cur.close()
    conn.close()
    return [{"vk_id": r[0], "nickname": r[1], "level": r[2]} for r in results]

def get_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT vk_id, nickname, status, level FROM users ORDER BY level DESC, nickname")
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def unregister_user(registrar_vk_id, target_vk_id):
    registrar_level = get_user_level(registrar_vk_id)
    
    if str(registrar_vk_id) != str(target_vk_id) and registrar_level < 3:
        return False, "Только администраторы могут удалять других пользователей!"
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT nickname FROM users WHERE vk_id = %s", (str(target_vk_id),))
    result = cur.fetchone()
    
    if result:
        nickname = result[0]
        cur.execute("DELETE FROM users WHERE vk_id = %s", (str(target_vk_id),))
        
        cur.execute(
            "INSERT INTO logs (vk_id, action, details) VALUES (%s, %s, %s)",
            (str(registrar_vk_id), 'unregister', f'Удалил {nickname}')
        )
        
        conn.commit()
        cur.close()
        conn.close()
        return True, nickname
    
    cur.close()
    conn.close()
    return False, None

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🟢 Онлайн", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🟡 АФК", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🔴 Вышел", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("👤 Мой статус", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📋 Кто онлайн", color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

def get_admin_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🟢 Онлайн", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🟡 АФК", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🔴 Вышел", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("👤 Мой статус", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📋 Кто онлайн", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("📊 Все пользователи", color=VkKeyboardColor.PRIMARY)
    return keyboard.get_keyboard()

# ========== ОСНОВНАЯ ЛОГИКА ==========
def main():
    init_db()
    
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)
    
    print("✅ Бот запущен!")
    
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            msg = event.text.lower().strip()
            user_id = str(event.user_id)
            peer_id = event.peer_id
            
            user_info = get_user_info(user_id)
            
            if event.from_chat:
                if not user_info and not msg.startswith('!рег'):
                    continue
                
                if not msg.startswith('!'):
                    continue
                
                msg = msg[1:]
            
            # РЕГИСТРАЦИЯ
            if msg.startswith('рег'):
                if not event.from_chat:
                    parts = msg.split()
                    if len(parts) >= 3:
                        try:
                            target_id = parts[1].replace('[', '').replace(']', '').replace('id', '').replace('@', '')
                            nickname = parts[2]
                            level = int(parts[3]) if len(parts) > 3 else 1
                            
                            success, result = register_user(user_id, target_id, nickname, level)
                            
                            vk.messages.send(
                                peer_id=peer_id,
                                message=f"{'✅' if success else '❌'} {result}",
                                random_id=0
                            )
                        except:
                            vk.messages.send(
                                peer_id=peer_id,
                                message="❌ Ошибка. Пример: рег @id123456 Вася 1",
                                random_id=0
                            )
                else:
                    vk.messages.send(
                        peer_id=peer_id,
                        message="❌ Регистрация только в ЛС!",
                        random_id=0
                    )
                continue
            
            # СТАТУСЫ
            if user_info:
                nickname = user_info['nickname']
                old_status = user_info['status']
                response = ""
                new_status = None
                
                if msg in ["онлайн", "!онлайн"]:
                    if old_status == "online":
                        response = f"⚠ {nickname}, уже в онлайне!"
                    else:
                        new_status = "online"
                        update_status(user_id, "online")
                        response = f"🟢 {nickname} зашёл!"
                
                elif msg in ["афк", "!афк"]:
                    if old_status == "afk":
                        response = f"⚠ {nickname}, уже в АФК!"
                    else:
                        new_status = "afk"
                        update_status(user_id, "afk")
                        response = f"🟡 {nickname} отошёл"
                
                elif msg in ["вышел", "!вышел"]:
                    if old_status == "offline":
                        response = f"⚠ {nickname}, уже вне сети!"
                    else:
                        new_status = "offline"
                        update_status(user_id, "offline")
                        response = f"🔴 {nickname} вышел"
                
                elif msg in ["мой статус", "!мой статус"]:
                    status_text = {
                        "online": "🟢 Онлайн",
                        "afk": "🟡 АФК",
                        "offline": "⚫ Офлайн"
                    }.get(user_info['status'], "⚫ Офлайн")
                    
                    vk.messages.send(
                        peer_id=peer_id,
                        message=f"👤 {nickname} (ур.{user_info['level']})\nСтатус: {status_text}",
                        random_id=0,
                        keyboard=get_main_keyboard() if user_info['level'] < 2 else get_admin_keyboard()
                    )
                    continue
                
                elif msg in ["кто онлайн", "!кто онлайн"]:
                    online_users = get_users_by_status("online")
                    afk_users = get_users_by_status("afk")
                    
                    message = "📊 **НА СЕРВЕРЕ**\n\n"
                    
                    if online_users:
                        message += "🟢 **Онлайн:**\n"
                        for u in online_users:
                            message += f"  • {u['nickname']}\n"
                    
                    if afk_users:
                        message += "\n🟡 **АФК:**\n"
                        for u in afk_users:
                            message += f"  • {u['nickname']}\n"
                    
                    if not online_users and not afk_users:
                        message += "📭 Пусто"
                    
                    vk.messages.send(
                        peer_id=peer_id,
                        message=message,
                        random_id=0
                    )
                    continue
                
                # АДМИН КОМАНДЫ
                if user_info['level'] >= 2 and msg in ["все пользователи", "!все пользователи"]:
                    users = get_all_users()
                    message = "📋 **ВСЕ ПОЛЬЗОВАТЕЛИ**\n\n"
                    
                    for u in users:
                        status_emoji = {
                            "online": "🟢",
                            "afk": "🟡",
                            "offline": "⚫"
                        }.get(u[2], "⚫")
                        
                        message += f"{status_emoji} {u[1]} (ур.{u[3]})\n"
                    
                    vk.messages.send(
                        peer_id=peer_id,
                        message=message,
                        random_id=0
                    )
                    continue
                
                # ОТПРАВКА ОБНОВЛЕНИЯ СТАТУСА
                if new_status:
                    online_users = get_users_by_status("online")
                    afk_users = get_users_by_status("afk")
                    
                    status_line = ""
                    if online_users:
                        online_list = ", ".join([u['nickname'] for u in online_users])
                        status_line += f"🟢 В онлайне: {online_list}\n"
                    
                    if afk_users:
                        afk_list = ", ".join([u['nickname'] for u in afk_users])
                        status_line += f"🟡 АФК: {afk_list}"
                    
                    if not online_users and not afk_users:
                        status_line = "📭 Пусто!"
                    
                    full_message = f"{response}\n\n{status_line}"
                    
                    vk.messages.send(
                        peer_id=peer_id,
                        message=full_message,
                        random_id=0
                    )

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)
