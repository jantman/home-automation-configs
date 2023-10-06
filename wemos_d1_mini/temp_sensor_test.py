"""
Temperature sensor circuit test
"""


import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from machine import Pin, I2C
from time import sleep, sleep_ms
from bme280 import BME280
from aht import AHT2x
from sht31 import SHT31

# Pin mappings - board number to GPIO number
SDA = micropython.const(19)  # 30-pin ESP32 D21 / GPIO21 / SDA
SCL = micropython.const(18)  # 30-pin ESP32 D22 / GPIO22 / SCL


class TempSensorTester(HassSender):

    SENSORS = {
        118: 'bme280',
        56: 'aht21',
        68: 'sht31d'
    }

    def __init__(self):
        super().__init__()
        printflush("Initializing i2c...")
        self.i2c = I2C(
            scl=Pin(SCL, mode=Pin.IN, pull=Pin.PULL_UP),
            sda=Pin(SDA, mode=Pin.IN, pull=Pin.PULL_UP)
        )
        printflush("Initializing BME280...")
        self.bme280 = BME280(i2c=self.i2c)
        printflush("Initializing AHT21...")
        self.aht21 = AHT2x(self.i2c, crc=True)
        printflush("Initializing SHT31...")
        self.sht31 = SHT31(self.i2c)
        printflush("Done initializing.")

    def run(self):
        printflush("Enter loop...")
        while True:
            messages = []
            printflush("Read BME280")
            values = self.bme280.read_compensated_data()
            messages.append({
                'path': '/api/states/sensor.test_bme280temp',
                'data_dict': {
                    'state': round(values[0], 2),
                    'attributes': {
                        'friendly_name': 'Test BME280 Temperature',
                        'unit_of_measurement': '\u00b0C'
                    }
                }
            })
            messages.append({
                'path': '/api/states/sensor.test_bme280humidity',
                'data_dict': {
                    'state': round(values[2], 2),
                    'attributes': {
                        'friendly_name': 'Test BME280 Humidity',
                        'unit_of_measurement': '%'
                    }
                }
            })
            while not self.aht21.is_ready:
                sleep_ms(100)
            messages.append({
                'path': '/api/states/sensor.test_aht21temp',
                'data_dict': {
                    'state': round(self.aht21.temperature, 2),
                    'attributes': {
                        'friendly_name': 'Test AHT21 Temperature',
                        'unit_of_measurement': '\u00b0C'
                    }
                }
            })
            messages.append({
                'path': '/api/states/sensor.test_aht21humidity',
                'data_dict': {
                    'state': round(self.aht21.humidity, 2),
                    'attributes': {
                        'friendly_name': 'Test AHT21 Humidity',
                        'unit_of_measurement': '%'
                    }
                }
            })
            temp, humi = self.sht31.get_temp_humi()
            messages.append({
                'path': '/api/states/sensor.test_sht31temp',
                'data_dict': {
                    'state': round(temp, 2),
                    'attributes': {
                        'friendly_name': 'Test SHT31 Temperature',
                        'unit_of_measurement': '\u00b0C'
                    }
                }
            })
            messages.append({
                'path': '/api/states/sensor.test_sht31humidity',
                'data_dict': {
                    'state': round(humi, 2),
                    'attributes': {
                        'friendly_name': 'Test SHT31 Humidity',
                        'unit_of_measurement': '%'
                    }
                }
            })
            printflush("Sending data...")
            for item in messages:
                print(item)
                self.http_post(**item)
            sleep(60)


if __name__ == '__main__':
    TempSensorTester().run()
