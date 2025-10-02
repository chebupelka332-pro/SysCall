# Финальная версия с разделением на потоки и стабилизирующей паузой
import network
import time
import ubinascii
import machine
import ubluetooth
import json
from umqtt.simple import MQTTClient
import _thread

# --- Настройки (без изменений) ---
WIFI_SSID = "Pixel 9"
WIFI_PASSWORD = "29052006"
MQTT_BROKER = "10.99.15.57"
MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id())
TOPIC_PUB = b"registrar/data"
FREQ = 1.0 # Частота отправки данных в секундах

WHITELIST = [
    "beacon_1", "beacon_2", "beacon_3", "beacon_4",
    "beacon_5", "beacon_6", "beacon_7", "beacon_8"
]

# --- Общие ресурсы для потоков ---
SHARED_QUEUE = []
QUEUE_LOCK = _thread.allocate_lock()


# --- Вспомогательные функции и классы (без изменений) ---
def find_adv_name(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0: break
        ad_type = adv_data[i + 1]
        if ad_type == 0x09 or ad_type == 0x08:
            name_data_view = adv_data[i + 2:i + length + 1]
            return bytes(name_data_view).decode('utf-8').strip()
        i += length + 1
    return None


class BLEScanner:
    def __init__(self, ble, whitelist):
        self._ble = ble
        self._ble.active(True)
        self._whitelist = whitelist
        self._found_devices = {}
        self._ble.irq(self._irq)

    def _irq(self, event, data):
        if event == 5:
            addr_type, addr, adv_type, rssi, adv_data = data
            name = find_adv_name(adv_data)
            if name and name in self._whitelist:
                self._found_devices[name] = rssi

    def get_results_and_clear(self):
        results = self._found_devices.copy()
        self._found_devices.clear()
        return results

    def start_scan(self):
        self._ble.gap_scan(0, 80000, 40000)


# --- Код для фонового потока (сканирование BLE) ---
def ble_scanner_thread():
    print("[BLE Thread] Поток сканирования запущен.")
    ble = ubluetooth.BLE()
    scanner = BLEScanner(ble, WHITELIST)

    scanner.start_scan()
    while True:
        time.sleep(1 / FREQ)
        beacons_data = scanner.get_results_and_clear()
        if beacons_data:
            with QUEUE_LOCK:
                SHARED_QUEUE.append(beacons_data)


# --- Основной поток (Wi-Fi и MQTT) ---
# 1. Подключаемся к Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print(f"[Main Thread] Подключаемся к сети '{WIFI_SSID}'...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    timeout = 15;
    start_time = time.time()
    while not wlan.isconnected() and time.time() - start_time < timeout:
        print(".", end="");
        time.sleep(1)

if wlan.isconnected():
    print(f"\n[Main Thread] Wi-Fi подключен! IP: {wlan.ifconfig()[0]}")

    # --- ИСПРАВЛЕНИЕ: ДОБАВЛЕНА ПАУЗА ДЛЯ СТАБИЛИЗАЦИИ СЕТИ ---
    print("[Main Thread] Пауза для стабилизации Wi-Fi соединения...")
    time.sleep(2)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    try:
        # 2. Подключаемся к MQTT
        client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, keepalive=60)
        print("[Main Thread] Подключаемся к MQTT брокеру...")
        client.connect()
        print("[Main Thread] MQTT подключен.")

        # 3. Запускаем фоновый поток для сканирования BLE
        _thread.start_new_thread(ble_scanner_thread, ())

        print("[Main Thread] Запуск основного цикла...")
        while True:
            data_to_send = None
            with QUEUE_LOCK:
                if SHARED_QUEUE:
                    data_to_send = SHARED_QUEUE.pop(0)

            if data_to_send:
                message = json.dumps(data_to_send)
                client.publish(TOPIC_PUB, message.encode())
                print(f"[Main Thread] Отправлено: {message}")

            client.check_msg()
            #time.sleep(0.1)

    except Exception as e:
        print(f"[Main Thread] Произошла ошибка в работе: {e}")
else:
    print("\n[Main Thread] Не удалось подключиться к Wi-Fi.")