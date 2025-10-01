import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import threading
import queue
from scipy.optimize import minimize
import numpy as np
import matplotlib.pyplot as plt


LAST_POSITION = np.array([0.0, 0.0])
# --- Настройки ---
BEACONS_FILE = "standart.beacons"
TX_POWER = -54
N = 2.00
MQTT_BROKER = "localhost"
MQTT_TOPIC = "registrar/data"

# --- Инициализация состояния Streamlit ---
if 'path' not in st.session_state: st.session_state.path = []
if 'beacons' not in st.session_state: st.session_state.beacons = {}
if 'recording' not in st.session_state: st.session_state.recording = False
if 'data_queue' not in st.session_state: st.session_state.data_queue = queue.Queue()



# --- Функции для вычислений (без изменений) ---
def load_beacon_positions(filename):
    positions = {};
    try:
        with open(filename, 'r') as f:
            next(f)
            for line in f:
                parts = line.strip().split(';')
                if len(parts) == 3: name, x, y = parts; positions[name] = (float(x), float(y))
        print(f"Загружены из '{filename}': {positions}");
        return positions
    except FileNotFoundError:
        st.error(f"Файл '{filename}' не найден!"); return None


def rssi_to_distance(rssi, tx_power, n): return 10 ** ((tx_power - rssi) / (10 * n))


def error_function(point, beacons):
    error = 0.0;
    px, py = point
    for name, (bx, by, distance) in beacons.items(): error += (np.sqrt((px - bx) ** 2 + (py - by) ** 2) - distance) ** 2
    return error


# Добавьте это в начало файла, после других настроек
RSSI_HISTORY = {}
HISTORY_SIZE = 5  # Будем хранить 5 последних значений


# ...

# Замените вашу функцию on_message на эту обновленную версию
def on_message(client, userdata, msg):
    global LAST_POSITION
    global RSSI_HISTORY  # Объявляем, что будем изменять глобальную переменную
    beacons_positions = userdata['beacons']
    data_queue = userdata['queue']

    if not beacons_positions: return

    try:
        data = json.loads(msg.payload.decode())

        # --- БЛОК ФИЛЬТРАЦИИ ---
        processed_rssi = {}
        for name, rssi in data.items():
            if name not in RSSI_HISTORY:
                RSSI_HISTORY[name] = []

            RSSI_HISTORY[name].append(rssi)

            # Ограничиваем размер истории
            if len(RSSI_HISTORY[name]) > HISTORY_SIZE:
                RSSI_HISTORY[name].pop(0)

            # Считаем среднее и используем его
            average_rssi = sum(RSSI_HISTORY[name]) / len(RSSI_HISTORY[name])
            processed_rssi[name] = average_rssi
        # --- КОНЕЦ БЛОКА ФИЛЬТРАЦИИ ---

        beacons_for_calc = {}
        # Используем отфильтрованные данные processed_rssi вместо сырых data
        for name, avg_rssi in processed_rssi.items():
            if name in beacons_positions:
                dist = rssi_to_distance(avg_rssi, TX_POWER, N)  # Используем средний RSSI
                bx, by = beacons_positions[name]
                beacons_for_calc[name] = (bx, by, dist)

        if len(beacons_for_calc) < 3: return
        result = minimize(error_function, LAST_POSITION, args=(beacons_for_calc,), method='L-BFGS-B')

        if result.success:
            new_point_coords = result.x
            # Сохраняем новую позицию для следующего раза
            LAST_POSITION = new_point_coords

            new_point = {'x': new_point_coords[0], 'y': new_point_coords[1]}
            data_queue.put(new_point)

    except Exception as e:
        print(f"Ошибка в MQTT-потоке: {e}")


# ИЗМЕНЕНИЕ 2: Функция потока теперь принимает и очередь
def mqtt_thread_func(beacon_positions, data_queue):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    # Передаем в userdata и позиции, и саму очередь
    userdata = {'beacons': beacon_positions, 'queue': data_queue}
    client.user_data_set(userdata)
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, 1883, 60)
        client.subscribe(MQTT_TOPIC)
        print("MQTT-поток запущен.")
        client.loop_forever()
    except Exception as e:
        print(f"Не удалось запустить MQTT-поток: {e}")


def format_path_data(path_data):
    header = "X;Y\n";
    lines = [f"{p['x']};{p['y']}" for p in path_data];
    return header + "\n".join(lines)


# --- Основная часть - интерфейс Streamlit ---
st.set_page_config(layout="wide")
st.title("Визуализация и управление маршрутом")

if 'beacons_loaded' not in st.session_state:
    st.session_state.beacons = load_beacon_positions(BEACONS_FILE)
    st.session_state.beacons_loaded = True

# ИЗМЕНЕНИЕ 3: Передаем объект очереди в поток при его создании
if 'mqtt_thread_started' not in st.session_state and st.session_state.beacons:
    mqtt_thread = threading.Thread(
        target=mqtt_thread_func,
        args=(st.session_state.beacons, st.session_state.data_queue)  # Передаем и маячки, и очередь
    )
    mqtt_thread.daemon = True
    mqtt_thread.start()
    st.session_state.mqtt_thread_started = True

# ... (код кнопок без изменений) ...
col1, col2, col3 = st.columns(3);
with col1:
    if st.button("Начать новый маршрут"): st.session_state.path = []; st.session_state.recording = True; st.success(
        "Запись начата!")
with col2:
    if st.button("Завершить маршрут"): st.session_state.recording = False; st.info("Запись завершена.")
if st.session_state.recording:
    st.warning(" идет запись маршрута...")
else:
    if st.session_state.path:
        with col3: st.download_button("Скачать маршрут (*.path)", format_path_data(st.session_state.path), "route.path",
                                      "text/plain")

# Основной поток работает с очередью из st.session_state
while not st.session_state.data_queue.empty():
    new_point = st.session_state.data_queue.get()
    if st.session_state.recording:
        st.session_state.path.append(new_point)

# ... (код отрисовки без изменений) ...
fig, ax = plt.subplots(figsize=(10, 8))
path_copy = list(st.session_state.path)
if st.session_state.beacons:
    b_x = [p[0] for p in st.session_state.beacons.values()];
    b_y = [p[1] for p in st.session_state.beacons.values()]
    ax.scatter(b_x, b_y, s=100, c='blue', label='Маячки')
    for name, pos in st.session_state.beacons.items(): ax.text(pos[0] + 0.1, pos[1] + 0.1, name)
if len(path_copy) > 0:
    p_x = [p['x'] for p in path_copy];
    p_y = [p['y'] for p in path_copy]
    ax.plot(p_x, p_y, color='red', marker='o', linestyle='-', label='Путь')
    ax.scatter(p_x[-1], p_y[-1], s=150, c='red', edgecolors='black', zorder=5, label='Текущая позиция')
ax.set_xlabel("X (м)");
ax.set_ylabel("Y (м)");
ax.set_title("Карта");
ax.grid(True);
ax.legend();
ax.axis('equal')
st.pyplot(fig);
plt.close(fig)
st.subheader("Данные пути (последние 10 точек)");
st.dataframe(path_copy[-10:])
time.sleep(1);
st.rerun()