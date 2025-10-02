# app.py
import os
import csv
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from positioning import PositionCalculator

app = Flask(__name__)
CORS(app)

# --- Глобальные переменные ---
beacons = {}
last_known_position = {"x": 0, "y": 0}

def load_beacons_from_csv(filename='beacons.beacons'):
    """Загружает координаты маячков из CSV файла, используя безопасный путь."""
    beacons_data = {}
    try:
        script_dir = os.path.dirname(__file__)  # Получаем директорию, где находится этот скрипт (/app/backend)
        abs_file_path = os.path.join(script_dir, filename) # Создаем полный путь /app/backend/beacons.beacons

        with open(abs_file_path, mode='r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile, delimiter=';')
            for row in reader:
                name = row['Name']
                beacons_data[name] = {
                    'name': name,
                    'x': float(row['X']),
                    'y': float(row['Y'])
                }
        print(f"Successfully loaded {len(beacons_data)} beacons from {abs_file_path}.")
        return beacons_data
    except FileNotFoundError:
        print(f"Error: {filename} not found at path {os.path.abspath(filename)}.")
        return {}


# Загружаем маячки при старте сервера
beacons = load_beacons_from_csv()
print(beacons)
# Инициализируем калькулятор позиции
position_calculator = PositionCalculator(beacons)


@app.route('/api/beacons', methods=['GET'])
def get_beacons():
    """Отдает список всех маячков и их координат."""
    return jsonify(list(beacons.values()))


@app.route('/api/position', methods=['POST'])
def update_position():
    """Принимает данные сканирования от ESP32, вычисляет позицию и сохраняет ее."""
    global last_known_position
    data = request.get_json()
    if not data or 'scans' not in data:
        return jsonify({"error": "Invalid data format"}), 400
    scan_data = data['scans']
    print(f"Received scan data: {scan_data}")
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


@app.route('/api/route', methods=['POST'])
def get_route():
    data = request.get_json()
    start = last_known_position
    end = data.get('end_point')
    print(f"Route requested from {start} to {end}")
    fake_route = [start, {"x": (start['x'] + end['x']) / 2, "y": (start['y'] + end['y']) / 2}, end]
    return jsonify(fake_route)

@app.route('/')
def serve_index():
    """Отдает главную страницу index.html."""
    # Путь '/app/frontend' - это куда мы скопировали папку frontend в Dockerfile
    return send_from_directory('/app/frontend', 'index.html')

@app.route('/<path:path>')
def serve_static_files(path):
    """Отдает другие файлы фронтенда (CSS, JS, и т.д.)."""
    return send_from_directory('/app/frontend', path)


if __name__ == '__main__':
    # Эта часть выполняется только при локальном запуске, не в Docker
    app.run(host='0.0.0.0', port=5000, debug=True)