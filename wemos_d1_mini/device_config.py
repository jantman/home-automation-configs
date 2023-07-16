DEVICE_CONFIG = {
    # humidor_sht85
    'f4cfa2d0a226': {
        'entity': 'sensor.500291c9b1a3',
        'friendly_name': 'Humidor',
        'files': {
            'humidor_sht85.py': 'main.py',
            'i2c_device.py': 'i2c_device.py',
        },
        'hostname': 'esp8266-humidor',
    },
    # temp_sensor
    'f008d1d18790': {
        'entity': 'sensor.porch_temp',
        'friendly_name': 'Porch Temp',
        'files': {
            'temp_sensor.py': 'main.py'
        },
        'hostname': 'esp32-porch-temp',
    },
    'bcddc2b67528': {
        'entity': 'sensor.chest_freezer_temp',
        'friendly_name': 'Chest Freezer Temp',
        'files': {
            'temp_sensor.py': 'main.py'
        },
        'hostname': 'esp8266-chest-freezer',
    },
    'bcddc2b66c5a': {
        'entity': 'sensor.kitchen_freezer_temp',
        'friendly_name': 'Kitchen Freezer Temp',
        'files': {
            'temp_sensor.py': 'main.py'
        },
        'hostname': 'esp8266-kitchen-freezer',
    },
    # air quality sensor
    '7c9ebd66d880': {
        'entity': 'sensor.air_quality',
        'friendly_name': 'Air Quality',
        'files': {
            'air_sensor.py': 'main.py',
            'sgp30.py': 'sgp30.py',
            'adafruit_bus_device_i2c.py': 'adafruit_bus_device_i2c.py',
            'pm25_i2c.py': 'pm25_i2c.py',
            'adafruit_shtc3.py': 'adafruit_shtc3.py',
        },
        'hostname': 'airsensor',
    },
}
