# 1. Указываем базовый образ. ЭТО САМАЯ ВАЖНАЯ СТРОКА.
FROM python:3.12-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    gcc \
    make \
    && rm -rf /var/lib/apt/lists/*

# 4. Копируем папки backend и frontend в контейнер
COPY SysCall/backend /app/backend
COPY SysCall/frontend /app/frontend

# 5. Копируем корневой файл requirements.txt
COPY requirements.txt /app/

# 6. Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# 7. Открываем порт
EXPOSE 5000

# 8. Устанавливаем переменные окружения для Flask
ENV FLASK_APP=/app/backend/app.py
ENV FLASK_RUN_HOST=0.0.0.0

# 9. Запускаем приложение
CMD ["flask", "run"]