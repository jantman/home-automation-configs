# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_shtc3`
================================================================================

A helper library for using the Sensirion SHTC3 Humidity and Temperature Sensor


* Author(s): Bryan Siepert

Implementation Notes
--------------------

**Hardware:**

* `Adafruit SHTC3 Temperature & Humidity Sensor
  <https://www.adafruit.com/product/4636>`_ (Product ID: 4636)

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's Bus Device library:
  https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

* Adafruit's Register library:
  https://github.com/adafruit/Adafruit_CircuitPython_Register

"""

# imports

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_SHTC3.git"

from struct import unpack_from
import time
from adafruit_bus_device import i2c_device


# include "Arduino.h"
# include <Adafruit_I2CDevice.h>
# include <Adafruit_Sensor.h>

_SHTC3_DEFAULT_ADDR = 0x70  # SHTC3 I2C Address
_SHTC3_NORMAL_MEAS_TFIRST_STRETCH = (
    0x7CA2  # Normal measurement, temp first with Clock Stretch Enabled
)
_SHTC3_LOWPOW_MEAS_TFIRST_STRETCH = (
    0x6458  # Low power measurement, temp first with Clock Stretch Enabled
)
_SHTC3_NORMAL_MEAS_HFIRST_STRETCH = (
    0x5C24  # Normal measurement, hum first with Clock Stretch Enabled
)
_SHTC3_LOWPOW_MEAS_HFIRST_STRETCH = (
    0x44DE  # Low power measurement, hum first with Clock Stretch Enabled
)

_SHTC3_NORMAL_MEAS_TFIRST = (
    0x7866  # Normal measurement, temp first with Clock Stretch disabled
)
_SHTC3_LOWPOW_MEAS_TFIRST = (
    0x609C  # Low power measurement, temp first with Clock Stretch disabled
)
_SHTC3_NORMAL_MEAS_HFIRST = (
    0x58E0  # Normal measurement, hum first with Clock Stretch disabled
)
_SHTC3_LOWPOW_MEAS_HFIRST = (
    0x401A  # Low power measurement, hum first with Clock Stretch disabled
)

_SHTC3_READID = 0xEFC8  # Read Out of ID Register
_SHTC3_SOFTRESET = 0x805D  # Soft Reset
_SHTC3_SLEEP = 0xB098  # Enter sleep mode
_SHTC3_WAKEUP = 0x3517  # Wakeup mode
_SHTC3_CHIP_ID = 0x807


class SHTC3:
    """
    A driver for the SHTC3 temperature and humidity sensor.

    :param ~busio.I2C i2c_bus: The I2C bus the SHTC3 is connected to.

    **Quickstart: Importing and using the SHTC3 temperature and humidity sensor**

        Here is an example of using the :class:`SHTC3`.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            import adafruit_shtc3

        Once this is done, you can define your `board.I2C` object and define your sensor

        .. code-block:: python

            i2c = board.I2C()   # uses board.SCL and board.SDA
            sht = adafruit_shtc3.SHTC3(i2c)

        Now you have access to the temperature and humidity using the :attr:`measurements`.
        it will return a tuple with the :attr:`temperature` and :attr:`relative_humidity`
        measurements

        .. code-block:: python

            temperature, relative_humidity = sht.measurements

    """

    def __init__(self, i2c_bus):
        self.i2c_device = i2c_device.I2CDevice(i2c_bus, _SHTC3_DEFAULT_ADDR)

        self._buffer = bytearray(6)
        self.low_power = False
        self.sleeping = False
        self.reset()
        self._chip_id = self._get_chip_id()
        if self._chip_id != _SHTC3_CHIP_ID:
            raise RuntimeError("Failed to find an SHTC3 sensor - check your wiring!")

    def _write_command(self, command):
        """helper function to write a command to the i2c device"""
        self._buffer[0] = command >> 8
        self._buffer[1] = command & 0xFF

        with self.i2c_device as i2c:
            i2c.write(self._buffer, start=0, end=2)

    def _get_chip_id(self):  #   readCommand(SHTC3_READID, data, 3);
        """Determines the chip id of the sensor"""
        self._write_command(_SHTC3_READID)
        time.sleep(0.001)
        with self.i2c_device as i2c:
            i2c.readinto(self._buffer)

        return unpack_from(">H", self._buffer)[0] & 0x083F

    def reset(self):
        """Perform a soft reset of the sensor, resetting all settings to their power-on defaults"""
        self.sleeping = False
        try:
            self._write_command(_SHTC3_SOFTRESET)

        except RuntimeError as run_err:
            if run_err.args and run_err.args[0] != "I2C device address was NACK'd":
                raise run_err
        time.sleep(0.001)

    @property
    def sleeping(self):
        """Determines the sleep state of the sensor"""
        return self._cached_sleep

    @sleeping.setter
    def sleeping(self, sleep_enabled):
        if sleep_enabled:
            self._write_command(_SHTC3_SLEEP)
        else:
            self._write_command(_SHTC3_WAKEUP)
        time.sleep(0.001)
        self._cached_sleep = sleep_enabled

    # lowPowerMode(bool readmode) { _lpMode = readmode

    @property
    def low_power(self):
        """Enables the less accurate low power mode, trading accuracy for power consumption"""
        return self._low_power

    @low_power.setter
    def low_power(self, low_power_enabled):
        self._low_power = low_power_enabled

    @property
    def relative_humidity(self):
        """The current relative humidity in % rH. This is a value from 0-100%."""
        return self.measurements[1]

    @property
    def temperature(self):
        """The current temperature in degrees Celsius"""
        return self.measurements[0]

    @property
    def measurements(self):
        """both `temperature` and `relative_humidity`, read simultaneously"""

        self.sleeping = False
        temperature = None
        humidity = None
        # send correct command for the current power state
        if self.low_power:
            self._write_command(_SHTC3_LOWPOW_MEAS_TFIRST)
            time.sleep(0.001)
        else:
            self._write_command(_SHTC3_NORMAL_MEAS_TFIRST)
            time.sleep(0.013)

        # self._buffer = bytearray(6)
        # read the measured data into our buffer
        with self.i2c_device as i2c:
            i2c.readinto(self._buffer)

        # separate the read data
        temp_data = self._buffer[0:2]
        temp_crc = self._buffer[2]
        humidity_data = self._buffer[3:5]
        humidity_crc = self._buffer[5]

        # check CRC of bytes
        if temp_crc != self._crc8(temp_data) or humidity_crc != self._crc8(
            humidity_data
        ):
            return (temperature, humidity)

        # decode data into human values:
        # convert bytes into 16-bit signed integer
        # convert the LSB value to a human value according to the datasheet
        raw_temp = unpack_from(">H", temp_data)[0]
        raw_temp = ((4375 * raw_temp) >> 14) - 4500
        temperature = raw_temp / 100.0

        # repeat above steps for humidity data
        raw_humidity = unpack_from(">H", humidity_data)[0]
        raw_humidity = (625 * raw_humidity) >> 12
        humidity = raw_humidity / 100.0

        self.sleeping = True
        return (temperature, humidity)

    ## CRC-8 formula from page 14 of SHTC3 datasheet
    # https://media.digikey.com/pdf/Data%20Sheets/Sensirion%20PDFs/HT_DS_SHTC3_D1.pdf
    # Test data [0xBE, 0xEF] should yield 0x92

    @staticmethod
    def _crc8(buffer):
        """verify the crc8 checksum"""
        crc = 0xFF
        for byte in buffer:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc = crc << 1
        return crc & 0xFF  # return the bottom 8 bits
