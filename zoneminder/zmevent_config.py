"""
Configuration for zmevent_handler.py and related scripts.
"""

import os
import re
import json
from datetime import datetime
from decimal import Decimal
from zmevent_object_filter import IgnoredObject
from platform import node

#: If logging to a file, the file path to log to.
LOG_PATH = '/var/cache/zoneminder/temp/zmevent_handler.log'

#: Minimum log level to run with. This can be used to enable debug logging
#: in the script itself overriding the command-line arguments, i.e. if you're
#: debugging the script but don't want to edit whatever calls it.
MIN_LOG_LEVEL = 1

#: Name of the MySQL table in the zoneminder database to store results in.
ANALYSIS_TABLE_NAME = 'zmevent_handler_ImageAnalysis'

#: Path on disk where ZoneMinder events are stored
EVENTS_PATH = '/var/cache/zoneminder/events/'

#: Name of the event to send homeassistant
HASS_EVENT_NAME = 'ZM_ALARM'

#: Path to homeassistant secrets.yaml
HASS_SECRETS_PATH = '/opt/homeassistant/.homeassistant/secrets.yaml'

#: Hostname for this instance
ZM_HOSTNAME = 'guarddog'

#: statsd hostname/ip to send metrics to; set to None to disable
STATSD_HOST = '192.168.0.24'

#: statsd port
STATSD_PORT = 8125

#: Directory to store retry files in
RETRY_DIR = '/var/cache/zoneminder/analysis-retries/'

#: Configuration populated from environment variables; see
#: :py:func:`~.populate_secrets`
CONFIG = {
    'MYSQL_DB': None,
    'MYSQL_USER': None,
    'MYSQL_PASS': None,
    'BASE_URL': 'http://redirect.jasonantman.com/zm/',
    'LOCAL_ZM_URL': 'http://localhost/zm/',
    'HASS_API_URL': 'http://localhost:8123/api',
    'HASS_TOKEN': None,
}

if node() == 'telescreen':
    CONFIG['BASE_URL'] = 'http://redirect.jasonantman.com/telescreen/'
    ZM_HOSTNAME = 'telescreen'
    CONFIG['HASS_API_URL'] = 'http://192.168.0.102:8123/api'


def populate_secrets():
    """Populate the ``CONFIG`` global from environment variables."""
    global CONFIG
    for varname in CONFIG.keys():
        if CONFIG[varname] is not None:
            continue
        if varname not in os.environ:
            raise RuntimeError(
                'ERROR: Variable %s must be set in environment' % varname
            )
        CONFIG[varname] = os.environ[varname]


def is_person_over_600px_high(i, label, x, y, w, h, zones, score):
    """
    Custom method to match "person" objects that are more than 600px (over half
    the frame) high.
    """
    return h >= 600


def is_person_rectangle(i, label, x, y, w, h, zones, score):
    """
    ``i`` is an IgnoredObject instance. This is a custom method to match the
    weird false "person" detection in the trees on SIDE.
    Returns True if object should be ignored.
    """
    if (
        h > 900 and
        label == 'person'
    ):
        return True
    return False


def is_garage_as_person(i, label, x, y, w, h, zones, score):
    """
    ``i`` is an IgnoredObject instance. This is a custom method to match the
    cases where the garage is identified as a person.
    Returns True if object should be ignored.
    """
    if (
        1400 < x < 1650 and
        450 < y < 650 and
        h > 800 and
        w > 550 and
        label == 'person'
    ):
        return True
    return False


