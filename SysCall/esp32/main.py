# main.py
import network
import time
import config
from api_client import APIClient
from ble_scanner import BLEScanner


def connect_wifi(ssid, password):
    """Функция для подключения к Wi-Fi."""
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print(f"Connecting to network '{ssid}'...")
        sta_if.active(True)
        sta_if.connect(ssid, password)
        # Ждем подключения
        max_wait = 15
        while not sta_if.isconnected() and max_wait > 0:
            print(".", end="")
            time.sleep(1)
            max_wait -= 1

        if not sta_if.isconnected():
            print("\nFailed to connect to WiFi.")
            return None

    print("\nWiFi connected! Network config:", sta_if.ifconfig())
    return sta_if


# --- Старт программы ---

# 1. Подключаемся к Wi-Fi
wifi = connect_wifi(config.WIFI_SSID, config.WIFI_PASSWORD)
if not wifi:
    # Если не удалось подключиться, программа не сможет работать
    print("Stopping execution.")
else:
    # 2. Инициализируем наши модули
    api = APIClient(config.BACKEND_URL)
    scanner = BLEScanner(config.BEACON_NAME_PREFIX)

    # Рассчитываем период ожидания между циклами
    sleep_period_s = 1 / config.SCAN_FREQUENCY_HZ

    print("\n--- Starting main loop ---")

    while True:
        try:
            # --- Фаза 1: Активен Bluetooth ---
            print("\nScanning for beacons...")
            found_beacons = scanner.scan(config.SCAN_DURATION_MS)

            # --- Фаза 2: Активен Wi-Fi ---
            if found_beacons:
                print(f"Found {len(found_beacons)}, sending to server...")
                payload = [{"name": name, "rssi": rssi} for name, rssi in found_beacons.items()]
                response = api.send_scan_data(payload)

                if response and 'position' in response:
                    pos = response['position']
                    print(f"--> Calculated position: X={pos['x']}, Y={pos['y']}")
                else:
                    print("--> Failed to get position from server.")
            else:
                print("No beacons found.")

            # --- Фаза 3: Отдых (ОЧЕНЬ ВАЖНО!) ---
            # Даем время стеку Wi-Fi и другим системным задачам поработать.
            period_ms = 1000 / config.SCAN_FREQUENCY_HZ
            # Простой, но надежный способ сделать паузу
            time.sleep_ms(int(period_ms - config.SCAN_DURATION_MS))

        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            time.sleep(5)