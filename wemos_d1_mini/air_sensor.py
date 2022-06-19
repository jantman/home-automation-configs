"""
Skeleton of a script for reading a sensor and sending the result to HomeAssistant.
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from machine import Pin, I2C, WDT
from sgp30 import SGP30
from pm25_i2c import PM25_I2C
import adafruit_shtc3
from time import sleep
import json
try:
    import struct
except ImportError:
    import ustruct as struct


class AirQualitySensor(HassSender):

    def __init__(self):
        self.wdt = WDT(timeout=40000)  # 40-second watchdog timer
        super().__init__()
        printflush("Initializing i2c...")
        self.i2c = I2C(0, freq=100000)  # ESP32 hardware I2C 0 - SCL on D18, SDA on D19
        printflush('Scanning I2C bus...')
        devices = self.i2c.scan()
        printflush('I2C scan results: %s' % devices)
        printflush('Initializing SHTC3...')
        self.sht = adafruit_shtc3.SHTC3(self.i2c)
        temp, rh = self.sht.measurements
        printflush("Initializing SGP30 sensor...")
        self.sensor = SGP30(self.i2c)
        # from: https://github.com/adafruit/Adafruit_CircuitPython_SGP30/blob/3e906600098d8d6049af2eedc6e93b5895f8a6f4/examples/sgp30_simpletest.py#L19
        self.sensor.set_indoor_air_quality_baseline(0x8973, 0x8AAE)
        self.sensor.set_iaq_relative_humidity(temp, rh)
        printflush("Serial number: %s", self.sensor.serial)
        printflush("Done initializing SGP30")
        printflush("Initializing PM25 sensor")
        self.pm25 = PM25_I2C(self.i2c)
        printflush('sleeping 1 second')
        sleep(1)
        printflush("PM25 sensor initialized")

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
            self.send_data()
            self.wdt.feed()
            sleep(20)
            self.wdt.feed()
            sleep(20)
            self.wdt.feed()
            sleep(20)

    def _read_sgp30(self):
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
        return {
            'baseline_eco2_ppm': {
                'state': baseline_co2,
                'attributes': {
                    'friendly_name': '%s Baseline eCO2' % self.friendly_name,
                    'unit_of_measurement': 'PPM'
                }
            },
            'baseline_tvoc_ppb': {
                'state': baseline_tvoc,
                'attributes': {
                    'friendly_name': '%s Baseline TVOC' % self.friendly_name,
                    'unit_of_measurement': 'PPB'
                }
            },
            'eco2_ppm': {
                'state': co2_ppm,
                'attributes': {
                    'friendly_name': '%s eCO2' % self.friendly_name,
                    'unit_of_measurement': 'PPM'
                }
            },
            'tvoc_ppb': {
                'state': tvoc_ppb,
                'attributes': {
                    'friendly_name': '%s TVOC' % self.friendly_name,
                    'unit_of_measurement': 'PPB'
                }
            },
        }

    def _read_pm25(self):
        measures = {
            'particles 03um': [
                'particles_03um_ppdL', 'Particles over 0.3um', 'ppdL'
            ],
            'particles 05um': [
                'particles_05um_ppdL', 'Particles over 0.5um', 'ppdL'
            ],
            'particles 100um': [
                'particles_100um_ppdL', 'Particles over 10.0um', 'ppdL'
            ],
            'particles 10um': [
                'particles_10um_ppdL', 'Particles over 1.0um', 'ppdL'
            ],
            'particles 25um': [
                'particles_25um_ppdL', 'Particles over 2.5um', 'ppdL'
            ],
            'particles 50um': [
                'particles_50um_ppdL', 'Particles over 5.0um', 'ppdL'
            ],
            'pm10 env': [
                'pm1_env_ugm3', 'PM1.0 environmental', 'μg/m³'
            ],
            'pm10 standard': [
                'pm1_std_ugm3', 'PM1.0 standard', 'μg/m³'
            ],
            'pm100 env': [
                'pm10_env_ugm3', 'PM10.0 environmental', 'μg/m³'
            ],
            'pm100 standard': [
                'pm10_std_ugm3', 'PM10.0 standard', 'μg/m³'
            ],
            'pm25 env': [
                'pm25_env_ugm3', 'PM2.5 environmental', 'μg/m³'
            ],
            'pm25 standard': [
                'pm25_std_ugm3', 'PM2.5 standard', 'μg/m³'
            ],
        }
        try:
            aqdata = self.pm25.read()
            printflush(aqdata)
        except RuntimeError as ex:
            printflush("ERROR: Unable to read from sensor: %s" % ex)
            return []
        return {
            v[0]: {
                'state': aqdata[k],
                'attributes': {
                    'friendly_name': '%s %s' % (self.friendly_name, v[1]),
                    'unit_of_measurement': v[2]
                }
            } for k, v in measures.items()
        }

    def send_data(self):
        # sgp30.set_iaq_relative_humidity(celcius=22.1, relative_humidity=44)
        printflush('measuring SGP30...')
        data = self._read_sgp30()
        printflush('measuring PM25...')
        data.update(self._read_pm25())
        temp_c, rh = self._read_shtc3()
        temp_f = ((temp_c * 9.0) / 5.0) + 32
        data['temperature_f'] = temp_f
        data['relative_humidity'] = rh
        for k, v in data.items():
            self.http_post(json.dumps(v), suffix=k)


if __name__ == '__main__':
    AirQualitySensor().run()
