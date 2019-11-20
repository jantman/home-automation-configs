"""
Connect to WiFi and wait (for WebREPL)...
"""

import micropython
import network
from time import sleep_ms
from binascii import hexlify
micropython.alloc_emergency_exception_buf(100)

from config import SSID, WPA_KEY


class WiFiWaiter:

    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.connect_wlan()
        self.mac = hexlify(self.wlan.config('mac')).decode()
        print('MAC: %s' % self.mac)

    def run(self):
        print("Enter loop...")
        while True:
            sleep_ms(200)

    def connect_wlan(self):
        self.wlan.active(True)
        if not self.wlan.isconnected():
            print('connecting to network...')
            self.wlan.connect(SSID, WPA_KEY)
            while not self.wlan.isconnected():
                pass
        print('network config:', self.wlan.ifconfig())


if __name__ == '__main__':
    WiFiWaiter().run()
