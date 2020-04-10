"""
POST temperature to HomeAssistant every minute

Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``temp_sensor.fzz``.
"""

from machine import Pin, reset
import micropython
import network
import socket
from time import sleep, sleep_ms
from binascii import hexlify
from onewire import OneWire
from ds18x20 import DS18X20
import json
micropython.alloc_emergency_exception_buf(100)

from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH

# Pin mappings - board number to GPIO number
D0 = micropython.const(16)
D1 = micropython.const(5)
D2 = micropython.const(4)
D3 = micropython.const(0)
D4 = micropython.const(2)
D5 = micropython.const(14)
D6 = micropython.const(12)
D7 = micropython.const(13)
D8 = micropython.const(15)

ENTITIES = {
    '500291c9b245': 'sensor.porch_temp',
    'bcddc2b67528': 'sensor.chest_freezer_temp',
    'bcddc2b66c5a': 'sensor.kitchen_freezer_temp'
}

FRIENDLY_NAMES = {
    '500291c9b245': 'Porch Temp',
    'bcddc2b67528': 'Chest Freezer Temp',
    'bcddc2b66c5a': 'Kitchen Freezer Temp'
}


class TempSender:

    def __init__(self):
        print("Init")
        self.unhandled_event = False
        print('Init LEDs')
        self.leds = {
            'red': Pin(D2, Pin.OUT, value=False),
            'blue': Pin(D3, Pin.OUT, value=False),
            'green': Pin(D4, Pin.OUT, value=False)
        }
        print('Init OneWire')
        self.ds_pin = Pin(D1)
        self.ow_inst = OneWire(self.ds_pin)
        self.ds_sensor = DS18X20(self.ow_inst)
        self.temp_id = self.ds_sensor.scan()[0]
        print('Temperature sensor: %s' % self.temp_id)
        self.leds['red'].on()
        self.wlan = network.WLAN(network.STA_IF)
        self.connect_wlan()
        self.leds['red'].off()
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
            self.send_temp()
            sleep(60)

    def send_temp(self):
        print('converting temps...')
        self.ds_sensor.convert_temp()
        sleep(1)
        temp_c = self.ds_sensor.read_temp(self.temp_id)
        print('temp_c=%s' % temp_c)
        if temp_c == 85.0:
            print('Got bad temp; reset onewire bus')
            self.ow_inst.reset()
            return
        temp_f = ((temp_c * 9.0) / 5.0) + 32
        print('temp_f=%s' % temp_f)
        data = json.dumps({
            'state': round(temp_f, 2),
            'attributes': {
                'friendly_name': self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        })
        self.http_post(data)

    def connect_wlan(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            print('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            while not self.wlan.isconnected():
                pass
        print('network config:', self.wlan.ifconfig())

    def http_post(self, data):
        self.set_rgb(False, False, True)
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        print('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.settimeout(10.0)
        try:
            s.connect(addr)
        except OSError as exc:
            print('ERROR connecting to %s: %s' % (addr, exc))
            self.set_rgb(False, False, False)
            self.blink_leds(['red'], num_times=3, length_ms=100)
            s.close()
            return None
        print('POST to: %s: %s' % (self.post_path, data))
        b = 'POST %s HTTP/1.0\r\nHost: %s\r\n' \
            'Content-Type: application/json\r\n' \
            'Content-Length: %d\r\n\r\n%s' % (
                self.post_path, HOOK_HOST, len(bytes(data, 'utf8')), data
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
        self.set_rgb(False, False, False)
        if 'HTTP/1.0 201 Created' or 'HTTP/1.0 200 OK' in buf:
            print('OK')
            self.blink_leds(['green'])
        else:
            print('FAIL')
            self.blink_leds(['red'], num_times=3, length_ms=100)

    def set_rgb(self, red, green, blue):
        self.leds['red'].value(red)
        self.leds['green'].value(green)
        self.leds['blue'].value(blue)

    def blink_leds(self, colors, length_ms=250, num_times=1):
        for color, led in self.leds.items():
            if color not in colors:
                led.off()
        for idx in range(0, num_times):
            for color in colors:
                self.leds[color].on()
            sleep_ms(length_ms)
            for color in colors:
                self.leds[color].off()
            if idx != num_times - 1:
                sleep_ms(length_ms)


if __name__ == '__main__':
    TempSender().run()
