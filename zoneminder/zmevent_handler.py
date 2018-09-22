#!/usr/bin/env python3
"""
My Python script for handling ZoneMinder events. This is called by
zmeventnotification.pl.

<https://github.com/jantman/home-automation-configs/blob/master/zoneminder/zmevent_handler.py>

Configuration is in ``zmevent_config.py``.

Program flow:

- Called from zmeventnotification.pl with EventID, MonitorID and possible Cause.
  The event may still be in progress when called.
- Populate Event information from the ZoneMinder database into objects.
- Run Filters on the images in the event, such as detecting switch between color
  and B&W (IR).
- Feed images through darknet yolo3 object detection; capture object detection
  results as well as which Zone each object is in.
  - Optionally ignore certain object labels/categories, optionally by Monitor
    ID, Zone, and/or bounding box rectangle.
- Pass the results of all this on to HASS via an event, that will be handled
  by an AppDaemon app.

The functionality of this script relies on the other ``zmevent_*.py`` modules
in this git repo.
"""

import sys
import os
import logging
from systemd.journal import JournalHandler
import argparse
import json
import time
import re
from collections import defaultdict

try:
    import requests
except ImportError:
    raise SystemExit(
        'could not import requests - please "pip install requests"'
    )
try:
    import pymysql
except ImportError:
    raise SystemExit(
        'could not import pymysql - please "pip install PyMySQL"'
    )
try:
    from PIL import Image
except ImportError:
    raise SystemExit(
        'could not import PIL - please "pip install Pillow"'
    )

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder,
    HASS_EVENT_NAME, CONFIG
)
from zmevent_image_analysis import YoloAnalyzer, ImageAnalysisWrapper
from zmevent_models import ZMEvent
from zmevent_filters import *

#: A list of the :py:class:`~.ImageAnalyzer` subclasses to use for each frame.
ANALYZERS = [YoloAnalyzer]

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='handler for Motion events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False, help='do not send notifications')
    p.add_argument('-f', '--foreground', dest='foreground', action='store_true',
                   default=False, help='log to foreground instead of file')
    p.add_argument('-E', '--event-id', dest='event_id', action='store',
                   type=int, help='Event ID', required=True)
    p.add_argument('-M', '--monitor-id', dest='monitor_id', action='store',
                   type=int, help='Monitor ID')
    p.add_argument('-C', '--cause', dest='cause', action='store', type=str,
                   help='event cause')
    args = p.parse_args(argv)
    return args


def populate_secrets():
    """Populate the ``CONFIG`` global from environment variables."""
    global CONFIG
    for varname in CONFIG.keys():
        if varname not in os.environ:
            raise RuntimeError(
                'ERROR: Variable %s must be set in environment' % varname
            )
        CONFIG[varname] = os.environ[varname]


def get_basicconfig_kwargs(args):
    """Return a dict of kwargs for :py:func:`logging.basicConfig`."""
    log_kwargs = {
        'level': logging.WARNING,
        'format': "[%(asctime)s %(levelname)s][%(process)d] %(message)s"
    }
    if not args.foreground:
        log_kwargs['filename'] = LOG_PATH
    # set logging level
    if args.verbose > 1 or (MIN_LOG_LEVEL is not None and MIN_LOG_LEVEL > 1):
        log_kwargs['level'] = logging.DEBUG
        log_kwargs['format'] = "%(asctime)s [%(process)d - %(levelname)s " \
                               "%(filename)s:%(lineno)s - %(name)s." \
                               "%(funcName)s() ] %(message)s"
    elif (
        args.verbose == 1 or (MIN_LOG_LEVEL is not None and MIN_LOG_LEVEL == 1)
    ):
        log_kwargs['level'] = logging.INFO
        log_kwargs['format'] = '%(asctime)s [%(process)d] %(levelname)s:' \
                               '%(name)s:%(message)s'
    return log_kwargs


def setup_logging(args):
    global logger
    kwargs = get_basicconfig_kwargs(args)
    logging.basicConfig(**kwargs)
    logger = logging.getLogger()
    if args.foreground:
        return
    # if not running in foreground, log to journald also
    logger.addHandler(JournalHandler())


