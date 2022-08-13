"""
AppDaemon app that runs hourly, checks if my humidor sensors are outside a
specified range, create a persistent notification, add a logbook entry, and
notify via NOTIFY_SERVICE, gmail, and Pushover.
"""

import logging
from datetime import time, timedelta, datetime, timezone
import appdaemon.plugins.hass.hassapi as hass
from email.message import EmailMessage
from dateutil.parser import parse
from humanize import naturaltime

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

STALE_THRESHOLD = timedelta(hours=1)

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: Name of input boolean to silence this
SILENCE_INPUT = 'input_boolean.silence_humidor_checker'


class HumidorChecker(hass.Hass, SaneLoggingApp, PushoverNotifier):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing HumidorChecker...")
        self._hass_secrets = self._get_hass_secrets()
        self.turn_off(SILENCE_INPUT)
        self.run_hourly(self._check_sensors, time(0, 0, 0))
        self._log.info('Done initializing HumidorChecker')
        self.listen_event(self._check_sensors, event='HUMIDOR_CHECKER')

    def _check_state(self, entity_id, min_val, max_val):
        problems = []
        state = self.get_state(entity_id, attribute='all')
        self._log.debug('%s state: %s', entity_id, state)
        if state is None:
            return ["No state for: %s" % entity_id]
        uom = state.get('attributes', {}).get('unit_of_measurement', '')
        try:
            updated = datetime.now(timezone.utc) - parse(state['last_updated'])
        except Exception as ex:
            self._log.error(
                'Error parsing date for entity %s: %s', entity_id, ex
            )
            updated = datetime.now() - datetime(2020, 1, 1, 1, 1, 1)
        if updated > STALE_THRESHOLD:
            problems.append('%s was lasted updated %s' % (
                entity_id, naturaltime(updated)
            ))
        try:
            val = float(state.get('state', 0.0))
        except Exception:
            val = 0.0
        if val <= min_val or val >= max_val:
            problems.append('%s value is %s' % (entity_id, val))
        return problems

    def _check_sensors(self, *args, **kwargs):
        problems = []
        problems.extend(self._check_state('sensor.500291c9b1a3_humidity', 64, 74))
        problems.extend(self._check_state('sensor.500291c9b1a3_temp', 65, 79))
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
            'logbook/log', name='HumidorChecker Problem',
            message=' | '.join(problems)
        )
        self.call_service(
            NOTIFY_SERVICE, title='HumidorChecker Found Problems',
            message='\n'.join(problems)
        )
        self.call_service(
            'persistent_notification/create',
            title='HumidorChecker Problems',
            message='\n'.join(problems)
        )
        self._do_notify_pushover(
            'HumidorChecker Problems', '; '.join(problems), sound='falling'
        )
