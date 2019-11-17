"""
Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect one leg of a button to "D6" on the board / GPIO12.
Connect the other leg to ground.
"""

from machine import Pin
import micropython
from time import sleep_ms
micropython.alloc_emergency_exception_buf(100)


class ButtonTest:

    def __init__(self):
        print('entered __init__()')
        self.button_pressed = False
        self.unhandled_event = False
        print('Init LED')
        self.led = Pin(2, Pin.OUT)
        print('Init Button')
        self.button = Pin(12, Pin.IN, Pin.PULL_UP)
        print('Finished init')

    def run(self):
        print('run - turn LED on')
        self.led.on()
        print('set IRQ rising')
        self.button.irq(
            trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
            handler=self.on_press
        )
        while True:
            if self.unhandled_event:
                self.handle_change()
            sleep_ms(50)
        print('done with run()')

    def handle_change(self):
        if self.button.value():
            self.led.on()
        else:
            self.led.off()

    def on_press(self, _):
        print('on_press() called')
        self.unhandled_event = True


if __name__ == '__main__':
    print('Before class.')
    ButtonTest().run()
    print('After class.')
