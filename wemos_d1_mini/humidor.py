"""
POST temperature and humidity to HomeAssistant every minute

BME-280 with SCL on D4 / 2 and SDA on D3 / 0
"""

from machine import Pin, reset, I2C
import micropython
import network
import socket
from time import sleep, sleep_ms
from binascii import hexlify
import json
micropython.alloc_emergency_exception_buf(100)
from bme280 import BME280

from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH

# Pin mappings - board number to GPIO number
D4 = Pin(micropython.const(2))
D3 = Pin(micropython.const(0))
SCL = D4
SDA = D3

ENTITIES = {
    'f4cfa2d0a962': 'sensor.humidor',
    'f4cfa2d0de01': 'sensor.f4cfa2d0de01',
    'f4cfa2d0a226': 'sensor.f4cfa2d0a226',
    '500291c9b1a3': 'sensor.500291c9b1a3',
}

FRIENDLY_NAMES = {
    'f4cfa2d0a962': 'Humidor',
    'f4cfa2d0de01': 'f4cfa2d0de01',
    'f4cfa2d0a226': 'f4cfa2d0a226',
    '500291c9b1a3': '500291c9b1a3',
}


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

    def run(self):
        print("Enter loop...")
        while True:
            self.send_data()
            sleep(60)

    def send_data(self):
        print('measuring...')
        temp_c = None
        pressure = None
        humidity = None
        try:
            i2c = I2C(scl=SCL, sda=SDA)
            i2c.scan()
            bme280 = BME280(i2c=i2c)
            temp_c, pressure, humidity = bme280.read_compensated_data()
        except Exception as ex:
            print('exception measuring: %s' % ex)
            return
        print('UNCONVERTED VALUES: temp_c=%s pressure=%s humidity=%s' % (temp_c, pressure, humidity))
        temp_c = temp_c / 100.0
        pressure = pressure / 256.0
        humidity = humidity / 1024.0
        print('CONVERTED: temp_c=%s pressure=%s humidity=%s' % (temp_c, pressure, humidity))
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
        data = json.dumps({
            'state': round(pressure, 2),
            'attributes': {
                'friendly_name': '%s Pressure' % self.friendly_name,
                'unit_of_measurement': 'Pa'
            }
        })
        self.http_post(data, 'pressure')

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
            'Content-Length: %d\r\n\r\n%s' % (
                path, HOOK_HOST, len(bytes(data, 'utf8')), data
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
