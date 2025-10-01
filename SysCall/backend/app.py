# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import csv
from positioning import PositionCalculator

app = Flask(__name__)
# CORS нужен, чтобы фронтенд мог без проблем делать запросы к бэкенду
CORS(app)

# --- Глобальные переменные ---
beacons = {}
last_known_position = {"x": 0, "y": 0}


# --- Загрузка данных и инициализация ---
def load_beacons_from_csv(filename='beacons.beacons'):
    """Загружает координаты маячков из CSV файла."""
    beacons_data = {}
    try:
        with open(filename, mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile, delimiter=';')
            for row in reader:
                name = row['Name']
                beacons_data[name] = {
                    'name': name,
                    'x': float(row['X']),
                    'y': float(row['Y'])
                }
        print(f"Successfully loaded {len(beacons_data)} beacons.")
        return beacons_data
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
        return {}


# Загружаем маячки при старте сервера
beacons = load_beacons_from_csv()
print(beacons)
# Инициализируем калькулятор позиции
position_calculator = PositionCalculator(beacons)


# --- API Эндпоинты ---

@app.route('/api/beacons', methods=['GET'])
def get_beacons():
    """Отдает список всех маячков и их координат."""
    return jsonify(list(beacons.values()))


@app.route('/api/position', methods=['POST'])
def update_position():
    """
    Принимает данные сканирования от ESP32, вычисляет позицию
    и сохраняет ее.
    """
    global last_known_position

    data = request.get_json()
    if not data or 'scans' not in data:
        return jsonify({"error": "Invalid data format"}), 400

    scan_data = data['scans']
    print(f"Received scan data: {scan_data}")

    # Вычисляем позицию
    calculated_pos = position_calculator.calculate_position(scan_data)

    if calculated_pos:
        last_known_position = calculated_pos
        print(f"New position calculated: {last_known_position}")
        return jsonify({"status": "success", "position": last_known_position})
    else:
        return jsonify({"status": "error", "message": "Could not calculate position"}), 500


@app.route('/api/current_position', methods=['GET'])
def get_current_position():
    """Отдает последнюю известную позицию (для фронтенда)."""
    return jsonify(last_known_position)


# Заглушка для эндпоинта маршрута (реализуем позже, если успеем)
@app.route('/api/route', methods=['POST'])
def get_route():
    # Здесь будет логика построения маршрута с помощью алгоритма A*
    # Пока просто вернем заглушку
    data = request.get_json()
    start = last_known_position
    end = data.get('end_point')
    print(f"Route requested from {start} to {end}")

    # Возвращаем фейковый маршрут для демонстрации
    fake_route = [start, {"x": (start['x'] + end['x']) / 2, "y": (start['y'] + end['y']) / 2}, end]
    return jsonify(fake_route)


if __name__ == '__main__':
    # Запускаем сервер. host='0.0.0.0' делает его доступным
    # для других устройств в твоей локальной сети (для ESP32).
    app.run(host='0.0.0.0', port=5000, debug=True)