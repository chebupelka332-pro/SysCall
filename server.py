# Код для компьютера (server.py) с алгоритмом позиционирования
import paho.mqtt.client as mqtt
import json
from scipy.optimize import minimize
import numpy as np

# --- Константы и настройки ---
BEACONS_FILE = "standart.beacons"
# TODO: Откалибруйте эти значения!
TX_POWER = -59  # RSSI на расстоянии 1 метра
N = 2.0  # Коэффициент затухания сигнала


# --- Шаг 1: Функция для загрузки позиций маячков ---
def load_beacon_positions(filename):
    positions = {}
    try:
        with open(filename, 'r') as f:
            next(f)  # Пропускаем заголовок
            for line in f:
                parts = line.strip().split(';')
                if len(parts) == 3:
                    name, x, y = parts
                    positions[name] = (float(x), float(y))
        print(f"Загружены позиции маячков: {positions}")
        return positions
    except FileNotFoundError:
        print(f"ОШИБКА: Файл с позициями маячков '{filename}' не найден.")
        return None


# --- Шаг 2: Функция для преобразования RSSI в расстояние ---
def rssi_to_distance(rssi, tx_power, n):
    return 10 ** ((tx_power - rssi) / (10 * n))


# --- Шаг 3: Функция ошибки для алгоритма минимизации ---
# Она вычисляет, насколько "плохо" данная точка (x, y) соответствует измеренным расстояниям
def error_function(point, beacons):
    error = 0.0
    px, py = point
    for name, (bx, by, distance) in beacons.items():
        # Вычисляем расстояние от предполагаемой точки до маячка
        dist_calculated = np.sqrt((px - bx) ** 2 + (py - by) ** 2)
        # Сравниваем с "измеренным" расстоянием
        error += (dist_calculated - distance) ** 2
    return error


# --- Глобальная переменная для хранения позиций ---
BEACON_POSITIONS = load_beacon_positions(BEACONS_FILE)


# --- Обработка MQTT сообщений ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Успешно подключено к MQTT брокеру!")
        client.subscribe("registrar/data")
    else:
        print(f"Не удалось подключиться, код ошибки: {rc}")


def on_message(client, userdata, msg):
    if not BEACON_POSITIONS:
        print("Позиции маячков не загружены, вычисление невозможно.")
        return

    try:
        data = json.loads(msg.payload.decode())
        print(f"Получены данные RSSI: {data}")

        # Собираем данные для вычислений: только те маячки, что есть в нашем файле
        beacons_for_calc = {}
        for name, rssi in data.items():
            if name in BEACON_POSITIONS:
                distance = rssi_to_distance(rssi, TX_POWER, N)
                bx, by = BEACON_POSITIONS[name]
                beacons_for_calc[name] = (bx, by, distance)

        # Для мультилатерации нужно хотя бы 3 маячка
        if len(beacons_for_calc) < 3:
            print(f"Недостаточно маячков для вычисления позиции (нужно >= 3, найдено {len(beacons_for_calc)}).")
            return

        # Начальная точка для поиска (можно взять центр карты)
        initial_guess = np.array([0.0, 0.0])

        # Запускаем оптимизатор для поиска точки с минимальной ошибкой
        result = minimize(
            error_function,
            initial_guess,
            args=(beacons_for_calc,),
            method='L-BFGS-B'
        )

        if result.success:
            calculated_pos = result.x
            print(f"--------------------------------------------")
            print(f"    ВЫЧИСЛЕННАЯ ПОЗИЦИЯ: X={calculated_pos[0]:.2f}, Y={calculated_pos[1]:.2f}")
            print(f"--------------------------------------------\n")
        else:
            print("Не удалось найти решение для позиционирования.")

    except Exception as e:
        print(f"Произошла ошибка при обработке сообщения: {e}")


# --- Настройка и запуск клиента ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883, 60)
print("Сервер запущен и ждет сообщений...")
client.loop_forever()