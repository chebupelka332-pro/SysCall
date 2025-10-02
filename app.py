import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import threading
import queue
from scipy.optimize import minimize
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# --- 1. НАСТРОЙКИ СИСТЕМЫ ---
BEACONS_FILE = "standart.beacons"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "registrar/data"

# --- 2. ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ПРИЛОЖЕНИЯ ---
# Очередь для безопасной передачи данных между потоками MQTT и Streamlit
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()

# Состояния, которые сохраняются между обновлениями страницы
if 'path' not in st.session_state: st.session_state.path = []
if 'beacons' not in st.session_state: st.session_state.beacons = {}
if 'live_data' not in st.session_state: st.session_state.live_data = {}
if 'recording' not in st.session_state: st.session_state.recording = False
if 'app_initialized' not in st.session_state: st.session_state.app_initialized = False

# Хранит последние N значений RSSI для медианного фильтра
if 'rssi_history' not in st.session_state:
    st.session_state.rssi_history = {}
# Хранит состояние для фильтра Калмана по каждому маячку
if 'kalman_states' not in st.session_state:
    st.session_state.kalman_states = {}

# --- НОВОЕ: Словарь для передачи обновляемых параметров в MQTT поток ---
if 'runtime_params' not in st.session_state:
    st.session_state.runtime_params = {}


# --- 3. ПАНЕЛЬ УПРАВЛЕНИЯ И КАЛИБРОВКИ (ШАГ 1) ---
st.sidebar.title("Параметры системы")
st.sidebar.markdown("### Шаг 1: Калибровка")
st.sidebar.info(
    "Измерьте RSSI на 1 метре, чтобы найти `A (Tx Power)`. Затем измерьте на 2, 3, 4 метрах, чтобы подобрать `n`.")
tx_power = st.sidebar.slider("A (Tx Power)", -100.0, -20.0, -46.5, 0.5)
n_path_loss = st.sidebar.slider("n (Path Loss Exponent)", 1.0, 5.0, 2.0, 0.1)

st.sidebar.markdown("### Шаг 2: Настройка фильтров")
median_window = st.sidebar.slider("Окно медианного фильтра", 3, 70, 25, 1)
kalman_R = st.sidebar.slider("Шум измерения (R)", 0.01, 1.0, 0.8, 0.01)
kalman_Q = st.sidebar.slider("Шум процесса (Q)", 0.0001, 0.1, 0.005, 0.0001)

# --- НОВОЕ: Слайдер для управления частотой обновления пути ---
st.sidebar.markdown("### Шаг 3: Настройка вывода")
path_update_rate = st.sidebar.slider("Частота обновления пути (Гц)", 0.1, 10.0, 5.0, 0.1)


# --- 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def load_beacon_positions(filename):
    """Читает файл с координатами маячков."""
    positions = {}
    try:
        with open(filename, 'r') as f:
            next(f)
            for line in f:
                parts = line.strip().split(';')
                if len(parts) == 3:
                    name, x, y = parts
                    positions[name] = (float(x), float(y))
        print(f"Загружены маячки из '{filename}': {positions}")
        return positions
    except Exception as e:
        st.error(f"Ошибка загрузки файла '{filename}': {e}")
        return None

def rssi_to_distance(rssi, tx_power_val, n_val):
    """Преобразует RSSI в расстояние с использованием калибровочных параметров."""
    return 10 ** ((tx_power_val - rssi) / (10 * n_val))

def error_function(point_guess, beacons_with_distances):
    """Функция ошибки для минимизации (Метод Наименьших Квадратов)."""
    error = 0.0
    px, py = point_guess
    for name, (bx, by, distance) in beacons_with_distances.items():
        calculated_dist = np.sqrt((px - bx) ** 2 + (py - by) ** 2)
        error += (calculated_dist - distance) ** 2
    return error

def update_kalman_filter(state, measurement, R, Q):
    """Обновляет состояние 1D фильтра Калмана."""
    x_pred = state['x']
    P_pred = state['P'] + Q
    K = P_pred / (P_pred + R)
    x_new = x_pred + K * (measurement - x_pred)
    P_new = (1 - K) * P_pred
    return {'x': x_new, 'P': P_new}, x_new

# --- 5. ЛОГИКА MQTT В ФОНОВОМ ПОТОКЕ (с фильтрацией) ---

