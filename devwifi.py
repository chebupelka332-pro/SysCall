# --- ДИАГНОСТИЧЕСКИЙ СКРИПТ ДЛЯ BLE (ИСПРАВЛЕННЫЙ) ---
import ubluetooth
import ubinascii
import time


# Вспомогательная функция для извлечения имени
def find_adv_name(adv_data):
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0:
            break
        ad_type = adv_data[i + 1]
        if ad_type == 0x09 or ad_type == 0x08:
            # ИСПРАВЛЕНИЕ: Преобразуем memoryview в bytes перед .decode()
            name_data_view = adv_data[i + 2:i + length + 1]
            return bytes(name_data_view).decode('utf-8')
        i += length + 1
    return None


# Глобальный флаг, чтобы прерывания не мешали печати
processing = False


def ble_irq(event, data):
    global processing
    if processing:
        return

    if event == 5:  # _IRQ_SCAN_RESULT
        processing = True
        addr_type, addr, adv_type, rssi, adv_data = data

        mac_addr = ubinascii.hexlify(addr).decode().upper()
        name = find_adv_name(adv_data)

        print("----------------------------------------")
        print(f"Найдено устройство:")

        formatted_mac = ':'.join(mac_addr[i:i + 2] for i in range(0, len(mac_addr), 2))
        print(f"  MAC-адрес:      {formatted_mac}")

        print(f"  RSSI:             {rssi}")
        print(f"  Извлеченное имя:  {name}")
        print(f"  Сырые данные (RAW): {adv_data}")
        print("----------------------------------------\n")
        processing = False


# --- Основная часть ---
print("Запуск диагностики BLE... Нажмите Ctrl+C для остановки.")
ble = ubluetooth.BLE()
ble.active(True)
ble.irq(ble_irq)

ble.gap_scan(0, 30000, 30000)

try:
    while True:
        time.sleep_ms(1000)
except KeyboardInterrupt:
    ble.gap_scan(None)
    ble.active(False)
    print("Сканирование остановлено.")