def send_to_hass(json_str, event_id):
    logger.info(json_str)
    url = '%s/events/%s' % (CONFIG['HASS_API_URL'], HASS_EVENT_NAME)
    count = 0
    while count < 13:
        count += 1
        try:
            logger.debug('Try POST to: %s', url)
            r = requests.post(
                url, data=json_str, timeout=5,
                headers={'Content-Type': 'application/json'}
            )
            r.raise_for_status()
            assert 'message' in r.json()
            logger.info('Event successfully posted to HASS: %s', r.text)
            return
        except Exception:
            logger.error('Error POSTing to HASS at %s: %s', url, r.text)
    fname = os.path.join(
        os.path.dirname(LOG_PATH), 'event_%s.json' % event_id
    )
    with open(fname, 'w') as fh:
        fh.write(json_str)
    logger.critical('Event not sent to HASS; persisted to: %s', fname)


def _set_event_name(event_id, name, dry_run=False):
    if dry_run:
        logger.warning('WOULD rename event %s to: %s', event_id, name)
        return
    logger.info('Renaming event %s to: %s', event_id, name)
    r = requests.put(
        'http://localhost/zm/api/events/%s.json' % event_id,
        data={'Event[Name]': name}
    )
    r.raise_for_status()
    assert r.json()['message'] == 'Saved'
    logger.debug('Event renamed.')


def update_event_name(event, analysis, dry_run=False):
    if event.Cause != 'Motion':
        _set_event_name(
            event.EventId, '%s-NotMotion' % event.Name, dry_run=dry_run
        )
        return
    m = re.match(
        r'^Motion: (([A-Za-z0-9,]+\s?)*).*$', event.Notes
    )
    if not m:
        _set_event_name(
            event.EventId, '%s-UnknownZones' % event.Name, dry_run=dry_run
        )
        return
    zones = [x.strip() for x in m.group(1).split(',')]
    objects = defaultdict(int)
    for odr in analysis:
        for od in odr.detections:
            motion_zones = set(zones).intersection(set(od._zones.keys()))
            if not motion_zones:
                # this object isn't in any of the zones that had motion
                continue
            # else the object was in a zone that had motion
            if od._score > objects[od._label]:
                objects[od._label] = od._score
    if len(objects) == 0:
        _set_event_name(
            event.EventId,
            '%s-NoObject-%s' % (event.Name, ','.join(zones)),
            dry_run=dry_run
        )
        return
    # else we have objects detected in zones with motion
    name = event.Name + '-'
    for label, _ in sorted(objects.items(), key=lambda kv: kv[1], reverse=True):
        if len(name + label + ',') > 63:
            break
        name += label + ','
    name = name.strip(',')
    _set_event_name(event.EventId, name, dry_run=dry_run)


def run(args):
    # populate the event from ZoneMinder DB
    event = ZMEvent(args.event_id, args.monitor_id, args.cause)
    # ensure that this command is run by the user that owns the event
    evt_owner = os.stat(event.path).st_uid
    if os.geteuid() != evt_owner:
        raise RuntimeError(
            'This command may only be run by the user that owns %s: UID %s'
            ' (not UID %s)', event.path, evt_owner, os.geteuid()
        )
    logger.debug('Loaded event: %s', event.as_json)
    # wait for the event to finish - we wait up to 30s then continue
    event.wait_for_finish()
    result = {
        'event': event,
        'filters': [],
        'object_detections': []
    }
    # run filters on event
    logger.debug('Running filters on %s', event)
    for cls in EventFilter.__subclasses__():
        try:
            logger.debug('Filter: %s', cls)
            f = cls(event)
            f.run()
            result['filters'].append(f)
        except Exception:
            logger.critical(
                'Exception running filter %s on event %s',
                cls, event, exc_info=True
            )
    # run object detection on the event
    try:
        analyzer = ImageAnalysisWrapper(event, ANALYZERS)
        analysis = analyzer.analyze_event()
        result['object_detections'] = analysis
        update_event_name(event, analysis, dry_run=args.dry_run)
    except Exception:
        logger.critical(
            'ERROR running ImageAnalysisWrapper on event: %s', event,
            exc_info=True
        )
    res_json = json.dumps(
        result, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
    )
    if args.dry_run:
        logger.warning('Would POST to HASS: %s', res_json)
        return
    send_to_hass(res_json, event.EventId)


def main():
    # setsid so we can continue running even if caller dies
    os.setsid()
    # populate secrets from environment variables
    populate_secrets()
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # setup logging
    setup_logging(args)
    # initial log
    logger.warning(
        'Triggered; EventId=%s MonitorId=%s Cause=%s',
        args.event_id, args.monitor_id, args.cause
    )
    # run...
    run(args)


if __name__ == "__main__":
    main()
