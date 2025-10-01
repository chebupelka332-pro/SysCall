# Код для ESP32 с поиском по имени
import network
import time
import ubinascii
import machine
import ubluetooth
import json
from umqtt.simple import MQTTClient

# --- Параметры Wi-Fi и MQTT ---
WIFI_SSID = "Pixel 9"
WIFI_PASSWORD = "29052006"
MQTT_BROKER = "10.99.15.57"
MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id())
TOPIC_PUB = b"registrar/data"
TOPIC_SUB = b"registrar/commands"

# --- ИЗМЕНЕНИЕ 1: WHITELIST теперь содержит ИМЕНА маячков ---
# Убедитесь, что ваши маячки действительно передают эти имена
WHITELIST = [
    "beacon_1", "beacon_2", "beacon_3", "beacon_4",
    "beacon_5", "beacon_6", "beacon_7", "beacon_8"
]


# --- Вспомогательная функция для извлечения имени из пакета данных ---
def find_adv_name(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0:
            break
        ad_type = adv_data[i + 1]

        # AD Type 0x09: Complete Local Name
        # AD Type 0x08: Shortened Local Name
        if ad_type == 0x09 or ad_type == 0x08:
            return adv_data[i + 2:i + length + 1].decode('utf-8')

        i += length + 1
    return None


class BLEScanner:
    def __init__(self, ble, whitelist):
        self._ble = ble
        self._ble.active(False)
        self._ble.irq(self._irq)
        self._whitelist = whitelist
        self._found_devices = {}

    def _irq(self, event, data):
        if event == 5:  # _IRQ_SCAN_RESULT
            addr_type, addr, adv_type, rssi, adv_data = data

            # ИЗМЕНЕНИЕ 2: Извлекаем имя из adv_data
            name = find_adv_name(adv_data)

            # Проверяем, что имя найдено и оно есть в нашем белом списке
            if name and name in self._whitelist:
                self._found_devices[name] = rssi

    def scan(self):
        self._found_devices.clear()
        self._ble.active(True)
        self._ble.gap_scan(300, 30000, 30000)
        time.sleep_ms(350)
        self._ble.gap_scan(None)
        self._ble.active(False)

        return self._found_devices.copy()


# --- Функция обратного вызова MQTT (без изменений) ---
def mqtt_callback(topic, msg):
    print(f"Пришло сообщение в топик '{topic.decode()}': {msg.decode()}")


# --- Подключение к Wi-Fi (без изменений) ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print(f"Подключаемся к сети '{WIFI_SSID}'...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    timeout = 15
    start_time = time.time()
    while not wlan.isconnected() and time.time() - start_time < timeout:
        print(".", end="")
        time.sleep(1)

# --- Основная логика ---
if wlan.isconnected():
    print("\nПодключение к Wi-Fi успешно!")
    try:
        ble = ubluetooth.BLE()
        scanner = BLEScanner(ble, WHITELIST)

        client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
        client.set_callback(mqtt_callback)
        client.connect()
        client.subscribe(TOPIC_SUB)
        print("Успешно подключено к MQTT и подписано на топик.")

        while True:
            client.check_msg()
            beacons_data = scanner.scan()

            if beacons_data:
                # ИЗМЕНЕНИЕ 3: Теперь данные уже содержат имена, дополнительное преобразование не нужно
                message = json.dumps(beacons_data)
                client.publish(TOPIC_PUB, message.encode())
                print(f"Отправлено: {message}")
            else:
                print("Маячки из белого списка не найдены.")

            time.sleep_ms(500)

    except Exception as e:
        print(f"Произошла ошибка в работе: {e}")
else:
    print("\nНе удалось подключиться к Wi-Fi.")