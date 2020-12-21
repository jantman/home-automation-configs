"""
POST temperature and humidity to HomeAssistant every minute

DHT-22 with data line on D4
"""

from machine import Pin, reset
import micropython
import network
import socket
from time import sleep, sleep_ms
from binascii import hexlify
import dht
import json
micropython.alloc_emergency_exception_buf(100)

from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH, HASS_TOKEN

# Pin mappings - board number to GPIO number
D4 = micropython.const(2)

ENTITIES = {
    '500291c9b1a3': 'sensor.500291c9b1a3',
}

FRIENDLY_NAMES = {
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
        d = None
        try:
            d = dht.DHT22(Pin(D4, Pin.IN))
            d.measure()
        except Exception as ex:
            print('exception measuring: %s' % ex)
            return
        temp_c = d.temperature()
        humidity = d.humidity()
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
            'Authentication: Bearer %s\r\n' \
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
