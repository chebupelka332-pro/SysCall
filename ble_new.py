import bluetooth
import time


WHITELIST = {
    "88:57:21:23:34:C8": "beacon_1",
    "84:1F:E8:09:88:94": "beacon_2",
    "84:1F:E8:45:49:8C": "beacon_3",
    "88:57:21:23:3D:D4": "beacon_4",
    "88:57:21:23:50:44": "beacon_5",
    "88:57:21:23:3F:6C": "beacon_6",
    "4C:C3:82:C4:27:A8": "beacon_7",
    "84:1F:E8:44:CD:28": "beacon_8"
}


class BLEScanner:
    def __init__(self, ble, whitelist):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._whitelist = whitelist
        self._found_devices = set()

    def _irq(self, event, data):
        if event == 5:
            addr_type, addr, adv_type, rssi, adv_data = data

            addr_str = ':'.join(['%02X' % b for b in addr])

            if addr_str in self._whitelist and addr_str not in self._found_devices:
                device_name = self._whitelist[addr_str]
                print(f"Found: Name={device_name}, MAC={addr_str}, RSSI={rssi}")
                self._found_devices.add(addr_str)

    def scan(self, duration_s=10):
        print(f"--- Starting scan for whitelisted devices for {duration_s} seconds ---")
        self._found_devices.clear()
        self._ble.gap_scan(duration_s * 1000, 30000, 30000)

        time.sleep(duration_s)
        self._ble.gap_scan(None)

        print(f"--- Scan complete. Found {len(self._found_devices)} whitelisted device(s). ---")



ble = bluetooth.BLE()
scanner = BLEScanner(ble, WHITELIST)
scanner.scan(15)