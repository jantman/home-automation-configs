"""
Skeleton of a script for reading a sensor and sending the result to HomeAssistant.
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

from machine import Pin, I2C, WDT
from hass_sender import printflush
import adafruit_shtc3
from time import sleep
try:
    import struct
except ImportError:
    import ustruct as struct


class Shtc3Tester:

    def __init__(self):
        self.wdt = WDT(timeout=40000)  # 40-second watchdog timer
        printflush("Initializing i2c...")
        self.i2c = I2C(0, freq=100000)  # ESP32 hardware I2C 0 - SCL on D18, SDA on D19
        printflush('Scanning I2C bus...')
        devices = self.i2c.scan()
        printflush('I2C scan results: %s' % devices)
        printflush('Initializing SHTC3...')
        self.sht = adafruit_shtc3.SHTC3(self.i2c)

    def _read_shtc3(self):
        printflush('Reading SHTC3...')
        temperature, relative_humidity = self.sht.measurements
        printflush("Temperature: %0.1f C" % temperature)
        printflush("Humidity: %0.1f %%" % relative_humidity)
        return temperature, relative_humidity

    def run(self):
        printflush("Enter loop...")
        while True:
            self.wdt.feed()
            self._read_shtc3()
            self.wdt.feed()
            sleep(20)
            self.wdt.feed()
            sleep(20)
            self.wdt.feed()
            sleep(20)


if __name__ == '__main__':
    Shtc3Tester().run()
