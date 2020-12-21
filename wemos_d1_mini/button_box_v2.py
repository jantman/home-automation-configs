"""
POST to HomeAssistant webhook when a button is pressed.

Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``main.fzz``.
"""

import sys
import os
from machine import Pin, Timer
import micropython
import network
import socket
from time import sleep_ms, sleep
from binascii import hexlify
import json
micropython.alloc_emergency_exception_buf(100)

from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH, HASS_TOKEN

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

BUTTON_MAP = {
    'white': D4,
    'silver': D7,
    'red': D1,
    'green': D5,
    'yellow': D3,
}


class ButtonSender:

    def __init__(self):
        print("Init")
        self.unhandled_event = False
        print('Init LEDs')
        self.leds = {
            'red': Pin(D6, Pin.OUT, value=False),
            'green': Pin(D0, Pin.OUT, value=False)
        }
        print('Init Buttons')
        self.pin_to_button_colors = {}
        self.buttons = {}
        self.buttons_pressed = {}
        for color, pin in BUTTON_MAP.items():
            self.pin_to_button_colors['Pin(%s)' % pin] = color
            self.buttons[color] = Pin(pin, Pin.IN, Pin.PULL_UP)
            self.buttons_pressed[color] = False
        self.debounce_timer = Timer(0)
        self.timer_running = False
        self.leds['red'].on()
        self.wlan = network.WLAN(network.STA_IF)
        self.connect_wlan()
        self.leds['red'].off()
        self.mac = hexlify(self.wlan.config('mac')).decode()
        self.hook_path = HOOK_PATH + self.mac
        print('Hook path: %s' % self.hook_path)

    def run(self):
        print("Run")
        for pin in self.buttons.values():
            pin.irq(
                trigger=Pin.IRQ_RISING,
                handler=self.button_pin_irq_callback
            )
        print("Enter loop...")
        while True:
            self.show_status()
            sleep(30)

    def button_pin_irq_callback(self, pin):
        print('button_pin_irq_callback()')
        self.buttons_pressed[self.pin_to_button_colors[str(pin)]] = True
        if self.timer_running:
            return
        self.debounce_timer.init(
            mode=Timer.ONE_SHOT, period=200,
            callback=self.button_debounce_timer_irq_callback
        )

    def button_debounce_timer_irq_callback(self, _):
        print('button_debounce_timer_irq_callback()')
        self.timer_running = False
        micropython.schedule(self.on_press_deferred, None)

    def connect_wlan(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            print('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            while not self.wlan.isconnected():
                pass
        print('network config:', self.wlan.ifconfig())

    def on_press_deferred(self, _):
        print('on_press_deferred() called')
        pressed = [
            x for x in self.buttons_pressed.keys()
            if self.buttons_pressed[x]
        ]
        print('Buttons pressed: %s' % pressed)
        # reset the dict
        self.buttons_pressed = self.buttons_pressed.fromkeys(
            self.buttons_pressed, False
        )
        if not pressed:
            return
        if len(pressed) > 1:
            self.blink_leds(['red'], length_ms=100, num_times=3)
            return
        color = pressed[0]
        if color == 'silver':
            self.http_post(self.hook_path + '-panic')
        elif color == 'green':
            self.http_post(self.hook_path + '-disarm')
        elif color == 'red':
            self.http_post(self.hook_path + '-armhome')
        elif color == 'white':
            self.http_post(self.hook_path + '-duress')
        elif color == 'yellow':
            self.http_post(self.hook_path + '-light')
        sleep(2)
        self.show_status()
        sleep(2)
        self.show_status()
        sleep(2)
        self.show_status()
        sleep(2)
        self.show_status()
        sleep(2)
        self.show_status()
        sleep(2)
        self.show_status()

    def show_status(self):
        if self.in_duress:
            self.set_rgb(True, True, False)
        elif self.alarm_state == 'Disarmed':
            self.set_rgb(False, True, False)
        else:
            self.set_rgb(True, False, False)

    @property
    def alarm_state(self):
        return self.get_entity_state('input_select.alarmstate')

    @property
    def in_duress(self):
        st = self.get_entity_state('input_boolean.alarm_duress')
        return st == 'on'

    def http_post(self, path):
        self.set_rgb(False, False, False)
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        print('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.settimeout(10.0)
        s.connect(addr)
        print('POST to: %s' % path)
        s.send(bytes(
            'POST %s HTTP/1.0\r\nHost: %s\r\n'
            'Authorization: Bearer %s\r\n\r\n' % (
                path, HOOK_HOST, HASS_TOKEN
            ),
            'utf8'
        ))
        buf = ''
        while True:
            data = s.recv(100)
            if data:
                buf += str(data, 'utf8')
            else:
                break
        print(buf)
        s.close()
        if 'HTTP/1.0 200 OK' in buf:
            print('OK')
            self.blink_leds(['green'])
        else:
            print('FAIL')
            self.blink_leds(['red'], num_times=3, length_ms=100)

    def get_entity_state(self, entity_id):
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        print('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.settimeout(10.0)
        s.connect(addr)
        path = '/api/states/' + entity_id
        print('GET: %s' % path)
        s.send(bytes(
            'GET %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (
                path, HOOK_HOST
            ),
            'utf8'
        ))
        buf = ''
        while True:
            data = s.recv(100)
            if data:
                buf += str(data, 'utf8')
            else:
                break
        print(buf)
        s.close()
        if 'HTTP/1.0 200 OK' in buf:
            print('OK')
        else:
            print('FAIL')
            self.blink_leds(['red'], num_times=3, length_ms=100)
            return None
        data = buf.strip().split("\n")[-1]
        res = json.loads(data)
        return res['state']

    def set_rgb(self, red, green, _):
        self.leds['red'].value(red)
        self.leds['green'].value(green)

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
    ButtonSender().run()
