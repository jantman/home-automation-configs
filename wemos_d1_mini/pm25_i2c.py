"""
Combination of __init__.py and i2c.py from:
https://github.com/adafruit/Adafruit_CircuitPython_PM25/tree/310e418f7425843b67127f45c70067f37a183b46

Copyright 2020 ladyada for Adafruit Industries
MIT license
"""

# imports
import time
from adafruit_bus_device.i2c_device import I2CDevice
import struct

# SPDX-FileCopyrightText: 2020 ladyada for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_pm25`
================================================================================

CircuitPython library for PM2.5 Air Quality Sensors


* Author(s): ladyada

Implementation Notes
--------------------

**Hardware:**

Works with most (any?) Plantower UART or I2C interfaced PM2.5 sensor.

* `PM2.5 Air Quality Sensor and Breadboard Adapter Kit - PMS5003
  <https://www.adafruit.com/product/3686>`_

* `PM2.5 Air Quality Sensor with I2C Interface - PMSA003I
  <https://www.adafruit.com/product/4505>`_

* `Adafruit PMSA003I Air Quality Breakout
  <https://www.adafruit.com/product/4632>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases
* Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

"""


__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_PM25.git"


class PM25:
    """
    Super-class for generic PM2.5 sensors.

    .. note::
        Subclasses must implement _read_into_buffer to fill self._buffer with a packet of data

    """

    def __init__(self) -> None:
        # rad, ok make our internal buffer!
        self._buffer = bytearray(32)
        self.aqi_reading = {
            "pm10 standard": None,
            "pm25 standard": None,
            "pm100 standard": None,
            "pm10 env": None,
            "pm25 env": None,
            "pm100 env": None,
            "particles 03um": None,
            "particles 05um": None,
            "particles 10um": None,
            "particles 25um": None,
            "particles 50um": None,
            "particles 100um": None,
        }

    def _read_into_buffer(self) -> None:
        """Low level buffer filling function, to be overridden"""
        raise NotImplementedError()

    def read(self) -> dict:
        """Read any available data from the air quality sensor and
        return a dictionary with available particulate/quality data"""
        self._read_into_buffer()
        # print([hex(i) for i in self._buffer])

        # check packet header
        if not self._buffer[0:2] == b"BM":
            raise RuntimeError("Invalid PM2.5 header")

        # check frame length
        frame_len = struct.unpack(">H", self._buffer[2:4])[0]
        if frame_len != 28:
            raise RuntimeError("Invalid PM2.5 frame length")

        checksum = struct.unpack(">H", self._buffer[30:32])[0]
        check = sum(self._buffer[0:30])
        if check != checksum:
            raise RuntimeError("Invalid PM2.5 checksum")

        # unpack data
        (
            self.aqi_reading["pm10 standard"],
            self.aqi_reading["pm25 standard"],
            self.aqi_reading["pm100 standard"],
            self.aqi_reading["pm10 env"],
            self.aqi_reading["pm25 env"],
            self.aqi_reading["pm100 env"],
            self.aqi_reading["particles 03um"],
            self.aqi_reading["particles 05um"],
            self.aqi_reading["particles 10um"],
            self.aqi_reading["particles 25um"],
            self.aqi_reading["particles 50um"],
            self.aqi_reading["particles 100um"],
        ) = struct.unpack(">HHHHHHHHHHHH", self._buffer[4:28])

        return self.aqi_reading


# SPDX-FileCopyrightText: 2020 ladyada for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_pm25.i2c`
================================================================================

I2C module for CircuitPython library for PM2.5 Air Quality Sensors


* Author(s): ladyada

Implementation Notes
--------------------

**Hardware:**

* `PM2.5 Air Quality Sensor with I2C Interface - PMSA003I
  <https://www.adafruit.com/product/4505>`_

* `Adafruit PMSA003I Air Quality Breakout
  <https://www.adafruit.com/product/4632>`_


Works with most (any?) Plantower I2C interfaced PM2.5 sensor.

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases
* Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

"""


class PM25_I2C(PM25):
    """
    A module for using the PM2.5 Air quality sensor over I2C

    :param i2c_bus: The `busio.I2C` object to use.
    :param ~microcontroller.Pin reset_pin: Pin use to reset the sensor. Defaults to `None`
    :param int address: The I2C address of the device. Defaults to :const:`0x12`

    **Quickstart: Importing and using the PMSA003I Air quality sensor**

        Here is one way of importing the `PM25_I2C` class so you can use it with the name ``pm25``.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            import busio
            from adafruit_pm25.i2c import PM25_I2C

        Once this is done you can define your `busio.I2C` object and define your sensor object

        .. code-block:: python

            i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
            reset_pin = None
            pm25 = PM25_I2C(i2c, reset_pin)


        Now you have access to the air quality data using the class function
        `adafruit_pm25.PM25.read`

        .. code-block:: python

            aqdata = pm25.read()

    """

    def __init__(self, i2c_bus, address=0x12):
        for _ in range(5):  # try a few times, it can be sluggish
            try:
                self.i2c_device = I2CDevice(i2c_bus, address)
                break
            except ValueError:
                time.sleep(1)
                continue
        else:
            raise RuntimeError("Unable to find PM2.5 device")
        super().__init__()

    def _read_into_buffer(self) -> None:
        with self.i2c_device as i2c:
            try:
                i2c.readinto(self._buffer)
            except OSError as err:
                raise RuntimeError("Unable to read from PM2.5 over I2C") from err
