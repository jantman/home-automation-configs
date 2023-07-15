"""
POST temperature to HomeAssistant every minute

Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``temp_sensor.fzz``.
"""
import micropython
micropython.alloc_emergency_exception_buf(100)

import sys
from hass_sender import printflush, HassSender
from machine import Pin, reset
import network
from time import sleep, sleep_ms
from binascii import hexlify
from onewire import OneWire
from ds18x20 import DS18X20
import json

if sys.platform == 'esp8266':
    PIN_ONEWIRE = micropython.const(5)  # D1
    PIN_RED = micropython.const(4)  # D2
    PIN_BLUE = micropython.const(0)  # D3
    PIN_GREEN = micropython.const(2)  # D4
elif sys.platform == 'esp32':
    PIN_ONEWIRE = micropython.const(15)  # D15
    PIN_RED = micropython.const(13)  # D13
    PIN_BLUE = micropython.const(12)  # D12
    PIN_GREEN = micropython.const(14)  # D14
else:
    raise RuntimeError('ERROR: Unknown platform %s' % sys.platform)


class TempSender(HassSender):

    def __init__(self):
        super().__init__(leds={
            'red': Pin(PIN_RED, Pin.OUT, value=False),
            'blue': Pin(PIN_BLUE, Pin.OUT, value=False),
            'green': Pin(PIN_GREEN, Pin.OUT, value=False)
        })
        printflush('Init OneWire')
        self.ds_pin = Pin(PIN_ONEWIRE)
        self.ow_inst = OneWire(self.ds_pin)
        self.ds_sensor = DS18X20(self.ow_inst)
        self.temp_id = self.ds_sensor.scan()[0]
        printflush('Temperature sensor: %s' % self.temp_id)

    def run(self):
        printflush("Enter loop...")
        while True:
            self.send_temp()
            printflush('sleep 60')
            sleep(60)
            printflush('after sleep 60')

    def send_temp(self):
        printflush('converting temps...')
        self.ds_sensor.convert_temp()
        sleep(1)
        printflush('read_temp()')
        temp_c = self.ds_sensor.read_temp(self.temp_id)
        printflush('temp_c=%s' % temp_c)
        if temp_c == 85.0:
            printflush('Got bad temp; reset onewire bus')
            self.ow_inst.reset()
            return
        temp_f = ((temp_c * 9.0) / 5.0) + 32
        printflush('temp_f=%s' % temp_f)
        data = json.dumps({
            'state': round(temp_f, 2),
            'attributes': {
                'friendly_name': self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        })
        self.http_post(data)


if __name__ == '__main__':
    TempSender().run()