def on_message(client, userdata, msg):
    """Вызывается при получении данных от MQTT. Обрабатывает и фильтрует RSSI."""
    try:
        if 'rssi_history' not in st.session_state: st.session_state.rssi_history = {}
        if 'kalman_states' not in st.session_state: st.session_state.kalman_states = {}

        beacons_positions = userdata['beacons']
        data_queue = userdata['queue']
        params = userdata['params'] # Это ссылка на st.session_state.runtime_params

        # --- НОВОЕ: Логика ограничения частоты обновления ---
        rate = params.get('path_update_rate', 5.0)  # 5.0 - значение по умолчанию
        required_delay = 1.0 / rate
        current_time = time.time()

        # --- Обновляем RSSI в интерфейсе всегда, независимо от частоты ---
        raw_rssi_data = json.loads(msg.payload.decode())
        filtered_rssi_map = {}
        live_data_update = {}
        for name, rssi in raw_rssi_data.items():
            if name not in beacons_positions: continue
            if name not in st.session_state.rssi_history:
                st.session_state.rssi_history[name] = deque(maxlen=params['median_window'])
                st.session_state.kalman_states[name] = {'x': float(rssi), 'P': 1.0}
            st.session_state.rssi_history[name].append(rssi)
            median_filtered_rssi = np.median(list(st.session_state.rssi_history[name]))
            kalman_state = st.session_state.kalman_states[name]
            new_state, kalman_filtered_rssi = update_kalman_filter(
                kalman_state, median_filtered_rssi, params['kalman_R'], params['kalman_Q'])
            st.session_state.kalman_states[name] = new_state
            filtered_rssi_map[name] = kalman_filtered_rssi
            live_data_update[name] = {'raw_rssi': rssi, 'filtered_rssi': round(kalman_filtered_rssi, 2)}
        # --- Конец блока обновления RSSI ---

        # --- НОВОЕ: Проверяем, прошло ли достаточно времени для расчета точки ---
        if (current_time - userdata['last_update_time']) < required_delay:
            # Времени прошло недостаточно. Отправляем только live_data и выходим.
            data_queue.put({'point': None, 'live_data': live_data_update})
            return

        # --- ЭТАП МУЛЬТИЛАТЕРАЦИИ (выполняется только с нужной частотой) ---
        N_BEST_BEACONS = 3
        sorted_beacons = sorted(filtered_rssi_map.items(), key=lambda item: item[1], reverse=True)
        top_n_beacons = dict(sorted_beacons[:N_BEST_BEACONS])

        beacons_for_calc = {}
        for name, filtered_rssi in top_n_beacons.items():
            if name in beacons_positions:
                distance = rssi_to_distance(filtered_rssi, params['tx_power'], params['n_path_loss'])
                bx, by = beacons_positions[name]
                beacons_for_calc[name] = (bx, by, distance)

        if len(beacons_for_calc) < 3:
            data_queue.put({'point': None, 'live_data': live_data_update})
            return

        result = minimize(error_function, np.array([0.0, 0.0]), args=(beacons_for_calc,), method='L-BFGS-B')

        if result.success:
            # --- НОВОЕ: Обновляем время последней успешной калькуляции ---
            userdata['last_update_time'] = current_time
            new_point = {'x': result.x[0], 'y': result.x[1]}
            data_to_queue = {'point': new_point, 'live_data': live_data_update}
            data_queue.put(data_to_queue)
        else:
            # Если расчет не удался, отправляем только live_data
            data_queue.put({'point': None, 'live_data': live_data_update})

    except Exception as e:
        print(f"Ошибка в MQTT-потоке: {e}")

