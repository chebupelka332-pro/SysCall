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
if 'live_data' not in st.session_state: st.session_state.live_data = {}  # {beacon_name: {'raw_rssi': X, 'filtered_rssi': Y}}
if 'recording' not in st.session_state: st.session_state.recording = False
if 'app_initialized' not in st.session_state: st.session_state.app_initialized = False


# Хранит последние N значений RSSI для медианного фильтра
if 'rssi_history' not in st.session_state:
    st.session_state.rssi_history = {}
# Хранит состояние (оценку и ковариацию ошибки) для фильтра Калмана по каждому маячку
if 'kalman_states' not in st.session_state:
    st.session_state.kalman_states = {}

# --- 3. ПАНЕЛЬ УПРАВЛЕНИЯ И КАЛИБРОВКИ (ШАГ 1) ---
st.sidebar.title("Параметры системы")
st.sidebar.markdown("### Шаг 1: Калибровка")
st.sidebar.info(
    "Измерьте RSSI на 1 метре, чтобы найти `A (Tx Power)`. Затем измерьте на 2, 3, 4 метрах, чтобы подобрать `n`.")
# Параметр A: мощность сигнала на расстоянии 1 метр.
tx_power = st.sidebar.slider("A (Tx Power)", -100.0, -20.0, -46.5, 0.5)
# Параметр n: коэффициент затухания сигнала в среде.
n_path_loss = st.sidebar.slider("n (Path Loss Exponent)", 1.0, 5.0, 2.0, 0.1)

st.sidebar.markdown("### Шаг 2: Настройка фильтров")
# Размер окна для медианного фильтра
median_window = st.sidebar.slider("Окно медианного фильтра", 3, 70, 25, 1)
# Шум измерения (R) для Калмана: насколько мы "не доверяем" новым данным. Больше R -> более плавный, но инертный путь.
kalman_R = st.sidebar.slider("Шум измерения (R)", 0.01, 1.0, 0.7, 0.01)
# Шум процесса (Q) для Калмана: как сильно может измениться "истинное" значение между измерениями. Больше Q -> быстрее реакция на изменения.
kalman_Q = st.sidebar.slider("Шум процесса (Q)", 0.0001, 0.1, 0.005, 0.0001)


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
    # Предсказание
    x_pred = state['x']
    P_pred = state['P'] + Q
    # Обновление
    K = P_pred / (P_pred + R)  # Коэффициент Калмана
    x_new = x_pred + K * (measurement - x_pred)
    P_new = (1 - K) * P_pred
    return {'x': x_new, 'P': P_new}, x_new


# --- 5. ЛОГИКА MQTT В ФОНОВОМ ПОТОКЕ (с фильтрацией) ---


