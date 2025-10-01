import network
import time
from umqtt.simple import MQTTClient
import ubinascii
import machine

# --- Параметры для Wi-Fi ---
WIFI_SSID = "Pixel 9"
WIFI_PASSWORD = "29052006"

# --- Параметры для MQTT ---
# IP-адрес компьютера, где запущен брокер (Mosquitto). Узнайте через ipconfig.
MQTT_BROKER = "10.99.15.57"  # ЗАМЕНИТЕ НА ВАШ IP-АДРЕС
# Уникальный ID клиента. Лучше использовать что-то уникальное, например, MAC-адрес платы.
MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id())
# Топик, в который плата будет отправлять данные (например, данные с сенсоров)
TOPIC_PUB = b"registrar/data"
# Топик, на который плата подпишется, чтобы получать команды от сервера
TOPIC_SUB = b"registrar/commands"


# --- Функция обратного вызова для входящих MQTT сообщений ---
# Эта функция будет автоматически вызываться, когда в топик TOPIC_SUB придет сообщение
def mqtt_callback(topic, msg):
    print(f"Пришло сообщение в топик '{topic.decode()}': {msg.decode()}")
    # Здесь можно добавить логику обработки команд, например, включить светодиод
    if msg == b"ping":
        print("Получена команда PING!")


# --- Инициализация Wi-Fi ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASSWORD)

# --- Подключение к Wi-Fi ---
print(f"Подключаемся к сети '{WIFI_SSID}'...")
timeout = 15
start_time = time.time()
while not wlan.isconnected() and time.time() - start_time < timeout:
    print(".", end="")
    time.sleep(1)

# --- Основная логика после подключения ---
if wlan.isconnected():
    print("\nПодключение к Wi-Fi успешно!")
    print("Параметры сети:", wlan.ifconfig())

    # --- Подключение к MQTT брокеру ---
    print(f"Подключаемся к MQTT брокеру по адресу {MQTT_BROKER}...")
    try:
        client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
        client.set_callback(mqtt_callback)  # Регистрируем функцию обратного вызова
        client.connect()
        print("Успешно подключено к MQTT брокеру!")

        # Подписываемся на топик для получения команд
        client.subscribe(TOPIC_SUB)
        print(f"Подписались на топик '{TOPIC_SUB.decode()}'")

        # --- Основной цикл отправки данных ---
        counter = 0
        while True:
            # Проверяем, есть ли входящие сообщения
            client.check_msg()

            # Готовим сообщение для отправки
            # ПОЗЖЕ ЗДЕСЬ БУДУТ ДАННЫЕ С BLE-МАЯЧКОВ
            message = f"Hello from ESP32! Count: {counter}"

            # Отправляем (публикуем) сообщение в топик
            client.publish(TOPIC_PUB, message.encode())
            print(f"Отправлено в '{TOPIC_PUB.decode()}': '{message}'")

            counter += 1
            time.sleep(2)  # Пауза 2 секунды

    except Exception as e:
        print(f"Не удалось подключиться или произошла ошибка в работе MQTT: {e}")

else:
    print("\nНе удалось подключиться к Wi-Fi.")