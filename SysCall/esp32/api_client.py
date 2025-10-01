import urequests
import ujson


class APIClient:
    """Класс для удобного общения с API бэкенда."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.headers = {'Content-Type': 'application/json'}

    def _request(self, method, endpoint, data=None):
        """Приватный метод для выполнения HTTP запросов."""
        url = f"{self.base_url}{endpoint}"
        try:
            if data:
                response = urequests.request(
                    method, url, data=ujson.dumps(data), headers=self.headers
                )
            else:
                response = urequests.request(method, url, headers=self.headers)

            # Проверяем успешность запроса
            if 200 <= response.status_code < 300:
                return response.json()
            else:
                print(f"Error: Received status {response.status_code} from {url}")
                response.close()
                return None
        except OSError as e:
            print(f"Network error: {e}")
            return None

    def get_beacons(self):
        """Получает список всех маячков и их координат с сервера."""
        print("Requesting beacon list from server...")
        return self._request("GET", "/api/beacons")

    def send_scan_data(self, scan_payload):
        """Отправляет данные сканирования на сервер и получает текущую позицию."""
        print(f"Sending scan data to server: {scan_payload}")
        return self._request("POST", "/api/position", data={"scans": scan_payload})