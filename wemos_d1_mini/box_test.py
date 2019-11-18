"""
Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Connect buttons and LEDs according to ``main.fzz``.
"""

from machine import Pin, Timer
import micropython
from time import sleep_ms

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

BUTTON_MAP = {
    'white': D8,
    'blue': D5,
    'red': D4,
    'green': D2,
    'yellow': D3,
    'black': D1,
}


def debugprint(*args):
    print(*args)


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
        self.buttons_pressed = {}
        for color, pin in BUTTON_MAP.items():
            self.pin_to_button_colors['Pin(%s)' % pin] = color
            self.buttons[color] = Pin(pin, Pin.IN, Pin.PULL_UP)
            self.buttons_pressed[color] = False
        self.debounce_timer = Timer(0)
        self.timer_running = False
        print(self.debounce_timer)
        print(dir(self.debounce_timer))
        print('Finished init')

    def set_rgb(self, red, green, blue):
        self.leds['red'].value(red)
        self.leds['green'].value(green)
        self.leds['blue'].value(blue)

    def run(self):
        print('set IRQ')
        for pin in self.buttons.values():
            pin.irq(
                trigger=Pin.IRQ_RISING,
                handler=self.button_pin_irq_callback
            )
        while True:
            if self.unhandled_event:
                pass
            sleep_ms(50)

    def button_pin_irq_callback(self, pin):
        print('button_pin_irq_callback()')
        self.buttons_pressed[self.pin_to_button_colors[str(pin)]] = True
        if self.timer_running:
            return
        self.debounce_timer.init(
            mode=Timer.ONE_SHOT, period=200,
            callback=self.button_debounce_timer_irq_callback
        )

    def button_debounce_timer_irq_callback(self, _):
        print('button_debounce_timer_irq_callback()')
        self.timer_running = False
        micropython.schedule(self.on_press_deferred, None)

    def read_buttons(self):
        res = []
        for name, pin in self.buttons.items():
            print(name, pin, pin.value())
            if not pin.value():
                res.append(name)
        return res

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

    def on_press_deferred(self, _):
        print('on_press_deferred() called')
        pressed = [
            x for x in self.buttons_pressed.keys()
            if self.buttons_pressed[x]
        ]
        print(pressed)
        # reset the dict
        self.buttons_pressed = self.buttons_pressed.fromkeys(
            self.buttons_pressed, False
        )
        if not pressed:
            return
        if len(pressed) > 1:
            self.blink_leds(['red'], length_ms=100, num_times=3)
            return
        for color in pressed:
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
