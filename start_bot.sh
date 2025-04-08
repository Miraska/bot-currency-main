#!/bin/bash

# Проверка наличия виртуального окружения
if [ ! -d ".venv" ]; then
    echo "Виртуальное окружение не найдено. Создание нового..."
    python3 -m venv .venv

    # Активация виртуального окружения
    source .venv/bin/activate
    pip install -r requirements.txt
else
    # Активация виртуального окружения
    source .venv/bin/activate
    pip install -r requirements.txt
fi

# Запуск бота
python3 main.py

# Ожидание нажатия клавиши
read -p "Нажмите любую клавишу для выхода..."
