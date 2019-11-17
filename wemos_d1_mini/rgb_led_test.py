"""
Intended for use pasted into MicroPython REPL.

Pinout:
https://wiki.wemos.cc/products:d1:d1_mini#pin

Using one of the common cathode 5mm RGB LEDs (see README)...

Connect the cathode to ground.
Connect the red leg through a 470-ohm resistor to D7 / GPIO13.
Connect the blue leg through a 2K-ohm resistor to D6 / GPIO12.
Connect the green leg through a 5K1-ohm resistor to D5 / GPIO14.
"""

from machine import Pin
import micropython
micropython.alloc_emergency_exception_buf(100)


def main():
    red = Pin(13, Pin.OUT)
    green = Pin(14, Pin.OUT)
    blue = Pin(12, Pin.OUT)
    resp = None
    while resp != 'x':
        print('x) exit')
        print('0) OFF')
        print('1) red')
        print('2) green')
        print('3) blue')
        print('4) magenta')
        print('5) cyan')
        print('6) yellow')
        print('7) white')
        resp = input('Selection: ').strip()
        if resp == 'x':
            break
        elif resp == '0':
            red.off()
            green.off()
            blue.off()
        elif resp == '1':
            red.on()
            green.off()
            blue.off()
        elif resp == '2':
            red.off()
            green.on()
            blue.off()
        elif resp == '3':
            red.off()
            green.off()
            blue.on()
        elif resp == '4':
            red.on()
            green.off()
            blue.on()
        elif resp == '5':
            red.off()
            green.on()
            blue.on()
        elif resp == '6':
            red.on()
            green.on()
            blue.off()
        elif resp == '7':
            red.on()
            green.on()
            blue.on()


if __name__ == '__main__':
    main()
