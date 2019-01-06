"""
ActivityWatch device-tracker

Maintain a bucket in ActivityWatch <https://activitywatch.net/> for a device
tracker location.
"""

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime
import os
import requests
import json
import socket

from sane_app_logging import SaneLoggingApp

#: Entity ID for the Device Tracker
DEVICE_TRACKER_ENTITY = 'device_tracker.02157df2c2d6e627'

#: The host that ActivityWatch is running on
AW_HOST = '192.168.0.24'

#: The port that ActivityWatch is running on
AW_PORT = 5600

#: Absolute path to a file on disk where we save state, so events persist
#: across AppDaemon restarts.
STATE_PATH = os.path.realpath(
    os.path.expanduser('~/.activitywatch_device_tracker')
)

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


class ActivityWatchDeviceTracker(hass.Hass, SaneLoggingApp):
    """
    ActivityWatch device tracker
    """

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ActivityWatchDeviceTracker...")
        self._base_url = 'http://%s:%d/api/0/' % (AW_HOST, AW_PORT)
        self._bucket_id = 'aw-watcher-hass-device'
        self._create_bucket()
        c_state = self.get_state(DEVICE_TRACKER_ENTITY)
        self.start_dt, self.current_state = self._load_state(c_state)
        if self.current_state != c_state:
            # else we had a state change while stopped
            self.send_event(self.current_state, self.start_dt)
            self.start_dt = datetime.utcnow()
            self.current_state = c_state
        self.listen_state(self.state_change, DEVICE_TRACKER_ENTITY)
        self._log.info('Done initializing ActivityWatchDeviceTracker.')

    def _create_bucket(self):
        url = self._base_url + 'buckets/%s' % self._bucket_id
        headers = {"Content-type": "application/json", "charset": "utf-8"}
        data = {
            'client': 'aw-watcher-hass-device',
            'hostname': socket.gethostname(),
            'type': 'currentwindow'
        }
        self._log.debug('POST to %s: %s', url, data)
        r = requests.post(
            url, data=bytes(json.dumps(data), "utf8"), headers=headers
        )
        self._log.debug('Response %s: %s', r.status_code, r.text)
        r.raise_for_status()

    def _load_state(self, c_state):
        start_dt = datetime.utcnow()
        if not os.path.exists(STATE_PATH):
            return start_dt, c_state
        self._log.debug('State path exists (%s); reading', STATE_PATH)
        with open(STATE_PATH, 'r') as fh:
            raw = fh.read().strip()
        self._log.debug('State path content: "%s"', raw)
        if raw == '':
            return start_dt, c_state
        parts = raw.split(':', 1)
        current_state = parts[1]
        start_dt = datetime.utcfromtimestamp(int(parts[0]))
        self._log.debug(
            'Load from STATE_PATH: current_state=%s start_dt=%s',
            self.current_state, self.start_dt
        )
        return start_dt, current_state

    def send_event(self, state, start_dt, end_dt=None):
        if end_dt is None:
            end_dt = datetime.utcnow()
        url = self._base_url + 'buckets/%s/events' % self._bucket_id
        headers = {"Content-type": "application/json", "charset": "utf-8"}
        data = {
            'id': None,
            'timestamp': start_dt.isoformat(),
            'duration': (end_dt - start_dt).total_seconds(),
            'data': {
                'app': state,
                'title': state,
                'state': state
            }
        }
        self._log.debug('POST to %s: %s', url, data)
        r = requests.post(
            url, data=bytes(json.dumps(data), "utf8"), headers=headers
        )
        self._log.debug('Response %s: %s', r.status_code, r.text)
        r.raise_for_status()

    def state_change(self, entity, attribute, old, new, kwargs):
        new = new.lower()
        self._log.debug(
            'state_change callback; entity=%s attribute=%s '
            'old=%s new=%s kwargs=%s; current_state=%s',
            entity, attribute, old, new, kwargs, self.current_state
        )
        if old == new:
            self._log.debug(
                'Ignoring device tracker state unchanged (%s)', old
            )
            return
        if self.current_state == new:
            self._log.debug(
                'Ignoring device tracker state unchanged from cache (%s)',
                self.current_state
            )
            return
        self.send_event(self.current_state, self.start_dt)
        self.start_dt = datetime.utcnow()
        self.current_state = new
