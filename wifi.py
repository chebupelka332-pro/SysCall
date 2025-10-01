import network
from umqtt.simple import MQTTClient
import time

# --- Параметры для сети WPA2-Enterprise ---
WIFI_SSID = "eduroam"  # Например, 'eduroam'
WIFI_USERNAME = "d.muruev@g.nsu.ru"  # Ваш логин, например, 'student_login@university.com'
WIFI_PASSWORD = "Denis2006"  # Ваш пароль

# --- Параметры MQTT (остаются без изменений) ---
MQTT_BROKER = "ip_address_of_broker"
MQTT_CLIENT_ID = "registrar_device_1"
# ... остальные параметры MQTT

# --- Подключение к Wi-Fi (WPA2-Enterprise) ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# Проверяем, не подключены ли мы уже
if not wlan.isconnected():
    print(f"Connecting to network '{WIFI_SSID}'...")
    # Используем специальные параметры для WPA2-Enterprise
    wlan.connect(WIFI_SSID, key=WIFI_PASSWORD, identity=WIFI_USERNAME)

    # Ждем подключения
    timeout = 15  # Таймаут в секундах
    start_time = time.time()
    while not wlan.isconnected() and time.time() - start_time < timeout:
        print(".", end="")
        time.sleep(1)

# Проверяем результат
if wlan.isconnected():
    print("\nConnected to Wi-Fi!")
    print("Network config:", wlan.ifconfig())
    # --- Далее идет код подключения к MQTT брокеру, как и в предыдущем ответе ---
    # client = MQTTClient(...)
    # client.connect()
    # print("Connected to MQTT Broker")
else:
    print("\nFailed to connect to Wi-Fi.")
    # Здесь можно добавить логику перезагрузки или повторной попытки