def on_message(client, userdata, msg):
    """Вызывается при получении данных от MQTT. Обрабатывает и фильтрует RSSI."""
    try:
        # --- ЗАЩИТА ОТ "СОСТОЯНИЯ ГОНКИ" ---
        # Гарантируем, что словари для фильтров существуют в session_state,
        # даже если этот поток запустился раньше, чем основной поток их создал.
        if 'rssi_history' not in st.session_state:
            st.session_state.rssi_history = {}
        if 'kalman_states' not in st.session_state:
            st.session_state.kalman_states = {}
        # --- КОНЕЦ ЗАЩИТЫ ---

        # Извлекаем общие ресурсы из userdata
        beacons_positions = userdata['beacons']
        data_queue = userdata['queue']
        params = userdata['params']

        raw_rssi_data = json.loads(msg.payload.decode())

        # --- ЭТАП ФИЛЬТРАЦИИ (ШАГ 2) ---
        filtered_rssi_map = {}
        live_data_update = {}

        for name, rssi in raw_rssi_data.items():
            if name not in beacons_positions:
                continue

            # 1. Инициализация хранилищ при первом появлении маячка
            if name not in st.session_state.rssi_history:
                st.session_state.rssi_history[name] = deque(maxlen=params['median_window'])
                st.session_state.kalman_states[name] = {'x': float(rssi), 'P': 1.0}

            # 2. Обновляем окно для медианного фильтра
            st.session_state.rssi_history[name].append(rssi)

            # 3. Применяем медианный фильтр
            median_filtered_rssi = np.median(list(st.session_state.rssi_history[name]))

            # 4. Применяем фильтр Калмана
            kalman_state = st.session_state.kalman_states[name]
            new_state, kalman_filtered_rssi = update_kalman_filter(
                kalman_state, median_filtered_rssi, params['kalman_R'], params['kalman_Q']
            )
            st.session_state.kalman_states[name] = new_state

            filtered_rssi_map[name] = kalman_filtered_rssi
            live_data_update[name] = {'raw_rssi': rssi, 'filtered_rssi': round(kalman_filtered_rssi, 2)}

        # --- ЭТАП МУЛЬТИЛАТЕРАЦИИ (ШАГ 3) ---
        N_BEST_BEACONS = 3

        # 2. Сортируем все доступные маячки по силе их отфильтрованного сигнала (от сильного к слабому)
        # filtered_rssi_map имеет вид {'beacon_name': rssi_value}
        sorted_beacons = sorted(filtered_rssi_map.items(), key=lambda item: item[1], reverse=True)

        # 3. Берем только N лучших из отсортированного списка
        top_n_beacons = dict(sorted_beacons[:N_BEST_BEACONS])

        beacons_for_calc = {}
        for name, filtered_rssi in top_n_beacons.items():
            if name in beacons_positions:
                distance = rssi_to_distance(filtered_rssi, params['tx_power'], params['n_path_loss'])
                bx, by = beacons_positions[name]
                beacons_for_calc[name] = (bx, by, distance)

        # Используем 4+ маячка для повышения точности
        if len(beacons_for_calc) < 3:
            # Обновляем RSSI в интерфейсе, даже если точку не считаем
            data_queue.put({'point': None, 'live_data': live_data_update})
            return

        # Запускаем оптимизатор для поиска лучшей точки (Метод Наименьших Квадратов)
        result = minimize(error_function, np.array([0.0, 0.0]), args=(beacons_for_calc,), method='L-BFGS-B')

        if result.success:
            new_point = {'x': result.x[0], 'y': result.x[1]}
            data_to_queue = {'point': new_point, 'live_data': live_data_update}
            data_queue.put(data_to_queue)

    except Exception as e:
        print(f"Ошибка в MQTT-потоке: {e}")


def mqtt_thread_func(beacon_positions, data_queue, params):
    """Функция, которая запускает MQTT-клиент в отдельном потоке."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.user_data_set({'beacons': beacon_positions, 'queue': data_queue, 'params': params})
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

# Однократная загрузка данных и запуск потока
if not st.session_state.app_initialized:
    st.session_state.beacons = load_beacon_positions(BEACONS_FILE)
    if st.session_state.beacons:
        # Собираем все настраиваемые параметры для передачи в поток
        runtime_params = {
            'tx_power': tx_power, 'n_path_loss': n_path_loss,
            'median_window': median_window,
            'kalman_R': kalman_R, 'kalman_Q': kalman_Q
        }
        mqtt_thread = threading.Thread(
            target=mqtt_thread_func,
            args=(st.session_state.beacons, st.session_state.data_queue, runtime_params)
        )
        mqtt_thread.daemon = True
        mqtt_thread.start()
        st.session_state.app_initialized = True
    else:
        st.error("Не удалось загрузить маячки. MQTT-поток не запущен.")

# --- Управление и отображение ---
main_col, data_col = st.columns([3, 1])

with main_col:
    # Кнопки управления
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        if st.button("▶️ Начать новый маршрут", use_container_width=True):
            st.session_state.path = []
            st.session_state.live_data = {}
            # Сбрасываем фильтры при старте новой записи
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

    # Обновление данных из очереди MQTT
    while not st.session_state.data_queue.empty():
        data_from_queue = st.session_state.data_queue.get()
        # Обновляем живые данные RSSI всегда
        if data_from_queue.get('live_data'):
            st.session_state.live_data.update(data_from_queue['live_data'])
        # Добавляем точку в путь, только если она была рассчитана и идет запись
        if data_from_queue.get('point') and st.session_state.recording:
            st.session_state.path.append(data_from_queue['point'])

    # Отрисовка карты
    fig, ax = plt.subplots(figsize=(10, 8))
    path_copy = list(st.session_state.path)

    # Рисуем маячки и их RSSI
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

    ax.set_title("Карта");
    ax.set_xlabel("X (м)");
    ax.set_ylabel("Y (м)")
    ax.grid(True);
    ax.legend();
    ax.axis('equal')
    st.pyplot(fig, clear_figure=True)

with data_col:
    st.subheader("Текущие данные")
    st.dataframe(st.session_state.live_data, use_container_width=True)

    st.subheader("Последние точки пути")
    st.dataframe(path_copy[-10:], use_container_width=True)


time.sleep(0.5)
st.rerun()