import paho.mqtt.client as mqtt
import time
import json
import random

MQTT_BROKER = "10.99.15.57"
TOPIC_PUB = "registrar/data"
CLIENT_ID = "esp32-simulator"
BEACON_NAMES = ["beacon_1", "beacon_2", "beacon_3", "beacon_4", "beacon_5", "beacon_6", "beacon_7", "beacon_8"]

def generate_fake_beacon_data():
    found_beacons = {}
    num_beacons_to_see = random.randint(3, 5)
    selected_beacons = random.sample(BEACON_NAMES, num_beacons_to_see)
    for beacon_name in selected_beacons:
        rssi = random.randint(-90, -40)
        found_beacons[beacon_name] = rssi
    return found_beacons

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
try:
    print(f"Подключаемся к MQTT брокеру...")
    client.connect(MQTT_BROKER)
    print("Успешно подключено!")
except Exception as e:
    print(f"Не удалось подключиться: {e}")
    exit()

print("Запуск симулятора. Нажмите Ctrl+C для остановки.")
try:
    # Этот цикл должен работать бесконечно
    while True:
        beacons_data = generate_fake_beacon_data()
        message = json.dumps(beacons_data)
        client.publish(TOPIC_PUB, message)
        print(f"Отправлено: {message}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nОстановка симулятора.")
finally:
    client.disconnect()
    print("Отключено от брокера.")