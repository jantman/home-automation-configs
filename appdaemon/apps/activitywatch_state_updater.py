"""
ActivityWatch state updater

Maintain a bucket in ActivityWatch <https://activitywatch.net/> and update it
when state changes.
"""

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, time
import os
import requests
import json
import socket

from sane_app_logging import SaneLoggingApp

#: Entity IDs to update state for, and their AW buckets
ENTITY_IDS_TO_BUCKETS = {
    'device_tracker.02157df2c2d6e627': 'aw-watcher-hass-device',
    'sensor.desk_standing': 'aw-watcher-hass-desk-standing'
}

#: The host that ActivityWatch is running on
AW_HOST = '192.168.0.24'

#: The port that ActivityWatch is running on
AW_PORT = 5600

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = True


class ActivityWatchStateUpdater(hass.Hass, SaneLoggingApp):
    """
    ActivityWatch state updater
    """

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ActivityWatchDeviceTracker...")
        self._base_url = 'http://%s:%d/api/0/' % (AW_HOST, AW_PORT)
        self.current_states = {}
        for entity_id, bucket_id in ENTITY_IDS_TO_BUCKETS.items():
            self._create_bucket(bucket_id)
            self.current_states[entity_id] = self.get_state(entity_id)
            self.listen_state(self.state_change, entity_id)
            self.send_heartbeat(bucket_id, self.current_states[entity_id])
        self._timer = self.run_minutely(
            self._timer_callback, time(0, 0, 12)
        )
        self._log.info('Done initializing ActivityWatchDeviceTracker.')

    def _create_bucket(self, bucket_id):
        url = self._base_url + 'buckets/%s' % bucket_id
        headers = {"Content-type": "application/json", "charset": "utf-8"}
        data = {
            'client': 'aw-watcher-hass',
            'hostname': socket.gethostname(),
            'type': 'currentwindow'
        }
        self._log.debug('POST to %s: %s', url, data)
        r = requests.post(
            url, data=bytes(json.dumps(data), "utf8"), headers=headers
        )
        self._log.debug('Response %s: %s', r.status_code, r.text)
        r.raise_for_status()

    def _timer_callback(self, _):
        for entity_id, bucket_id in ENTITY_IDS_TO_BUCKETS.items():
            self.current_states[entity_id] = self.get_state(entity_id)
            self.send_heartbeat(bucket_id, self.current_states[entity_id])

    def send_heartbeat(self, bucket_id, state):
        url = self._base_url + 'buckets/%s/heartbeat?pulsetime=70' % bucket_id
        headers = {"Content-type": "application/json", "charset": "utf-8"}
        data = {
            'id': None,
            'timestamp': datetime.utcnow().isoformat(),
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
            entity, attribute, old, new, kwargs, self.current_states[entity]
        )
        if entity not in ENTITY_IDS_TO_BUCKETS:
            self._log.error(
                'ERROR: State update for unknown entity: %s', entity
            )
        if old == new:
            self._log.debug(
                'Ignoring device tracker state unchanged (%s)', old
            )
            return
        if self.current_states[entity] == new:
            self._log.debug(
                'Ignoring device tracker state unchanged from cache (%s)',
                self.current_states[entity]
            )
            return
        self.send_heartbeat(ENTITY_IDS_TO_BUCKETS[entity], new)
        self.current_states[entity] = new
