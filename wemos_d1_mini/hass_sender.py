"""
Base class for connecting to WiFi and sending metrics to HomeAssistant
"""

import network
import machine
import socket
from time import sleep, sleep_ms, time
from binascii import hexlify
import ntptime

from config import (
    SSID, WPA_KEY, HOOK_HOST, HOOK_PORT, HASS_TOKEN
)
from device_config import DEVICE_CONFIG
from glpi_inventory import send_glpi

try:
    from urequests import get, post
except ImportError:
    from requests import get, post

try:
    import ujson
except ImportError:
    import json as ujson

wlan_status_code = {}
wlan_status_code[network.STAT_IDLE] = 'Idle'
wlan_status_code[network.STAT_CONNECTING] = 'Connecting'
wlan_status_code[network.STAT_WRONG_PASSWORD] = 'Wrong Password'
wlan_status_code[network.STAT_NO_AP_FOUND] = 'No AP Found'
wlan_status_code[network.STAT_GOT_IP] = 'Connected'


def printflush(*args):
    print(*args)


class NoLed:

    def __init__(self):
        printflush("No LED configured")

    def led_on(self, color):
        pass

    def led_off(self, color):
        pass

    def set_rgb(self, red, green, blue):
        pass

    def blink_leds(self, colors, length_ms=250, num_times=1):
        pass


class RgbLed:

    def __init__(self, leds={}):
        printflush("RGB LED configured")
        self.leds = leds

    def led_on(self, color: str):
        if color in self.leds:
            self.leds[color].on()

    def led_off(self, color: str):
        if color in self.leds:
            self.leds[color].off()

    def set_rgb(self, red: bool, green: bool, blue: bool):
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


class NeoPixelLed:

    def __init__(self, neo_pixel, brightness: int = 255):
        printflush("NeoPixel LED configured")
        self.neopixel = neo_pixel
        self.brightness = brightness
        self.values = [0, 0, 0]

    def led_on(self, color: str):
        if color == 'red':
            self.values[0] = self.brightness
        elif color == 'green':
            self.values[1] = self.brightness
        elif color == 'blue':
            self.values[2] = self.brightness
        self.neopixel.fill(self.values)
        self.neopixel.write()

    def led_off(self, color: str):
        if color == 'red':
            self.values[0] = 0
        elif color == 'green':
            self.values[1] = 0
        elif color == 'blue':
            self.values[2] = 0
        self.neopixel.fill(self.values)
        self.neopixel.write()

    def set_rgb(self, red: bool, green: bool, blue: bool):
        self.values = [
            self.brightness if red else 0,
            self.brightness if green else 0,
            self.brightness if blue else 0
        ]
        self.neopixel.fill(self.values)
        self.neopixel.write()

    def blink_leds(self, colors, length_ms=250, num_times=1):
        for color in ['red', 'green', 'blue']:
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


class HassSender:

    def __init__(self, leds={}, neo_pixel=None, brightness: int = 255, set_ntptime=True):
        printflush("Init")
        if neo_pixel is not None:
            self.led = NeoPixelLed(neo_pixel, brightness=brightness)
        elif leds:
            self.led = RgbLed(leds)
        else:
            self.led = NoLed()
        self.led.led_on('red')
        unique_id = hexlify(machine.unique_id()).decode()
        devconf = DEVICE_CONFIG[unique_id]
        hostname = devconf.get('hostname')
        if hostname:
            if len(hostname) >= 16:
                printflush("ERROR: hostname must be < 16 characters")
            else:
                printflush('Set hostname to: %s' % hostname)
                network.hostname(hostname)
        printflush('Instantiate WLAN')
        self.wlan = network.WLAN(network.STA_IF)
        printflush('connect_wlan()')
        self.connect_wlan()
        self.led.led_off('red')
        printflush('hexlify mac')
        self.mac = hexlify(self.wlan.config('mac')).decode()
        printflush('MAC: %s' % self.mac)
        self.entity_id = devconf['entity']
        self.friendly_name = devconf['friendly_name']
        printflush('Entity ID: %s; Friendly Name: %s' % (
            self.entity_id, self.friendly_name
        ))
        self.post_path = '/api/states/' + self.entity_id
        printflush('POST path: %s' % self.post_path)
        if set_ntptime:
            self._set_time_from_ntp()
        self.boot_time = time()
        send_glpi(self.wlan, self.boot_time)

    def run(self):
        raise NotImplementedError()

    def _set_time_from_ntp(self):
        printflush('Setting time from NTP...')
        printflush('Current time: %s' % time())
        for _ in range(0, 5):
            try:
                ntptime.settime()
                printflush('Time set via NTP; new time: %s' % time())
                return
            except Exception as ex:
                printflush(
                    'Failed setting time via NTP: %s; try again in 5s' % ex
                )
                sleep(5)
        printflush('ERROR: Could not set time via NTP')

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

    def http_post(self, data_dict, suffix=None):
        printflush('http_post() called')
        j = bytes(ujson.dumps(data_dict), 'utf8')
        self.set_rgb(False, False, True)
        path = self.post_path
        if suffix is not None:
            path = path + '_' + suffix
        try:
            r = post(
                f'http://{HOOK_HOST}:{HOOK_PORT}{path}', data=j,
                timeout=10,
                headers={'Authorization': f'Bearer {HASS_TOKEN}'}
            )
            printflush(f'POST returned HTTP {r.status_code}: {r.reason}')
            printflush('Received data:')
            printflush(r.text)
            assert r.status_code in [200, 201]
        except Exception:
            self.led.set_rgb(False, False, False)
            self.led.blink_leds(['red'], num_times=3, length_ms=100)
            printflush('CONNECTION ERROR: calling machine.reset()')
            machine.reset()
            return None
        r.close()
        printflush('after close()')
        self.led.set_rgb(False, False, False)
        self.led.blink_leds(['green'])
        printflush('http_post done')

    def led_on(self, color):
        self.led.led_on(color)

    def led_off(self, color):
        self.led.led_off(color)

    def set_rgb(self, red, green, blue):
        self.led.set_rgb(red, green, blue)

    def blink_leds(self, colors, length_ms=250, num_times=1):
        self.led.blink_leds(colors, length_ms=length_ms, num_times=num_times)
