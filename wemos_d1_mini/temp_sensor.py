"""
POST temperature to HomeAssistant every minute

Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``temp_sensor.fzz``.
"""
import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from machine import Pin, reset
import network
from time import sleep, sleep_ms
from binascii import hexlify
from onewire import OneWire
from ds18x20 import DS18X20
import json

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


class TempSender(HassSender):

    def __init__(self):
        super().__init__(leds={
            'red': Pin(D2, Pin.OUT, value=False),
            'blue': Pin(D3, Pin.OUT, value=False),
            'green': Pin(D4, Pin.OUT, value=False)
        })
        printflush('Init OneWire')
        self.ds_pin = Pin(D1)
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
