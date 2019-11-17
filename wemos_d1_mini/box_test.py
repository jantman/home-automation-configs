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
                trigger=Pin.IRQ_FALLING,
                handler=self.button_pin_irq_callback
            )
        while True:
            if self.unhandled_event:
                pass
            sleep_ms(50)

    def button_pin_irq_callback(self, _):
        print('button_pin_irq_callback()')
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

    def on_press_deferred(self, _):
        print('on_press_deferred() called')
        print(self.read_buttons())
        return
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
