"""
AppDaemon app that runs hourly, iterates over all sensor entities that have a
unit_of_measurement of °F, and if any of them are outside a specified range,
create a persistent notification, add a logbook entry, and notify via
NOTIFY_SERVICE, gmail, and Pushover.
"""

import logging
from datetime import time
import appdaemon.plugins.hass.hassapi as hass
from email.message import EmailMessage

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

MIN_THRESHOLD = 60
MAX_THRESHOLD = 80
FREEZER_THRESHOLD = 25

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: List of entity IDs to ignore
IGNORE_IDS = [
    'sensor.porch_temp',
]

#: List of entity IDs that are freezers
FREEZER_IDS = [
    'sensor.chest_freezer_temp',
    'sensor.kitchen_freezer_temp',
]


class TemperatureChecker(hass.Hass, SaneLoggingApp, PushoverNotifier):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing TemperatureChecker...")
        self._hass_secrets = self._get_hass_secrets()
        self.run_hourly(self._check_temperatures, time(0, 0, 0))
        self._log.info('Done initializing TemperatureChecker')
        self.listen_event(self._check_temperatures, event='TEMPERATURE_CHECKER')

    def _check_freezer(self, ename, val):
        if val >= FREEZER_THRESHOLD:
            self._log.info('Found problem: entity=%s state=%s', ename, val)
            return '%s: state of %s is above threshold of %s' % (
                ename, val, FREEZER_THRESHOLD
            )
        return None

    def _check_threshold(self, ename, val):
        self._log.debug('Checking entity=%s state=%s', ename, val)
        return self._check_freezer(ename, val)
        if val < MIN_THRESHOLD or val > MAX_THRESHOLD:
            self._log.info('Found problem: entity=%s state=%s', ename, val)
            return '%s: state of %s is outside threshold of %s to %s' % (
                ename, val, MIN_THRESHOLD, MAX_THRESHOLD
            )
        return None

    def _check_temperatures(self, *args, **kwargs):
        problems = []
        for e in self.get_state('sensor').values():
            if e is None:
                continue
            uom = e.get('attributes', {}).get('unit_of_measurement', '')
            ename = e['entity_id']
            if ename in IGNORE_IDS:
                self._log.debug('Skipping ignored entity: %s', ename)
                continue
            if uom != '°F':
                self._log.debug('Skipping entity: %s', ename)
                continue
            try:
                val = float(e.get('state', 0.0))
            except Exception:
                val = 0.0
            res = self._check_threshold(ename, val)
            if res is not None:
                problems.append(res)
        if len(problems) < 1:
            self._log.info('No problems found.')
            return
        self._log.warning('Problems: %s', problems)
        self.call_service(
            'logbook/log', name='TemperatureChecker Problem',
            message=' | '.join(problems)
        )
        self.call_service(
            NOTIFY_SERVICE, title='TemperatureChecker Found Problems',
            message='\n'.join(problems)
        )
        self.call_service(
            'persistent_notification/create',
            title='TemperatureChecker Problems',
            message='\n'.join(problems)
        )
        self._do_notify_pushover(
            'TemperatureChecker Problems', '; '.join(problems), sound='falling'
        )
