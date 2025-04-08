import io
import sqlite3
from datetime import datetime, date
from typing import List, Tuple

from db.requests_database import (
    init_requests_db,
    log_request,
    get_requests_count_today,
    get_all_requests,
    get_total_requests_count,
    get_unique_users_count
)

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from tabulate import tabulate

from aiogram.types import BufferedInputFile

def generate_stats_table_today() -> str:
    """
    Формирует текстовую таблицу (tabulate) для запросов за сегодня.
    """
    rows = _get_requests_rows_today()
    headers = ["User ID", "Text", "Date"]
    table_str = tabulate(rows, headers, tablefmt="pretty")
    return table_str

def _get_requests_rows_today() -> List[Tuple[str, str, str]]:
    # Вспомогательная функция
    today_str = date.today().isoformat()
    all_rows = get_all_requests()
    # Фильтруем
    today_rows = [row for row in all_rows if row[2] == today_str]
    return today_rows

def generate_full_stats_pdf() -> BufferedInputFile:
    """
    Генерирует PDF со всей статистикой:
    - Кол-во уникальных пользователей
    - Кол-во запросов за сегодня
    - Кол-во запросов за всё время
    - Полная таблица запросов (user_id, text, date)
    Возвращает файл в формате BufferedInputFile для отправки через aiogram.
    """
    rows = get_all_requests()
    unique_users = get_unique_users_count()
    requests_today = get_requests_count_today()
    requests_total = get_total_requests_count()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    # Добавим обобщающую информацию
    summary_text = (
        f"Unique users: {unique_users}\n"
        f"Requests today: {requests_today}\n"
        f"Requests total: {requests_total}\n"
    )
    elements.append(Paragraph(summary_text, styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Таблица со всеми запросами
    data = [["User ID", "Text", "Date"]]
    if rows:
        data += [list(row) for row in rows]
    else:
        data.append(["—", "Нет запросов", "—"])

    table = Table(data)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ])
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    pdf_file = BufferedInputFile(file=buffer.getvalue(), filename="full_stats.pdf")
    return pdf_file
