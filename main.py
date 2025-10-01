from machine import Pin
import time

# Указываем, что светодиод подключен к GPIO 35 и это выход (OUT)
led = Pin(35, Pin.OUT)

# Бесконечный цикл для мигания
while True:
    led.on()         # Включаем светодиод
    time.sleep(0.5)  # Ждем 0.5 секунды
    led.off()        # Выключаем светодиод
    time.sleep(0.5)  # Ждем еще 0.5 секунды
    print("I'm blinking!")

