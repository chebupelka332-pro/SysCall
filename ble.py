import bluetooth
import time


# A class for convenient BLE operations
class BLEScanner:
    def __init__(self, ble):
        self._ble = ble
        self._ble.active(True)  # Activate the Bluetooth interface
        self._ble.irq(self._irq)  # Register the event handler
        self._found_devices = {}

    # Bluetooth event handler
    def _irq(self, event, data):
        # If a new device is found as a result of the scan
        if event == 5:  # _IRQ_SCAN_RESULT
            addr_type, addr, adv_type, rssi, adv_data = data
            # Convert the address to a readable format
            addr_str = ':'.join(['%02x' % b for b in addr])

            # Try to get the device name from the advertising data
            name = self.decode_name(adv_data) or "N/A"

            # Add the device to the dictionary to avoid duplicates
            # and print info only about new devices
            if addr_str not in self._found_devices:
                print(f"Found: MAC={addr_str}, RSSI={rssi}, Name='{name}'")
                self._found_devices[addr_str] = name

    # Function to decode the name from the advertising packet
    def decode_name(self, payload):
        n = 0
        while n + 1 < len(payload):
            try:
                length = payload[n]
                if length == 0:
                    break
                ad_type = payload[n + 1]

                # 0x09 - "Complete Local Name", 0x08 - "Shortened Local Name"
                if ad_type == 0x09 or ad_type == 0x08:
                    return bytes(payload[n + 2: n + 2 + length - 1]).decode('utf-8')

                n += 1 + length
            except (IndexError, UnicodeError):
                # If the packet is corrupted, just break
                break
        return None

    # Start scanning
    def scan(self, duration_s=10):
        print(f"--- Starting Bluetooth scan for {duration_s} seconds ---")
        self._found_devices.clear()
        self._ble.gap_scan(duration_s * 1000, 30000, 30000)

        # Wait for the scan to complete
        time.sleep(duration_s)
        self._ble.gap_scan(None)  # Stop scanning

        print(f"--- Scan complete. Found {len(self._found_devices)} unique devices. ---")



ble = bluetooth.BLE()  # Initialize the Bluetooth object
scanner = BLEScanner(ble)  # Create our scanner
scanner.scan(10)  # Start scanning for 10 seconds