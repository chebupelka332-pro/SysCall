# ble_scanner.py
import ubluetooth
import time
from micropython import const

# Константы для парсинга BLE-пакетов
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_ADV_TYPE_NAME = const(0x09)


class BLEScanner:
    """Класс для сканирования и фильтрации BLE-маячков."""

    def __init__(self, beacon_name_prefix="beacon_"):
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.beacon_name_prefix = beacon_name_prefix
        self.found_devices = {}
        self.scan_in_progress = False

    def _irq(self, event, data):
        """Обработчик прерываний от BLE-стека."""
        if event == _IRQ_SCAN_RESULT:
            addr, addr_type, adv_type, rssi, adv_data = data

            # Пытаемся декодировать имя устройства из рекламного пакета
            device_name = self._decode_name(adv_data)

            if device_name and device_name.startswith(self.beacon_name_prefix):
                # Если это наш маячок, сохраняем его имя и RSSI
                # Используем имя как ключ, чтобы избежать дубликатов за одно сканирование
                self.found_devices[device_name] = rssi

        elif event == _IRQ_SCAN_DONE:
            # Сканирование завершено
            self.scan_in_progress = False

    def _decode_name(self, payload):
        """Извлекает имя устройства из сырых данных рекламного пакета."""
        i = 0
        while i < len(payload):
            length, adv_type = payload[i], payload[i + 1]
            if adv_type == _ADV_TYPE_NAME:
                return bytes(payload[i + 2: i + length + 1]).decode("utf-8")
            i += length + 1
        return None

    def scan(self, duration_ms):
        """Запускает сканирование на заданное время и возвращает найденные устройства."""
        self.found_devices.clear()
        self.scan_in_progress = True

        # Запускаем сканирование (в мс, интервал и окно в мкс)
        self.ble.gap_scan(duration_ms, 30000, 30000)

        # Ждем завершения сканирования
        while self.scan_in_progress:
            time.sleep_ms(50)

        return self.found_devices