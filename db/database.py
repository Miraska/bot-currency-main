import sqlite3
import json
from typing import Optional, Any

DB_PATH = "db/users.db"

def init_db() -> None:
    """
    Создаёт таблицу user_variables, если её нет.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_variables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            variables TEXT,
            in_process BOOLEAN
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id: int) -> None:
    """
    Добавляет запись о пользователе, если его ещё нет, с дефолтными переменными.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_variables WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        default_vars = {
            "royalty": 0.1,
            "delivery": 0.15,
            "payment": 0.12,
            "operational": 0.2,
            "cashless": 0.4,
            "discount": 0.2,
            "aedusdt": 0.3
        }
        cur.execute('''
            INSERT INTO user_variables (user_id, variables, in_process)
            VALUES (?, ?, ?)
        ''', (user_id, json.dumps(default_vars), False))
        conn.commit()
    conn.close()

def get_user_variables(user_id: int) -> Optional[dict[str, Any]]:
    """
    Возвращает переменные пользователя в виде словаря.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT variables FROM user_variables WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return None

def update_user_variables(user_id: int, variables: dict[str, Any]) -> None:
    """
    Сохраняет (перезаписывает) переменные пользователя в базе.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        UPDATE user_variables
        SET variables = ?
        WHERE user_id = ?
    ''', (json.dumps(variables), user_id))
    conn.commit()
    conn.close()

def get_process_state(user_id: int) -> bool:
    """
    Возвращает текущее значение in_process (True/False) для пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT in_process FROM user_variables WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return bool(row[0])
    return False

def set_process_state(user_id: int, state: bool) -> None:
    """
    Устанавливает флаг in_process для пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        UPDATE user_variables
        SET in_process = ?
        WHERE user_id = ?
    ''', (state, user_id))
    conn.commit()
    conn.close()


def reset_all_process_states():
    """
    Сбросить состояние процесса у всех пользователей в False.
    Вызывается при старте бота, чтобы не оставалось "залипших" состояний.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE user_variables SET in_process = 0")
        conn.commit()