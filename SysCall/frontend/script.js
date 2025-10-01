// frontend/script.js

// --- Настройки ---
// Убедись, что IP и порт совпадают с твоим бэкендом
const BACKEND_URL = 'http://127.0.0.1:5000'; // Используй IP-адрес бэкенда, если он на другой машине

// Масштабный коэффициент. Подбери его так, чтобы карта помещалась на холсте.
// Если координаты маячков большие (например, 50 метров), коэффициент нужен маленький (например, 10).
// Если координаты маленькие (например, 5 метров), коэффициент нужен большой (например, 50).
const SCALE = 15;
// Смещение, чтобы карта рисовалась не с самого края, а с отступом
const OFFSET_X = 100;
const OFFSET_Y = 100;


// --- Получение элементов со страницы ---
const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const coordsSpan = document.getElementById('coords');

// --- Глобальные переменные для хранения состояния ---
let beacons = [];
let userPosition = { x: 0, y: 0 };
let route = [];
const floorPlan = new Image();
floorPlan.src = 'floor_plan.png'; // Убедись, что картинка лежит рядом


// --- Функции для рисования ---

// Функция для преобразования координат из метров в пиксели на холсте
function transformCoords(point) {
    return {
        x: point.x * SCALE + OFFSET_X,
        y: point.y * SCALE + OFFSET_Y,
    };
}

// Главная функция отрисовки
function draw() {
    // Очищаем холст
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Рисуем фон (план этажа)
    ctx.drawImage(floorPlan, 0, 0, canvas.width, canvas.height);

    // Рисуем маячки (синие квадраты)
    beacons.forEach(beacon => {
        const pos = transformCoords(beacon);
        ctx.fillStyle = 'rgba(0, 0, 255, 0.7)';
        ctx.fillRect(pos.x - 5, pos.y - 5, 10, 10);
        ctx.fillStyle = 'black';
        ctx.fillText(beacon.name, pos.x + 8, pos.y + 4);
    });

    // Рисуем маршрут (зеленая линия)
    if (route.length > 1) {
        ctx.strokeStyle = 'rgba(0, 200, 0, 0.8)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        let startPoint = transformCoords(route[0]);
        ctx.moveTo(startPoint.x, startPoint.y);
        for (let i = 1; i < route.length; i++) {
            let nextPoint = transformCoords(route[i]);
            ctx.lineTo(nextPoint.x, nextPoint.y);
        }
        ctx.stroke();
    }

    // Рисуем позицию пользователя (красный круг)
    const userPos = transformCoords(userPosition);
    ctx.fillStyle = 'rgba(255, 0, 0, 0.9)';
    ctx.beginPath();
    ctx.arc(userPos.x, userPos.y, 8, 0, 2 * Math.PI);
    ctx.fill();

    // Обновляем текст с координатами
    coordsSpan.textContent = `X: ${userPosition.x.toFixed(2)}, Y: ${userPosition.y.toFixed(2)}`;
}

// --- Функции для работы с API ---

// Получаем актуальную позицию с сервера
async function fetchPosition() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/current_position`);
        if (!response.ok) throw new Error('Network response was not ok');
        userPosition = await response.json();
    } catch (error) {
        console.error("Failed to fetch position:", error);
    }
}

// Запрашиваем построение маршрута
async function fetchRoute(endPoint) {
    try {
        const response = await fetch(`${BACKEND_URL}/api/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ end_point: endPoint }),
        });
        if (!response.ok) throw new Error('Network response was not ok');
        route = await response.json();
    } catch (error) {
        console.error("Failed to fetch route:", error);
    }
}


// --- Инициализация и основной цикл ---

// Функция, которая запускается при загрузке страницы
async function initialize() {
    // 1. Загружаем данные о маячках
    try {
        const response = await fetch(`${BACKEND_URL}/api/beacons`);
        if (!response.ok) throw new Error('Failed to load beacons');
        beacons = await response.json();
    } catch (error) {
        console.error(error);
        alert("Не удалось загрузить данные о маячках. Убедитесь, что бэкенд запущен.");
    }

    // 2. Запускаем основной цикл обновления
    setInterval(async () => {
        await fetchPosition();
        draw(); // Перерисовываем всё после получения новых данных
    }, 1000); // Обновляем раз в секунду
}

// Обработчик клика по холсту для построения маршрута
canvas.addEventListener('click', (event) => {
    const rect = canvas.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Преобразуем пиксели обратно в метры
    const targetPoint = {
        x: (clickX - OFFSET_X) / SCALE,
        y: (clickY - OFFSET_Y) / SCALE,
    };

    console.log(`Route requested to:`, targetPoint);
    fetchRoute(targetPoint);
});

// Ждем, пока загрузится изображение плана, и только потом запускаем инициализацию
floorPlan.onload = () => {
    initialize();
};
floorPlan.onerror = () => {
    console.error("Floor plan image not found or failed to load. Continuing without it.");
    initialize();
}