"""
Skeleton of a script for reading a sensor and sending the result to HomeAssistant.
"""

import micropython
micropython.alloc_emergency_exception_buf(100)

from hass_sender import printflush, HassSender
from time import sleep, sleep_ms
import json
try:
    import struct
except ImportError:
    import ustruct as struct


class Skeleton(HassSender):

    def __init__(self):
        super().__init__()
        raise NotImplementedError('Initialize sensors')

    def run(self):
        printflush("Enter loop...")
        while True:
            self.send_data()
            sleep(60)

    def send_data(self):
        printflush('measuring...')
        raise NotImplementedError('Read sensor data here')
        data = read_my_data()
        printflush('data=%s' % data)
        data = json.dumps({
            'state': data,
            'attributes': {
                'friendly_name': self.friendly_name,
                'unit_of_measurement': '\u00b0F'
            }
        })
        self.http_post(data)


if __name__ == '__main__':
    Skeleton().run()
