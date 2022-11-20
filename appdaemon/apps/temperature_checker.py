"""
AppDaemon app that runs hourly, iterates over all sensor entities that have a
unit_of_measurement of °F, and if any of them are outside a specified range,
create a persistent notification, add a logbook entry, and notify via
NOTIFY_SERVICE, gmail, and Pushover.
"""

import logging
from datetime import time, timedelta, datetime, timezone
import appdaemon.plugins.hass.hassapi as hass
from email.message import EmailMessage
from dateutil.parser import parse
from humanize import naturaltime

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

MIN_THRESHOLD = 60
MAX_THRESHOLD = 80
FREEZER_THRESHOLD = 25

STALE_THRESHOLD = timedelta(hours=1)

CHECK_STALE_IDS = [
    'sensor.chest_freezer_temp',
    'sensor.kitchen_freezer_temp',
    #'sensor.porch_temp',
    'sensor.air_quality_temperature_f',
    'sensor.air_quality_class_uptime_sec',
    'sensor.air_quality_particles_03um_ppdl',
    # 'sensor.tv_temp',
]

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: List of entity IDs to ignore
IGNORE_IDS = [
    'sensor.porch_temp',
    'sensor.tv_temp',
    'sensor.humidor_temp',
    'sensor.500291c9b1a3_temp',
    'sensor.f4cfa2d0de01_temp',
    'sensor.officelightswitch_temperature_2',
    'sensor.octoprint_actual_bed_temp',
    'sensor.octoprint_target_bed_temp',
    'sensor.octoprint_actual_tool0_temp',
    'sensor.octoprint_target_tool0_temp',
]

#: List of entity IDs that are freezers
FREEZER_IDS = [
    'sensor.chest_freezer_temp',
    'sensor.kitchen_freezer_temp',
]

#: Name of input boolean to silence this
SILENCE_INPUT = 'input_boolean.silence_temperature_checker'


class TemperatureChecker(hass.Hass, SaneLoggingApp, PushoverNotifier):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing TemperatureChecker...")
        self._hass_secrets = self._get_hass_secrets()
        self.turn_off(SILENCE_INPUT)
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
        if ename in FREEZER_IDS:
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
            if ename in CHECK_STALE_IDS:
                try:
                    updated = datetime.now(timezone.utc) - parse(e['last_updated'])
                except Exception as ex:
                    self._log.error(
                        'Error parsing date for entity %s: %s', e, ex
                    )
                    updated = datetime.now() - datetime(2020, 1, 1, 1, 1, 1)
                if updated > STALE_THRESHOLD:
                    problems.append('%s was lasted updated %s' % (
                        ename, naturaltime(updated)
                    ))
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
        try:
            input_state = self.get_state(SILENCE_INPUT)
        except Exception:
            input_state = 'off'
        if input_state == 'on':
            self._log.warning(
                'Suppressing notification - %s is on', SILENCE_INPUT
            )
            return
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
