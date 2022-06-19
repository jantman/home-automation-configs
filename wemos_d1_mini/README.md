# WeMos D1 Mini

This directory contains code, schematics, etc. for the [WeMos D1 Mini](https://wiki.wemos.cc/products:d1:d1_mini) clone microcontrollers that I have performing various IO tasks for HomeAssistant. I chose these because they're cheap (currently $4USD each for a clone), have built-in WiFi, 11 digital IO (GPIO) pins that support PWM and One-Wire too, and use a simple MicroUSB connection for power and programming.

I've flashed the boards with [MicroPython](https://micropython.org/), both because Python is my strongest language and because the rest of this repository (and HomeAssistant itself) is Python.

## What's Here

* [adafruit_bus_device_i2c.py](adafruit_bus_device_i2c.py) - Modified version of https://github.com/adafruit/Adafruit_CircuitPython_BusDevice/blob/904ab2f199c5f865b75837a8999cfe2e3eec1d56/adafruit_bus_device/i2c_device.py to work with MicroPython.
* [adafruit_shtc3.py](adafruit_shtc3.py) - Modified version of https://github.com/adafruit/Adafruit_CircuitPython_SHTC3/blob/519bf17361a132ecd5fc8f83ed2e32b42b3672a6/adafruit_shtc3.py to work with MicroPython.
* [air_sensor.py](air_sensor.py) - Indoor air quality sensor using an [Adafruit SGP30](https://www.adafruit.com/product/3709) equivalent carbon dioxide (eCO2) and total volatile organic compounds (TVOC) and an [Adafruit PMSA003I](https://www.adafruit.com/product/4632) particulate size and concentration sensor.
* [boot.py](boot.py) - the original boot file that came with MicroPython
* [config_example.py](config_example.py) - An example configuration file for these scripts, containing WiFi settings and your HASS URL. Copy to ``config.py`` and update for your values, then copy to the board.
* [hass_sender.py](hass_sender.py) - Base class for connecting to WiFi and sending metrics to HomeAssistant.
* [humidor_sht85.py](humidor_sht85.py) - The code for the temperature and humidity sensor in my humidor, using the SHT85 sensor. See [sht85.md](sht85.md) for details.
* [i2c_device.py](i2c_device.py) - Version of i2c_device.py from https://github.com/adafruit/Adafruit_CircuitPython_BusDevice @ a489e58 modified to run on MicroPython (MIT license)
* [led_test.py](led_test.py) - A simple test of flashing the board's onboard LED.
* [main.py](main.py) - Sample script that just attempts to connect to WiFi.
* [pm25_i2c.py](pm25_i2c.py) - Modified version of Adafruit PM25 I2C driver for MicroPython (from https://github.com/adafruit/Adafruit_CircuitPython_PM25/tree/310e418f7425843b67127f45c70067f37a183b46).
* [requirements.txt](requirements.txt) - pip requirements file for managing the boards and uploading code to them
* [rgb_led_test.py](rgb_led_test.py) - A script for testing RGB LEDs, mainly for quickly turning on and off different colors/combinations when tuning resistors.
* [sgp30.py](sgp30.py) - needed by air_sensor.py - https://github.com/safuya/micropython-sgp30/blob/09115cf788e0c1417c2fb5f77246f5a7dcc58b15/sgp30.py
* [sht85.md](sht85.md) - Notes on the SHT85 sensor and WeMos setup.
* [shtc3_test.py](shtc3_test.py) - Test script for I2C SHTC3 temp/humidity sensors; just prints temperature and humidity every 60 seconds.
* [skeleton.py](skeleton.py) - Skeleton of a script for reading a sensor and sending the result to HomeAssistant.
* [sync.py](sync.py) - Wrapper script around [rshell](https://github.com/dhylands/rshell) to automate syncing scripts to my boards.
* [temp_sensor.fzz](temp_sensor.fzz) - Schematic for the temperature sensor.
* [temp_sensor.png](temp_sensor.png) - PNG of Schematic
* [temp_sensor.py](temp_sensor.py) - A quick-and-dirty script to check the temperature of a DS18B20 temperature sensor and POST it to HomeAssistant (as a sensor value) every minute.
* [temp_sensor.svg](temp_sensor.svg) - SVG of Schematic
* [temp_sensor_box.jpg](temp_sensor_box.jpg) - Photo of installed temperature sensor box.
* [temp_sensor_test.py](temp_sensor_test.py) - Script for testing new temperature sensors.
* ``webrepl*`` and ``websocket_helper.py`` - Imported from https://github.com/micropython/webrepl @ 03492fef5c687e76057e6e93f6602b0a2dd5e660 because this isn't published to PyPI or as a real Python package.

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
3. Use esptool to erase the flash (``esptool.py erase_flash``).
4. Flash MicroPython on to it; I'm currently using 1.18 (``esptool.py --port /dev/ttyUSB4 --baud 460800 write_flash --flash_size=detect 0 esp32-20220117-v1.18.bin``).

## Quick Board Identity

``esptool.py --port /dev/ttyUSBn read_mac``
