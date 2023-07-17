"""
POST temperature and humidity to HomeAssistant every minute

SHT85 sensor wired according to sht85.md
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from micropython import const
from machine import Pin, I2C
from time import sleep, sleep_ms
import json
from i2c_device import I2CDevice
try:
    import struct
except ImportError:
    import ustruct as struct

# Pin mappings - board number to GPIO number
SDA = micropython.const(4)  # D1Mini pin D2 / GPIO4 / SDA
SCL = micropython.const(5)  # D1Mini pin D1 / GPIO5 / SCL

# BEGIN Condensed version of sht85.py
_SHT31_DEFAULT_ADDRESS = const(0x44)
REP_HIGH = "High"
FREQUENCY_4 = 4
_SHT31_PERIODIC_BREAK = const(0x3093)
_SHT31_SOFTRESET = const(0x30A2)
_SHT31_READSERIALNBR = const(0x3780)

def _crc(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc <<= 1
                crc ^= 0x131
            else:
                crc <<= 1
    return crc


def _unpack(data):
    length = len(data)
    crc = [None] * (length // 3)
    word = [None] * (length // 3)
    for i in range(length // 6):
        word[i * 2], crc[i * 2], word[(i * 2) + 1], crc[(i * 2) + 1] = struct.unpack(
            ">HBHB", data[i * 6 : (i * 6) + 6]
        )
        if crc[i * 2] == _crc(data[i * 6 : (i * 6) + 2]):
            length = (i + 1) * 6
    for i in range(length // 3):
        if crc[i] != _crc(data[i * 3 : (i * 3) + 2]):
            raise RuntimeError("CRC mismatch")
    return word[: length // 3]


class SHT85:

    def __init__(self, i2c_bus, address=_SHT31_DEFAULT_ADDRESS):
        self.i2c_device = I2CDevice(i2c_bus, address)
        self._repeatability = REP_HIGH
        self._frequency = FREQUENCY_4
        self._last_read = 0
        self._cached_temperature = None
        self._cached_humidity = None
        self._reset()

    def _command(self, command):
        self.i2c_device.write(struct.pack(">H", command))

    def _reset(self):
        """
        Soft reset the device
        The reset command is preceded by a break command as the
        device will not respond to a soft reset when in 'Periodic' mode.
        """
        print("SHT31D._reset() Sending periodic break to device")
        self._command(_SHT31_PERIODIC_BREAK)
        sleep(0.001)
        print("SHT31D._reset() Sending soft reset to device")
        self._command(_SHT31_SOFTRESET)
        sleep(0.0015)

    def _data(self):
        data = bytearray(6)
        data[0] = 0xFF
        self._command(const(0x2400))
        sleep(0.0155)
        self.i2c_device.readinto(data)
        word = _unpack(data)
        length = len(word)
        temperature = [None] * (length // 2)
        humidity = [None] * (length // 2)
        for i in range(length // 2):
            temperature[i] = -45 + (175 * (word[i * 2] / 65535))
            humidity[i] = 100 * (word[(i * 2) + 1] / 65535)
        if (len(temperature) == 1) and (len(humidity) == 1):
            return temperature[0], humidity[0]
        return temperature, humidity

    def _read(self):
        self._cached_temperature, self._cached_humidity = self._data()
        return self._cached_temperature, self._cached_humidity

    @property
    def serial_number(self):
        """Device serial number."""
        data = bytearray(6)
        data[0] = 0xFF
        self._command(_SHT31_READSERIALNBR)
        sleep(0.001)
        self.i2c_device.readinto(data)
        word = _unpack(data)
        return (word[0] << 16) | word[1]

# END Condensed version of sht85.py


class HumidorSender(HassSender):

    def __init__(self):
        super().__init__()
        printflush("Initializing i2c...")
        self.i2c = I2C(
            scl=Pin(SCL, mode=Pin.IN, pull=Pin.PULL_UP),
            sda=Pin(SDA, mode=Pin.IN, pull=Pin.PULL_UP),
            freq=1000
        )
        printflush("Initializing sensor...")
        self.sensor = SHT85(self.i2c)
        printflush("Serial number: %s", self.sensor.serial_number)
        printflush("Done initializing.")

    def run(self):
        printflush("Enter loop...")
        while True:
            self.send_data()
            sleep(60)

    def send_data(self):
        printflush('measuring...')
        temp_c, humidity = self.sensor._read()
        printflush('temp_c=%s humidity=%s' % (temp_c, humidity))
        temp_f = ((temp_c * 9.0) / 5.0) + 32
        printflush('temp_f=%s' % temp_f)
        data = {
            'state': round(temp_f, 2),
            'attributes': {
                'friendly_name': '%s Temp' % self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        }
        self.http_post(data, suffix='temp')
        data = {
            'state': round(humidity, 2),
            'attributes': {
                'friendly_name': '%s RH' % self.friendly_name,
                'unit_of_measurement': '%'
            }
        }
        self.http_post(data, suffix='humidity')


if __name__ == '__main__':
    HumidorSender().run()
