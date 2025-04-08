import sqlite3
from datetime import datetime, date
from typing import List, Tuple

REQUESTS_DB_PATH = "db/requests.db"

# Создаём таблицу requests, если не существует
def init_requests_db() -> None:
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            text TEXT,
            date TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_request(user_id: str, text: str) -> None:
    """
    Добавляет запись (user_id, text, date=сегодня) в таблицу requests.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO requests (user_id, text, date)
        VALUES (?, ?, ?)
    """, (user_id, text, today_str))
    conn.commit()
    conn.close()

def get_requests_count_today() -> int:
    """
    Возвращает кол-во запросов за сегодняшний день.
    """
    today_str = date.today().isoformat()
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM requests WHERE date = ?
    """, (today_str,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_all_requests() -> List[Tuple[str, str, str]]:
    """
    Возвращает список всех (user_id, text, date) из таблицы requests.
    """
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, text, date FROM requests")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_total_requests_count() -> int:
    """
    Кол-во всех запросов (за всё время).
    """
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM requests")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_unique_users_count() -> int:
    """
    Кол-во уникальных user_id за всё время.
    """
    conn = sqlite3.connect(REQUESTS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM requests")
    count = cur.fetchone()[0]
    conn.close()
    return count
