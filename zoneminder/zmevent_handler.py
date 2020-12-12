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
from platform import node

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
    HASS_EVENT_NAME, CONFIG, HASS_IGNORE_MONITOR_IDS, populate_secrets,
    HASS_IGNORE_EVENT_NAME_RES, HASS_IGNORE_MONITOR_ZONES
)
from zmevent_analyzer import ImageAnalysisWrapper
from zmevent_models import ZMEvent
from zmevent_filters import *
from zmevent_ir_change import handle_ir_change
from statsd_utils import statsd_increment_counter, statsd_send_time

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None
NODE_NAME = node()


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


def setup_library_logging():
    global logger
    logger = logging.getLogger('zmevent_handler')


def send_to_hass(json_str, event_id):
    logger.info(json_str)
    url = '%s/events/%s' % (CONFIG['HASS_API_URL'], HASS_EVENT_NAME)
    count = 0
    start = time.time()
    while count < 13:
        count += 1
        r = None
        try:
            logger.debug('Try POST to: %s', url)
            r = requests.post(
                url, data=json_str, timeout=5,
                headers={'Content-Type': 'application/json'}
            )
            r.raise_for_status()
            assert 'message' in r.json()
            logger.info('Event successfully posted to HASS: %s', r.text)
            statsd_send_time(
                'zmevent_handler.send_to_hass.success',
                time.time() - start
            )
            return
        except Exception as exc:
            statsd_send_time(
                'zmevent_handler.send_to_hass.failures',
                time.time() - start
            )
            if r is not None:
                logger.error('Error POSTing to HASS at %s: %s', url, r.text)
            else:
                logger.error('Error POSTing to HASS at %s: %s', url, exc)
    statsd_send_time(
        'zmevent_handler.send_to_hass.unrecoverable_failure_time',
        time.time() - start
    )
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
        '%sapi/events/%s.json' % (CONFIG['LOCAL_ZM_URL'], event_id),
        data={'Event[Name]': name}
    )
    r.raise_for_status()
    assert r.json()['message'] == 'Saved'
    logger.debug('Event renamed.')


def update_event_name(event, analysis, filters, dry_run=False):
    for f in filters:
        if f.matched:
            event.Name += '-' + f.suffix
    if event.Cause != 'Motion':
        _set_event_name(
            event.EventId, '%s-NotMotion' % event.Name, dry_run=dry_run
        )
        return '%s-NotMotion' % event.Name, []
    m = re.match(
        r'^Motion: (([A-Za-z0-9,]+\s?)*).*$', event.Notes
    )
    if not m:
        _set_event_name(
            event.EventId, '%s-UnknownZones' % event.Name, dry_run=dry_run
        )
        return '%s-UnknownZones' % event.Name, []
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
        return '%s-NoObject-%s' % (event.Name, ','.join(zones)), zones
    # else we have objects detected in zones with motion
    name = event.Name + '-'
    for label, _ in sorted(objects.items(), key=lambda kv: kv[1], reverse=True):
        if len(name + label + ',') > 63:
            break
        name += label + ','
    name = name.strip(',')
    _set_event_name(event.EventId, name, dry_run=dry_run)
    return name, zones


def handle_event(event_id, monitor_id, cause, dry_run=False):
    event = ZMEvent(event_id, monitor_id, cause)
    # ensure that this command is run by the user that owns the event
    evt_owner = os.stat(event.path).st_uid
    if os.geteuid() != evt_owner:
        raise RuntimeError(
            'This command may only be run by the user that owns %s: UID %s'
            ' (not UID %s)' % (event.path, evt_owner, os.geteuid())
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
            if cls == IRChangeFilter and f.matched:
                logger.debug(
                    'Handle IRChangeFilter for Monitor %s Event %s',
                    event.MonitorId, event.EventId
                )
                try:
                    handle_ir_change(event, f)
                except Exception:
                    logger.critical(
                        'Exception running handle_ir_change on Event %s',
                        event.EventId, exc_info=True
                    )
        except Exception:
            logger.critical(
                'Exception running filter %s on event %s',
                cls, event, exc_info=True
            )
    # run object detection on the event
    zones = []
    try:
        analyzer = ImageAnalysisWrapper(event, ['Yolo4Analyzer'], NODE_NAME)
        analysis = analyzer.analyze_event()
        result['object_detections'] = analysis
        new_name, zones = update_event_name(
            event, analysis, result['filters'], dry_run=dry_run
        )
        result['event'].Name = new_name
    except Exception:
        logger.critical(
            'ERROR running ImageAnalysisWrapper on event: %s', event,
            exc_info=True
        )
    return result, zones


def run(args):
    if 'End:' not in args.cause:
        logger.info(
            'Not handling un-ended event: %s (Cause: %s)' % (
                args.event_id, args.cause
            )
        )
        return
    # populate the event from ZoneMinder DB
    result, zones = handle_event(
        args.event_id, args.monitor_id, args.cause, dry_run=args.dry_run
    )
    if args.monitor_id in HASS_IGNORE_MONITOR_IDS.get(NODE_NAME, []):
        logger.info(
            'Not sending Event %s for monitor %s to HASS - MonitorId '
            'in HASS_IGNORE_MONITOR_IDS[%s]',
            result['event'].EventId, args.monitor_id, NODE_NAME
        )
        return
    for r in HASS_IGNORE_EVENT_NAME_RES:
        if r.match(result['event'].Name):
            logger.info(
                'Not sending Event %s for monitor %s to HASS - event name '
                '%s matches regex %s',
                result['event'].EventId, args.monitor_id,
                result['event'].Name, r.pattern
            )
            return
    ignored_zones = HASS_IGNORE_MONITOR_ZONES.get(
        NODE_NAME, {}
    ).get(args.monitor_id, set([]))
    if set(zones).issubset(ignored_zones):
        logger.info(
            'Not sending Event %s for monitor %s to HASS - zones (%s) '
            'are subset of ignored (%s)',
            result['event'].EventId, args.monitor_id,
            zones, ignored_zones
        )
        return
    result['hostname'] = NODE_NAME
    res_json = json.dumps(
        result, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
    )
    if args.dry_run:
        logger.warning('Would POST to HASS: %s', res_json)
        return
    send_to_hass(res_json, args.event_id)


def main():
    # setsid so we can continue running even if caller dies
    if os.environ.get('NO_SETSID', None) != 'true':
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
