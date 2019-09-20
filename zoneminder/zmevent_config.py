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
EVENTS_PATH = '/usr/share/zoneminder/www/events'

#: Name of the event to send homeassistant
HASS_EVENT_NAME = 'ZM_ALARM'

#: Path to homeassistant secrets.yaml
HASS_SECRETS_PATH = '/opt/homeassistant/.homeassistant/secrets.yaml'

#: Hostname for this instance
ZM_HOSTNAME = 'guarddog'

#: Configuration populated from environment variables; see
#: :py:func:`~.populate_secrets`
CONFIG = {
    'MYSQL_DB': None,
    'MYSQL_USER': None,
    'MYSQL_PASS': None,
    'BASE_URL': 'http://redirect.jasonantman.com/zm/',
    'LOCAL_ZM_URL': 'http://localhost/zm/',
    'HASS_API_URL': 'http://localhost:8123/api',
}

if node() == 'telescreen':
    CONFIG['BASE_URL'] = 'http://redirect.jasonantman.com/telescreen/'
    EVENTS_PATH = '/var/cache/zoneminder/events/'
    ZM_HOSTNAME = 'telescreen'


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
        150 < x < 250 and
        475 < y < 570 and
        h > 900 and
        350 < w < 460 and
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
                'diningtable', 'bottle', 'umbrella', 'bird', 'cow', 'elephant'
            ],
            monitor_num=2
        ),
        # yolo3-tiny seems to randomly be classifying my kitchen window, wire
        # metal shelving and rice cooker as a person, with < 30% confidence.
        # ignore that.
        IgnoredObject(
            'KitchenShelvesAsPerson',
            ['person'],
            bounding_box=(385, 635, 15, 15),
            min_score=0.3,
            monitor_num=2
        ),
        #
        # MONITOR 3 - PORCH
        #
        # False detection for porch railing
        IgnoredObject(
            'FrontPorchLeftRailing',
            ['bench', 'chair', 'zebra'],
            monitor_num=3
        ),
        # front
        IgnoredObject(
            'Front',
            # yolo3-tiny often sees shadows on my front as strange things...
            ['suitcase', 'umbrella', 'stop sign', 'elephant'],
            monitor_num=3,
            bounding_box=(1447, 574, 500, 500)
        ),
        # yolo3-tiny thinks this tree stump in my yard is a sheep or cow...
        IgnoredObject(
            'FrontTreeStump',
            ['sheep', 'cow'],
            bounding_box=(1540, 335, 50, 50),
            monitor_num=3
        ),
        # it also gets confused about a bush in my yard
        IgnoredObject(
            'FrontShrub',
            ['sheep', 'cow', 'pottedplant'],
            bounding_box=(1300, 150, 100, 100),
            monitor_num=3
        ),
        #
        # MONITOR 4 - BACK
        #
        # grill in back yard
        IgnoredObject(
            'Grill',
            [
                'surfboard', 'suitcase', 'umbrella', 'kite', 'backpack',
                'handbag', 'toilet', 'boat',
            ],
            monitor_num=4,
            bounding_box=(840, 560, 100, 100)
        ),
        # other grill
        IgnoredObject(
            'WeberGrill',
            ['toilet', 'surfboard', 'boat', 'sports ball'],
            monitor_num=4,
            bounding_box=(1100, 830, 30, 30)
        ),
        # shadows on the storage box in the yard get recognized as weird things
        IgnoredObject(
            'BackStorageBox',
            ['toilet'],
            monitor_num=4,
            bounding_box=(700, 250, 100, 100)
        ),
        IgnoredObject(
            'BackFenceBox',
            ['pottedplant'],
            monitor_num=4,
            bounding_box=(425, 180, 150, 150)
        ),
        IgnoredObject(
            'BackStreetCar',
            ['car', 'truck', 'bus', 'train', 'kite'],
            monitor_num=4,
            zone_names=['BackFence']
        ),
        #
        # MONITOR 5 - SIDE
        #
        # ignore all the giraffes on the side of the house...
        IgnoredObject(
            'SideAnimals',
            ['giraffe', 'cow', 'sports ball'],
            monitor_num=5
        ),
        IgnoredObject(
            'SIDEperson', ['person'],
            monitor_num=5,
            callable=is_person_rectangle
        ),
        IgnoredObject(
            'SIDEhalfFrameHighPerson', ['person'],
            monitor_num=5,
            callable=is_person_over_600px_high
        ),
        IgnoredObject(
            'MikesShrubAsCar', ['car'],
            monitor_num=5,
            bounding_box=[255, 370, 20, 20]
        ),
        IgnoredObject(
            'SIDEtrailer',
            ['pottedplant'],
            monitor_num=5,
            bounding_box=(260, 520, 100, 100)
        ),
        # Ignore cars off my property...
        IgnoredObject(
            'SideStreetCar',
            ['car', 'truck', 'bus', 'train'],
            monitor_num=5,
            zone_names=['Street1']
        ),
        #
        # MONITOR 6 - OFFICE
        #
        IgnoredObject(
            'OFFICEJunk', ['traffic light'],
            monitor_num=6
        ),
        #
        # MONITOR 7 - BEDRM
        #
        IgnoredObject(
            'BEDRMJunk', ['bed', 'oven'],
            monitor_num=7
        ),
        #
        # MONITOR 8 - HALL
        #
        IgnoredObject(
            'HallStuff',
            ['parking meter', 'toilet', 'cake', 'handbag', 'teddy bear'],
            monitor_num=8
        ),
        #
        # MONITOR 9 - FRONT
        #
        # front camera front street
        IgnoredObject(
            'FrontCamFrontStreet',
            ['sheep', 'car', 'truck', 'train', 'pottedplant'],
            monitor_num=9,
            zone_names=['Street']
        ),
        # Ignore Kevin's cars
        IgnoredObject(
            'FrontCamKevinsCars',
            ['car', 'truck', 'bicycle'],
            monitor_num=9,
            bounding_box=(1000, 95, 180, 50)
        ),
        # front camera SideYardNear
        IgnoredObject(
            'FrontCamSideYardNear',
            ['pottedplant'],
            monitor_num=9,
            zone_names=['SideYardNear']
        ),
        # garage
        IgnoredObject(
            'GarageFrontCam',
            ['boat'],
            monitor_num=9,
            zone_names=['GarageSide']
        ),
        # garage identified as person
        IgnoredObject(
            'GARAGEasPerson', ['person'],
            monitor_num=9,
            callable=is_garage_as_person
        ),
    ]
}

#: List of Monitor IDs to never send to HASS
HASS_IGNORE_MONITOR_IDS = [
    11,
    12
]

#: List of zones to never send to HASS, per monitor
HASS_IGNORE_MONITOR_ZONES = {
    9: set(['RoadCamera'])
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
