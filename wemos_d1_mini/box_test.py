"""
Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``main.fzz``.
"""

from machine import Pin
import micropython
from time import sleep_ms
micropython.alloc_emergency_exception_buf(100)

# Pin mappings - board number to GPIO number
D0 = 16
D1 = 5
D2 = 4
D3 = 0
D4 = 2
D5 = 14
D6 = 12
D7 = 13
D8 = 15

BUTTON_MAP = {
    'white': D8,
    'blue': D5,
    'red': D4,
    'green': D2,
    'yellow': D3,
    'black': D1,
}


class BoxTest:

    def __init__(self):
        print('entered __init__()')
        self.unhandled_event = False
        print('Init LEDs')
        self.leds = {
            'red': Pin(D7, Pin.OUT, value=False),
            'blue': Pin(D0, Pin.OUT, value=False),
            'green': Pin(D6, Pin.OUT, value=False)
        }
        print('Init Buttons')
        self.pin_to_button_colors = {}
        self.buttons = {}
        for color, pin in BUTTON_MAP.items():
            self.pin_to_button_colors['Pin(%s)' % pin] = color
            self.buttons[color] = Pin(pin, Pin.IN, Pin.PULL_UP)
        print('Finished init')

    def set_rgb(self, red, green, blue):
        self.leds['red'].value(red)
        self.leds['green'].value(green)
        self.leds['blue'].value(blue)

    def run(self):
        print('set IRQ')
        for pin in self.buttons.values():
            pin.irq(
                trigger=Pin.IRQ_FALLING,
                handler=self.on_press
            )
        while True:
            if self.unhandled_event:
                pass
            sleep_ms(50)

    def on_press(self, pin):
        micropython.schedule(self.on_press_deferred, pin)

    def on_press_deferred(self, pin):
        color = self.pin_to_button_colors[str(pin)]
        print('on_press_deferred() called for pin: %s (%s)' % (color, pin))
        # print(pin.name)
        # print(pin.phys_port)
        # print(pin.__dict__())
        # print(vars(pin))
        # print(str(pin))
        if color == 'blue':
            self.set_rgb(False, False, True)
        elif color == 'green':
            self.set_rgb(False, True, False)
        elif color == 'red':
            self.set_rgb(True, False, False)
        elif color == 'white':
            self.set_rgb(True, True, True)
        elif color == 'black':
            self.set_rgb(False, False, False)
        elif color == 'yellow':
            self.set_rgb(True, True, False)


if __name__ == '__main__':
    BoxTest().run()