#: IgnoredObject instances to filter objects out from detection results
IGNORED_OBJECTS = {
    'guarddog': [
        #
        # MONITOR 2 - LRKitchen
        #
        # ignore... stuff... inside the house
        IgnoredObject(
            'IndoorStuff',
            [
                'cup', 'dog', 'cat', 'book', 'tvmonitor', 'remote', 'sofa',
                'sink', 'bowl', 'refrigerator', 'laptop', 'chair',
                'diningtable', 'bottle', 'umbrella', 'bird', 'cow', 'elephant',
                'bench',
            ],
            monitor_num=2
        ),
        #
        # MONITOR 3 - PORCH
        #
        IgnoredObject(
            'Front',
            # yolo3-tiny often sees shadows on my front as strange things...
            ['suitcase', 'umbrella', 'stop sign', 'elephant'],
            monitor_num=3,
            bounding_box=(1447, 574, 500, 500)
        ),
        #
        # MONITOR 4 - BACK
        #
        IgnoredObject(
            'BackCrap',
            ['chair', 'bench', 'diningtable', 'umbrella'],
            monitor_num=4,
        ),
        IgnoredObject(
            'BackStreetCar',
            ['car', 'truck', 'bus', 'train', 'kite', 'boat'],
            monitor_num=4,
            zone_names=['BackFence']
        ),
        #
        # MONITOR 5 - SIDE
        #
        # Ignore cars off my property...
        IgnoredObject(
            'SideVehicles',
            ['car', 'truck', 'bus', 'train', 'fire hydrant'],
            monitor_num=5,
        ),
        IgnoredObject(
            'SideGiantPerson',
            ['person'],
            monitor_num=5,
            callable=is_person_rectangle,
        ),
        IgnoredObject(
            'SideCrap',
            ['toothbrush', 'traffic light', 'giraffe', 'banana', 'baseball bat', 'sports ball', 'frisbee'],
            monitor_num=5,
        ),
        IgnoredObject(
            'SidePersonInStreet',
            ['person'],
            monitor_num=5,
            zone_names=['Street1', 'Street2'],
        ),
        IgnoredObject(
            'SidePersonNoZone',
            ['person'],
            monitor_num=5,
            no_zone=True,
        ),
        #
        # MONITOR 6 - OFFICE
        #
        IgnoredObject(
            'OfficeCrap',
            ['bicycle',],
            monitor_num=6,
        ),
        #
        # MONITOR 7 - BEDRM
        #
        IgnoredObject(
            'BEDRMJunk', ['bed'],
            monitor_num=7
        ),
        #
        # MONITOR 8 - HALL
        #
        IgnoredObject(
            'HallStuff',
            [
                'parking meter', 'toilet', 'cake', 'handbag', 'teddy bear',
                'backpack', 'bench', 'suitcase',
            ],
            monitor_num=8
        ),
        IgnoredObject(
            'HallWaterBottle',
            ['person'], bounding_box=(1503, 288, 20, 20),
            monitor_num=8
        ),
        #
        # MONITOR 9 - FRONT
        #
        # front camera front street
        IgnoredObject(
            'FrontCamFrontStreet',
            ['car', 'truck', 'train'],
            monitor_num=9,
            zone_names=['Street']
        ),
        IgnoredObject(
            'FrontCamNoZone',
            ['car', 'truck', 'train'],
            monitor_num=9,
            no_zone=True,
        ),
        # Ignore Kevin's cars
        IgnoredObject(
            'FrontCamKevinsCars',
            ['car', 'truck', 'bicycle'],
            monitor_num=9,
            bounding_box=(1000, 95, 180, 50)
        ),
        IgnoredObject(
            'FrontJunk',
            ['pottedplant', 'bench',],
            monitor_num=9,
        ),
        IgnoredObject(
            'FrontRoadCamera',
            ['person'],
            zone_names=['RoadCamera'],
            monitor_num=9,
        ),
        IgnoredObject(
            'FrontNoZone',
            ['person'],
            no_zone=True,
            monitor_num=9,
        ),
        IgnoredObject(
            'GarageAsUmbrella',
            ['umbrella'],
            monitor_num=9,
            bounding_box=(1599,652,40,40),
        ),
        #
        # MONITOR 10 - GARAGE
        #
        IgnoredObject(
            'GarageCrap',
            ['aeroplane', 'car', 'toaster', 'truck', 'toilet', 'parking meter', 'suitcase'],
            monitor_num=10,
        ),
    ],
    'telescreen': [
        #
        # MONITOR 3 - GATE
        #
        IgnoredObject(
            'GateCrap',
            # yolo4 often sees shadows on my front as strange things...
            ['boat', 'bench', 'baseball bat', 'frisbee', 'sports ball', 'traffic light', 'stop sign', 'tennis racket', 'umbrella'],
            monitor_num=3,
        ),
    ]
}

#: List of Monitor IDs to never send to HASS
HASS_IGNORE_MONITOR_IDS = {
    'guarddog': [
        11,
        12
    ]
}

#: List of zones to never send to HASS, per monitor
HASS_IGNORE_MONITOR_ZONES = {
    'guarddog': {
        9: set(['RoadCamera'])
    }
}

#: List of Event Name regexes to never send to HASS
HASS_IGNORE_EVENT_NAME_RES = [
    re.compile(r'^FRONT-.*-RoadCamera$')
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