def mqtt_thread_func(beacon_positions, data_queue, params):
    """Функция, которая запускает MQTT-клиент в отдельном потоке."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    # --- ИЗМЕНЕНО: Добавляем 'last_update_time' в user_data ---
    client.user_data_set({
        'beacons': beacon_positions,
        'queue': data_queue,
        'params': params,
        'last_update_time': 0.0
    })
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, 1883, 60)
        client.subscribe(MQTT_TOPIC)
        print("MQTT-поток запущен.")
        client.loop_forever()
    except Exception as e:
        print(f"Не удалось запустить MQTT-поток: {e}")

def format_path_data_for_download(path_data):
    """Готовит строку для сохранения в .path файл."""
    header = "X;Y\n"
    lines = [f"{point['x']};{point['y']}" for point in path_data]
    return header + "\n".join(lines)

# --- 6. ИНТЕРФЕЙС STREAMLIT ---

st.set_page_config(layout="wide")
st.title("Улучшенная система навигации с фильтрацией")

# --- ИЗМЕНЕНО: Обновляем общий словарь параметров при каждом rerun ---
st.session_state.runtime_params.update({
    'tx_power': tx_power, 'n_path_loss': n_path_loss,
    'median_window': median_window,
    'kalman_R': kalman_R, 'kalman_Q': kalman_Q,
    'path_update_rate': path_update_rate # Добавляем новый параметр
})

# Однократная загрузка данных и запуск потока
if not st.session_state.app_initialized:
    st.session_state.beacons = load_beacon_positions(BEACONS_FILE)
    if st.session_state.beacons:
        # --- ИЗМЕНЕНО: Передаем в поток ссылку на общий словарь параметров ---
        mqtt_thread = threading.Thread(
            target=mqtt_thread_func,
            args=(st.session_state.beacons, st.session_state.data_queue, st.session_state.runtime_params)
        )
        mqtt_thread.daemon = True
        mqtt_thread.start()
        st.session_state.app_initialized = True
    else:
        st.error("Не удалось загрузить маячки. MQTT-поток не запущен.")

# --- Управление и отображение ---
main_col, data_col = st.columns([3, 1])

with main_col:
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        if st.button("▶️ Начать новый маршрут", use_container_width=True):
            st.session_state.path = []
            st.session_state.live_data = {}
            st.session_state.rssi_history.clear()
            st.session_state.kalman_states.clear()
            st.session_state.recording = True
            st.success("Запись начата!")
    with btn_col2:
        if st.button("⏹️ Завершить маршрут", use_container_width=True):
            st.session_state.recording = False
            st.info("Запись завершена.")
    if not st.session_state.recording and st.session_state.path:
        with btn_col3:
            st.download_button("📥 Скачать маршрут (*.path)",
                               format_path_data_for_download(st.session_state.path),
                               "route.path", use_container_width=True)

    while not st.session_state.data_queue.empty():
        data_from_queue = st.session_state.data_queue.get()
        if data_from_queue.get('live_data'):
            st.session_state.live_data.update(data_from_queue['live_data'])
        if data_from_queue.get('point') and st.session_state.recording:
            st.session_state.path.append(data_from_queue['point'])

    fig, ax = plt.subplots(figsize=(10, 8))
    path_copy = list(st.session_state.path)

    if st.session_state.beacons:
        bx = [p[0] for p in st.session_state.beacons.values()]
        by = [p[1] for p in st.session_state.beacons.values()]
        ax.scatter(bx, by, s=120, c='blue', label='Маячки', zorder=10)
        for name, pos in st.session_state.beacons.items():
            ax.text(pos[0], pos[1] + 0.3, name, fontsize=12, color='darkblue', ha='center')
            if name in st.session_state.live_data:
                filtered_rssi = st.session_state.live_data[name]['filtered_rssi']
                ax.text(pos[0], pos[1] - 1.2, f"RSSI: {filtered_rssi}", fontsize=9, color='gray', ha='center')

    if len(path_copy) > 0:
        px = [p['x'] for p in path_copy]
        py = [p['y'] for p in path_copy]
        ax.plot(px, py, color='green', marker='o', linestyle='-', markersize=4, label="Пройденный путь")
        ax.scatter(px[-1], py[-1], s=180, c='red', edgecolors='black', zorder=5, label='Текущая позиция')

    ax.set_title("Карта"); ax.set_xlabel("X (м)"); ax.set_ylabel("Y (м)")
    ax.grid(True); ax.legend(); ax.axis('equal')
    st.pyplot(fig, clear_figure=True)

with data_col:
    st.subheader("Текущие данные")
    st.dataframe(st.session_state.live_data, use_container_width=True)
    st.subheader("Последние точки пути")
    st.dataframe(path_copy[-10:], use_container_width=True)

# --- ИЗМЕНЕНО: Уменьшена задержка для более плавного интерфейса ---
time.sleep(0.05)
st.rerun()