"""
Base class for connecting to WiFi and sending metrics to HomeAssistant
"""

import network
import machine
import socket
from time import sleep, sleep_ms
from binascii import hexlify

from config import (
    SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HASS_TOKEN, ENTITIES, FRIENDLY_NAMES
)

wlan_status_code = {}
wlan_status_code[network.STAT_IDLE] = 'Idle'
wlan_status_code[network.STAT_CONNECTING] = 'Connecting'
wlan_status_code[network.STAT_WRONG_PASSWORD] = 'Wrong Password'
wlan_status_code[network.STAT_NO_AP_FOUND] = 'No AP Found'
wlan_status_code[network.STAT_GOT_IP] = 'Connected'


def printflush(*args):
    print(*args)


class HassSender:

    def __init__(self, leds={}):
        printflush("Init")
        self.leds = leds
        self.led_on('red')
        printflush('Instantiate WLAN')
        self.wlan = network.WLAN(network.STA_IF)
        printflush('connect_wlan()')
        self.connect_wlan()
        self.led_off('red')
        printflush('hexlify mac')
        self.mac = hexlify(self.wlan.config('mac')).decode()
        printflush('MAC: %s' % self.mac)
        self.entity_id = ENTITIES[self.mac]
        self.friendly_name = FRIENDLY_NAMES[self.mac]
        printflush('Entity ID: %s; Friendly Name: %s' % (
            self.entity_id, self.friendly_name
        ))
        self.post_path = '/api/states/' + self.entity_id
        printflush('POST path: %s' % self.post_path)

    def run(self):
        raise NotImplementedError()

    def connect_wlan(self):
        printflush('set wlan to active')
        self.wlan.active(True)
        printflush('test if wlan is connected')
        if not self.wlan.isconnected():
            printflush('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            printflush('MAC: %s' % hexlify(self.wlan.config('mac')).decode())
            for _ in range(0, 60):
                if self.wlan.isconnected():
                    printflush('WLAN is connected')
                    break
                stat = self.wlan.status()
                printflush(
                    'WLAN is not connected; sleep 1s; status=%s' %
                    wlan_status_code.get(stat, stat)
                )
                sleep(1)
            else:
                printflush('Could not connect to WLAN after 15s; reset')
                machine.reset()
        print('network config:', self.wlan.ifconfig())

    def http_post(self, data, suffix=None):
        printflush('http_post() called')
        self.set_rgb(False, False, True)
        printflush('getaddrinfo()')
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        printflush('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.settimeout(10.0)
        try:
            printflush('before connect()')
            s.connect(addr)
            printflush('after connect()')
        except OSError as exc:
            printflush('ERROR connecting to %s: %s' % (addr, exc))
            self.set_rgb(False, False, False)
            self.blink_leds(['red'], num_times=3, length_ms=100)
            printflush('s.close()')
            s.close()
            printflush('CONNECTION ERROR: calling machine.reset()')
            machine.reset()
            return None
        path = self.post_path
        if suffix is not None:
            path = self.post_path + '_' + suffix
        printflush('POST to: %s: %s' % (path, data))
        b = 'POST %s HTTP/1.0\r\nHost: %s\r\n' \
            'Content-Type: application/json\r\n' \
            'Authorization: Bearer %s\r\n' \
            'Content-Length: %d\r\n\r\n%s' % (
                path, HOOK_HOST, HASS_TOKEN, len(bytes(data, 'utf8')), data
            )
        printflush('SEND:\n%s' % b)
        try:
            s.send(bytes(b, 'utf8'))
            printflush('after send()')
        except OSError as exc:
            printflush('ERROR sending to %s: %s' % (addr, exc))
            self.set_rgb(False, False, False)
            self.blink_leds(['red'], num_times=3, length_ms=100)
            printflush('s.close()')
            s.close()
            printflush('CONNECTION ERROR: calling machine.reset()')
            machine.reset()
            return None
        buf = ''
        try:
            while True:
                data = s.recv(100)
                if data:
                    buf += str(data, 'utf8')
                else:
                    break
            printflush('received data:')
            printflush(buf)
        except OSError as exc:
            printflush('ERROR receiving from %s: %s' % (addr, exc))
            printflush('Buffer: %s' % buf)
            self.set_rgb(False, False, False)
            self.blink_leds(['red'], num_times=3, length_ms=100)
            printflush('s.close()')
            s.close()
            printflush('CONNECTION ERROR: calling machine.reset()')
            machine.reset()
            return None
        s.close()
        printflush('after close()')
        self.set_rgb(False, False, False)
        if 'HTTP/1.0 201 Created' or 'HTTP/1.0 200 OK' in buf:
            printflush('OK')
            self.blink_leds(['green'])
        else:
            printflush('FAIL')
            self.blink_leds(['red'], num_times=3, length_ms=100)
        printflush('http_post done')

    def led_on(self, color):
        if color in self.leds:
            self.leds[color].on()

    def led_off(self, color):
        if color in self.leds:
            self.leds[color].off()

    def set_rgb(self, red, green, blue):
        if 'red' in self.leds:
            self.leds['red'].value(red)
        if 'green' in self.leds:
            self.leds['green'].value(green)
        if 'blue' in self.leds:
            self.leds['blue'].value(blue)

    def blink_leds(self, colors, length_ms=250, num_times=1):
        if not self.leds:
            return
        for color, led in self.leds.items():
            if color not in colors:
                self.led_off(color)
        for idx in range(0, num_times):
            for color in colors:
                self.led_on(color)
            sleep_ms(length_ms)
            for color in colors:
                self.led_off(color)
            if idx != num_times - 1:
                sleep_ms(length_ms)
