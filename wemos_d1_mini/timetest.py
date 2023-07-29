"""
Class to test NTP / time drift
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

import network
import machine
import socket
from time import sleep, sleep_ms, time, mktime
from binascii import hexlify
import ntptime
from machine import RTC

from config import SSID, WPA_KEY
from device_config import DEVICE_CONFIG
from glpi_inventory import send_glpi
from utils import time_to_unix_time

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


class TimeTester:

    def __init__(self):
        printflush("Init")
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
        printflush('hexlify mac')
        self.mac = hexlify(self.wlan.config('mac')).decode()
        printflush('MAC: %s' % self.mac)
        self._set_time_from_ntp()
        self.rtc = RTC()
        self.boot_time = time()
        send_glpi(self.wlan, self.boot_time)

    def run(self):
        # from: https://docs.micropython.org/en/latest/esp8266/tutorial/network_tcp.html#simple-http-server
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        s = socket.socket()
        s.bind(addr)
        s.listen(1)
        print('listening on', addr)
        while True:
            cl, addr = s.accept()
            print('client connected from', addr)
            cl_file = cl.makefile('rwb', 0)
            while True:
                line = cl_file.readline()
                if not line or line == b'\r\n':
                    break
            response = ujson.dumps({
                'time': time_to_unix_time(time()),
                'rtc': time_to_unix_time(mktime(self.rtc.datetime())),
                'time_since_boot': time() - self.boot_time,

            })
            cl.send('HTTP/1.0 200 OK\r\nContent-type: application/json\r\n\r\n')
            cl.send(response)
            cl.close()

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


if __name__ == '__main__':
    TimeTester().run()
