# WeMos D1 Mini

This directory contains code, schematics, etc. for the [WeMos D1 Mini](https://wiki.wemos.cc/products:d1:d1_mini) clone microcontrollers that I have performing various IO tasks for HomeAssistant. I chose these because they're cheap (currently $4USD each for a clone), have built-in WiFi, 11 digital IO (GPIO) pins that support PWM and One-Wire too, and use a simple MicroUSB connection for power and programming.

I've flashed the boards with [MicroPython](https://micropython.org/), both because Python is my strongest language and because the rest of this repository (and HomeAssistant itself) is Python.

## What's Here

* [boot.py](boot.py) - the original boot file that came with MicroPython
* [box_test.py](box_test.py) - Script to test the LED and buttons in the assembled [main.py](main.py) box.
* [button_test.py](button_test.py) - a simple test of momentary pushbutton input
* [config_example.py](config_example.py) - An example configuration file for these scripts, containing WiFi settings and your HASS URL. Copy to ``config.py`` and update for your values, then copy to the board.
* [led_test.py](led_test.py) - A simple test of flashing the board's onboard LED.
* [main.py](main.py) - The main application I run on my D1 Mini pushbutton control boxes. See the docstring at the top of the file for an explanation.
* [main.fzz](main.fzz) - A [Fritzing](https://fritzing.org) schematic for how the pushbutton control boxes are wired.
* [main.png](main.png) - PNG output of ``main.fzz``
* [main.svg](main.svg) - SVG output of ``main.fzz``
* [rgb_led_test.py](rgb_led_test.py) - A script for testing RGB LEDs, mainly for quickly turning on and off different colors/combinations when tuning resistors.

## Materials

Here are the actual parts that I'm using, all from Amazon:

* Boards: [Amazon.com: IZOKEE D1 Mini NodeMcu Lua 4M Bytes WLAN WiFi Internet Development Board Base on ESP8266 ESP-12F for Arduino, 100% Compatible with WeMos D1 Mini (Pack of 3)](https://www.amazon.com/gp/product/B076F53B6S/ref=ppx_yo_dt_b_asin_title_o03_s00?ie=UTF8&psc=1) - currently $12.99USD for a pack of 3.
* MicroUSB power supplies - whatever I had lying around, and some cheap ones from Amazon.
* RGB LEDs: [Amazon.com: EDGELEC 100pcs 5mm RGB Tri-Color (Red Green Blue Multicolor) 4Pin LED Diodes Common Cathode Diffused Round Top 29mm Long Feet +300pcs Resistors (for DC 6-13V) Included/Light Emitting Diodes: Home Improvement](https://www.amazon.com/gp/product/B077XGF3YR/ref=ppx_od_dt_b_asin_title_s00?ie=UTF8&psc=1)
* Small momentary pushbuttons: [Cylewet 12Pcs 1A 250V AC 2 Pins SPST Momentary Mini Push Button Switch Normal Open (Pack of 12) CYT1078: Amazon.com: Industrial & Scientific](https://www.amazon.com/gp/product/B0752RMB7Q/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)
* Large pushbutton: [Clyxgs Momentary Push Button Switch, Mini Push Button Switch No Lock Round 16mm 3A 250V AC/6A 125V AC Red Cap - - Amazon.com](https://www.amazon.com/gp/product/B07L1L5MZ3/ref=ppx_yo_dt_b_asin_title_o06_s00?ie=UTF8&psc=1) and covers: [Amazon.com: DaierTek 2Pcs Waterproof Safety Push Button Switch Cover Guard Plastic Protector Transperant for 16MM Push Button Switch: Automotive](https://www.amazon.com/gp/product/B07VF4F9JL/ref=ppx_yo_dt_b_asin_title_o07_s00?ie=UTF8&psc=1)
* Project boxes: [Ocharzy Plastic Black Electronic Project Box Enclosure Case, 4 Pcs (100x60x25 mm) - - Amazon.com](https://www.amazon.com/gp/product/B01EWXIJBM/ref=ppx_yo_dt_b_asin_title_o05_s00?ie=UTF8&psc=1) and [Zulkit Waterproof Plastic Project Box ABS IP65 Electronic Junction box Enclosure Black 3.94 x 2.68 x 1.97 inch (100X68X50mm) (Pack of 2) - - Amazon.com](https://www.amazon.com/gp/product/B07RTYYHK7/ref=ppx_yo_dt_b_asin_title_o05_s00?ie=UTF8&psc=1)
* DS18B20 One-Wire temperature sensors: [Diymore 5pcs DS18B20 Waterproof Temperature Sensors Thermistor Temperature Controller Length 1M with Digital Thermal Stainless Steel Probe: Amazon.com: Industrial & Scientific](https://www.amazon.com/gp/product/B01JKVRVNI/ref=ppx_yo_dt_b_asin_title_o02_s00?ie=UTF8&psc=1)

## Inital Setup

Follow the [Getting started with MicroPython on the ESP8266](https://docs.micropython.org/en/latest/esp8266/tutorial/intro.html#intro) guide; essentially:

1. ``pip install esptool rshell``
2. Plug the board in to your computer via USB and make sure your user has access to the tty.
3. Use esptool to erase the flash.
4. Flash MicroPython on to it; I'm currently using 1.11.

## Main Projects

### main.py / pushbutton control boxes

These are my main use for the WeMos D1 Mini's, and my first project with them. It's a simple project box with a D1 inside, a single RGB LED, and six momentary pushbuttons. Five of the pushbuttons trigger webhooks to HASS; the other reports the current status of my alarm.
