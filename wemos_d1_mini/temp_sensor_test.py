"""
Temperature sensor circuit test

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


class TempTester:

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
        self.wlan = network.WLAN(network.STA_IF)
        self.mac = hexlify(self.wlan.config('mac')).decode()
        print('MAC: %s' % self.mac)

    def run(self):
        resp = None
        while resp != 'x':
            print('x) exit')
            print('0) OFF')
            print('1) red')
            print('2) green')
            print('3) blue')
            print('4) magenta')
            print('5) cyan')
            print('6) yellow')
            print('7) white')
            print('t) temp')
            resp = input('Selection: ').strip()
            if resp == 'x':
                break
            elif resp == '0':
                self.leds['red'].off()
                self.leds['green'].off()
                self.leds['blue'].off()
            elif resp == '1':
                self.leds['red'].on()
                self.leds['green'].off()
                self.leds['blue'].off()
            elif resp == '2':
                self.leds['red'].off()
                self.leds['green'].on()
                self.leds['blue'].off()
            elif resp == '3':
                self.leds['red'].off()
                self.leds['green'].off()
                self.leds['blue'].on()
            elif resp == '4':
                self.leds['red'].on()
                self.leds['green'].off()
                self.leds['blue'].on()
            elif resp == '5':
                self.leds['red'].off()
                self.leds['green'].on()
                self.leds['blue'].on()
            elif resp == '6':
                self.leds['red'].on()
                self.leds['green'].on()
                self.leds['blue'].off()
            elif resp == '7':
                self.leds['red'].on()
                self.leds['green'].on()
                self.leds['blue'].on()
            elif resp == 't':
                self.leds['red'].off()
                self.leds['green'].off()
                self.leds['blue'].off()
                self.get_temp()

    def get_temp(self):
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
    TempTester().run()
