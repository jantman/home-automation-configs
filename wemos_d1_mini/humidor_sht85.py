"""
POST temperature and humidity to HomeAssistant every minute

SHT85 sensor wired according to sht85.md
"""

import micropython
from micropython import const
micropython.alloc_emergency_exception_buf(100)
from machine import Pin, I2C
import network
import socket
from time import sleep, sleep_ms
from binascii import hexlify
import time
import time
import json
from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH, HASS_TOKEN
from i2c_device import I2CDevice
try:
    import struct
except ImportError:
    import ustruct as struct

# Pin mappings - board number to GPIO number
SDA = micropython.const(4)  # D2
SCL = micropython.const(5)  # D1


ENTITIES = {
    '500291c9b1a3': 'sensor.500291c9b1a3',
}

FRIENDLY_NAMES = {
    '500291c9b1a3': 'Humidor',
}

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
        time.sleep(0.001)
        print("SHT31D._reset() Sending soft reset to device")
        self._command(_SHT31_SOFTRESET)
        time.sleep(0.0015)

    def _data(self):
        data = bytearray(6)
        data[0] = 0xFF
        self._command(const(0x2400))
        time.sleep(0.0155)
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
        time.sleep(0.001)
        self.i2c_device.readinto(data)
        word = _unpack(data)
        return (word[0] << 16) | word[1]

# END Condensed version of sht85.py

class HumidorSender:

    def __init__(self):
        print("Init")
        self.unhandled_event = False
        self.wlan = network.WLAN(network.STA_IF)
        self.connect_wlan()
        self.mac = hexlify(self.wlan.config('mac')).decode()
        print('MAC: %s' % self.mac)
        self.entity_id = ENTITIES[self.mac]
        self.friendly_name = FRIENDLY_NAMES[self.mac]
        print('Entity ID: %s; Friendly Name: %s' % (
            self.entity_id, self.friendly_name
        ))
        self.post_path = '/api/states/' + self.entity_id
        print('POST path: %s' % self.post_path)
        print("Initializing i2c...")
        self.i2c = I2C(
            scl=Pin(SCL, mode=Pin.IN, pull=Pin.PULL_UP),
            sda=Pin(SDA, mode=Pin.IN, pull=Pin.PULL_UP),
            freq=1000
        )
        print("Initializing sensor...")
        self.sensor = SHT85(self.i2c)
        print("Serial number: %s", self.sensor.serial_number)
        print("Done initializing.")

    def run(self):
        print("Enter loop...")
        while True:
            self.send_data()
            sleep(60)

    def send_data(self):
        print('measuring...')
        temp_c, humidity = self.sensor._read()
        print('temp_c=%s humidity=%s' % (temp_c, humidity))
        temp_f = ((temp_c * 9.0) / 5.0) + 32
        print('temp_f=%s' % temp_f)
        data = json.dumps({
            'state': round(temp_f, 2),
            'attributes': {
                'friendly_name': '%s Temp' % self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        })
        self.http_post(data, 'temp')
        data = json.dumps({
            'state': round(humidity, 2),
            'attributes': {
                'friendly_name': '%s RH' % self.friendly_name,
                'unit_of_measurement': '%'
            }
        })
        self.http_post(data, 'humidity')

    def connect_wlan(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            print('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            while not self.wlan.isconnected():
                pass
        print('network config:', self.wlan.ifconfig())

    def http_post(self, data, suffix):
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        print('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.settimeout(10.0)
        try:
            s.connect(addr)
        except OSError as exc:
            print('ERROR connecting to %s: %s' % (addr, exc))
            s.close()
            return None
        path = self.post_path + '_' + suffix
        print('POST to: %s: %s' % (path, data))
        b = 'POST %s HTTP/1.0\r\nHost: %s\r\n' \
            'Content-Type: application/json\r\n' \
            'Authorization: Bearer %s\r\n' \
            'Content-Length: %d\r\n\r\n%s' % (
                path, HOOK_HOST, HASS_TOKEN, len(bytes(data, 'utf8')), data
            )
        print('SEND:\n%s' % b)
        s.send(bytes(b, 'utf8'))
        buf = ''
        while True:
            data = s.recv(100)
            if data:
                buf += str(data, 'utf8')
            else:
                break
        print(buf)
        s.close()
        if 'HTTP/1.0 201 Created' or 'HTTP/1.0 200 OK' in buf:
            print('OK')
        else:
            print('FAIL')


if __name__ == '__main__':
    HumidorSender().run()
