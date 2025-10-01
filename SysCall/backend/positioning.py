# positioning.py
import numpy as np
from scipy.optimize import minimize

# --- Константы для перевода RSSI в метры ---
# Эти значения нужно подбирать экспериментально для твоих маячков и помещения,
# но для хакатона эти - хорошая отправная точка.
A = -60  # "Эталонное" RSSI на расстоянии 1 метр
N = 2.5  # Коэффициент затухания сигнала (2.0-4.0)


def rssi_to_distance(rssi):
    """Преобразует значение RSSI в расстояние в метрах."""
    return 10 ** ((A - rssi) / (10 * N))


class PositionCalculator:
    def __init__(self, beacons_map):
        # beacons_map - это словарь вида {'beacon_1': {'x': 3.0, 'y': -2.4}, ...}
        self.beacons_map = beacons_map
        self.beacon_coords = np.array([[b['x'], b['y']] for b in beacons_map.values()])
        self.beacon_names = list(beacons_map.keys())

    def calculate_position(self, scan_data):
        """
        Вычисляет позицию (x, y) на основе данных сканирования.
        scan_data - список словарей: [{'name': 'beacon_1', 'rssi': -65}, ...]
        """

        # Фильтруем данные: оставляем только известные маячки и их расстояния
        distances = []
        coords = []

        for scan in scan_data:
            name = scan.get('name')
            rssi = scan.get('rssi')
            if name in self.beacons_map:
                dist = rssi_to_distance(rssi)
                distances.append(dist)
                coords.append([self.beacons_map[name]['x'], self.beacons_map[name]['y']])

        # Для трилатерации нужно минимум 3 маячка
        if len(distances) < 3:
            print(f"Not enough beacons to calculate position. Found: {len(distances)}")
            return None

        distances = np.array(distances)
        coords = np.array(coords)

        # Функция ошибки, которую мы будем минимизировать.
        # Она считает сумму квадратов разниц между реальным расстоянием (из RSSI)
        # и расчетным расстоянием от предполагаемой точки (x,y) до каждого маячка.
        def error_function(point, beacon_coords, measured_distances):
            x, y = point
            calculated_distances = np.sqrt(np.sum((beacon_coords - [x, y]) ** 2, axis=1))
            return np.sum((calculated_distances - measured_distances) ** 2)

        # Начальное предположение для нашей позиции (например, среднее всех маячков)
        initial_guess = np.mean(coords, axis=0)

        # Запускаем оптимизатор для поиска точки (x, y), минимизирующей ошибку
        result = minimize(
            error_function,
            initial_guess,
            args=(coords, distances),
            method='L-BFGS-B'
        )

        if result.success:
            return {'x': result.x[0], 'y': result.x[1]}
        else:
            print("Position calculation failed.")
            return None