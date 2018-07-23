"""
Configuration for zmevent_handler.py and related scripts.
"""

import json
from datetime import datetime
from decimal import Decimal
from zmevent_object_filter import IgnoredObject

#: If logging to a file, the file path to log to.
LOG_PATH = '/var/cache/zoneminder/temp/zmevent_handler.log'

#: Minimum log level to run with. This can be used to enable debug logging
#: in the script itself overriding the command-line arguments, i.e. if you're
#: debugging the script but don't want to edit whatever calls it.
MIN_LOG_LEVEL = 1

#: Name of the MySQL table in the zoneminder database to store results in.
ANALYSIS_TABLE_NAME = 'zmevent_handler_ImageAnalysis'

#: Path on disk where ZoneMinder events are stored
EVENTS_PATH = '/usr/share/zoneminder/www/events'

#: Name of the event to send homeassistant
HASS_EVENT_NAME = 'ZM_ALARM'

#: Configuration populated from environment variables; see
#: :py:func:`~.populate_secrets`
CONFIG = {
    'MYSQL_DB': None,
    'MYSQL_USER': None,
    'MYSQL_PASS': None,
    'BASE_URL': None,  # ZoneMinder base URL, i.e.: http://localhost/zm/
    'HASS_API_URL': None,  # usually should be: http://localhost:8123/api
}

#: IgnoredObject instances to filter objects out from detection results
IGNORED_OBJECTS = [
    # False detection for porch railing
    IgnoredObject(
        'FrontPorchLeftRailing',
        ['bench', 'chair', 'zebra'],
        monitor_num=3,
        bounding_box=(470, 430, 300, 300)
    ),
    # my car when parked
    IgnoredObject(
        'MyCarParked',
        ['car'],
        monitor_num=3,
        bounding_box=(1550, 730, 200, 200)
    ),
    # grill in back yard
    IgnoredObject(
        'Grill',
        ['surfboard', 'suitcase', 'umbrella'],
        monitor_num=4,
        bounding_box=(1070, 575, 100, 100)
    ),
    # ignore... stuff... inside the house
    IgnoredObject(
        'IndoorStuff',
        ['cup', 'dog', 'cat', 'book', 'tvmonitor'],
        monitor_num=2
    )
    # yolo3-tiny seems to randomly be classifying my kitchen window, wire
    # metal shelving and rice cooker as a person, with < 30% confidence.
    # ignore that.
    # x=386 y=637 w=352 h=825
]


class DateSafeJsonEncoder(json.JSONEncoder):
    """
    Subclass of :py:class:`json.JSONEncoder` with special logic for some types.

    - :py:class:`datetime.datetime` objects are serialized as strings in
      ``%Y-%m-%d %H:%M:%S`` format
    - :py:class:`decimal.Decimal` objects are serialized as floats
    - Objects with ``as_dict`` properties are serialized as the dict returned
      by that property.
    """

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, 'as_dict'):
            return obj.as_dict
        return json.JSONEncoder.default(self, obj)