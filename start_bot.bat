@echo off
setlocal

:: Проверка наличия виртуального окружения
if not exist ".venv\Scripts\activate" (
    echo Виртуальное окружение не найдено. Создание нового...
    python -m venv .venv

    :: Активация виртуального окружения
    call .venv\\Scripts\\activate
    pip install -r requirements.txt
)

else (
    :: Активация виртуального окружения
    call .venv\\Scripts\\activate
    pip install -r requirements.txt
)

:: Запуск бота
python main.py

pause