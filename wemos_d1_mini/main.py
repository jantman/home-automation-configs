"""
POST to HomeAssistant webhook when a button is pressed.

Pinout:
https://github.com/nodemcu/nodemcu-devkit-v1.0/blob/master/README.md#pin-map

Connect one leg of a button to "D6" on the board / GPIO12.
Connect the other leg to ground.

Connect the cathode (short leg) of a red LED to ground.
Connect the anode through a 220-Ohm resistor to D7 / GPIO13.

red 470 ohm

"""

import sys
import os
from machine import Pin
import micropython
import network
import socket
from time import sleep_ms
from binascii import hexlify
micropython.alloc_emergency_exception_buf(100)

from config import SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HOOK_PATH


class ButtonSender:

    def __init__(self):
        print("Init")
        self.unhandled_event = False
        self.button = Pin(12, Pin.IN, Pin.PULL_UP)
        self.led = Pin(13, Pin.OUT)
        self.led.on()
        self.wlan = network.WLAN(network.STA_IF)
        self.connect_wlan()
        self.led.off()
        self.mac = hexlify(self.wlan.config('mac')).decode()
        self.hook_path = HOOK_PATH + self.mac
        print('Hook path: %s' % self.hook_path)

    def run(self):
        print("Run")
        self.button.irq(
            trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
            handler=self.on_press
        )
        print("Enter loop...")
        while True:
            if self.unhandled_event:
                self.handle_change()
            sleep_ms(50)

    def connect_wlan(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            print('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            while not self.wlan.isconnected():
                pass
        print('network config:', self.wlan.ifconfig())

    def handle_change(self):
        self.unhandled_event = False
        if self.button.value():
            self.http_post()

    def on_press(self, _):
        print('on_press() called')
        self.unhandled_event = True

    def http_post(self):
        self.led.on()
        addr = socket.getaddrinfo(HOOK_HOST, HOOK_PORT)[0][-1]
        print('Connect to %s:%s' % (HOOK_HOST, HOOK_PORT))
        s = socket.socket()
        s.connect(addr)
        print('POST to: %s' % self.hook_path)
        s.send(bytes(
            'POST %s HTTP/1.0\r\nHost: %s\r\n\r\n' % (
                self.hook_path, HOOK_HOST
            ),
            'utf8'
        ))
        while True:
            data = s.recv(100)
            if data:
                print(str(data, 'utf8'), end='')
            else:
                break
        s.close()
        self.led.off()


if __name__ == '__main__':
    ButtonSender().run()
