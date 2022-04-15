"""
Skeleton of a script for reading a sensor and sending the result to HomeAssistant.
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from sgp30 import SGP30
from machine import Pin, I2C
from time import sleep
import json
try:
    import struct
except ImportError:
    import ustruct as struct

# Pin mappings - board number to GPIO number
SDA = micropython.const(19)  # D19
SCL = micropython.const(18)  # D18


class AirQualitySensor:

    def __init__(self):
        printflush("Initializing i2c...")
        self.i2c = I2C(
            scl=Pin(SCL, mode=Pin.IN, pull=Pin.PULL_UP),
            sda=Pin(SDA, mode=Pin.IN, pull=Pin.PULL_UP),
            freq=100000
        )
        printflush("Initializing sensor...")
        self.sensor = SGP30(self.i2c)
        printflush("Serial number: %s", self.sensor.serial)
        printflush("Done initializing.")

    def run(self):
        printflush("Enter loop...")
        while True:
            self.send_data()
            sleep(60)

    def _read_sensor(self):
        printflush('Reading baseline...')
        baseline_co2, baseline_tvoc = self.sensor.indoor_air_quality_baseline
        printflush(
            'Baseline: eCO2=%s TVOC=%s' % (baseline_co2, baseline_tvoc)
        )
        printflush('Readling air quality...')
        co2_ppm, tvoc_ppb = self.sensor.indoor_air_quality
        printflush(
            'Indoor Air Quality: eCO2=%s ppm TVOC=%s ppb' % (co2_ppm, tvoc_ppb)
        )
        return baseline_co2, baseline_tvoc, co2_ppm, tvoc_ppb

    def send_data(self):
        printflush('measuring...')
        baseline_eco2, baseline_tvoc, eco2_ppm, tvoc_ppb = self._read_sensor()
        return
        data = json.dumps({
            'state': data,
            'attributes': {
                'friendly_name': self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        })
        self.http_post(data)


if __name__ == '__main__':
    AirQualitySensor().run()
