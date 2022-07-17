"""
AppDaemon app that runs daily at the time specified by RUN_AT_TIME, iterates
all ZWave entities, and checks their battery level and is_failed. If any of
them have is_failed True or a battery level below BATTERY_THRESHOLD, create
a persistent notification, add a logbook entry, and notify via
NOTIFY_SERVICE.
"""

from datetime import time
import appdaemon.plugins.hass.hassapi as hass
from dateutil.parser import parse
from datetime import timedelta, datetime
from humanize import naturaltime
import re

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

#: Threshold below which battery level will trigger an alert.
BATTERY_THRESHOLD = 60

#: Time to run every day.
RUN_AT_TIME = time(4, 0, 0)

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: Entities to ignore
IGNORE_ENTITIES = []

#: states that are OK
OK_STATES = ['alive', 'asleep', 'awake']

#: Entity ID regex
ID_RE = re.compile(r'^sensor\.node_\d+_node_status$')


class ZwaveChecker(hass.Hass, SaneLoggingApp, PushoverNotifier):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ZWaveChecker...")
        self._hass_secrets = self._get_hass_secrets()
        self.run_daily(self._check_zwave, RUN_AT_TIME)
        self._log.info('Done initializing ZWaveChecker')
        self.listen_event(self._check_zwave, event='ZWAVE_CHECKER')

    def _check_zwave(self, *args, **kwargs):
        problems = []
        for e in self.get_state('binary_sensor').values():
            if e.get('attributes', {}).get('device_class') != 'battery':
                continue
            if e['entity_id'] in IGNORE_ENTITIES:
                self._log.debug('Ignore entity %s', e['entity_id'])
                continue
            a = e.get('attributes', {})
            ename = f"{e['entity_id']} ({a['friendly_name']})"
            if e.get('state') == 'on':
                problems.append(f'{ename} is triggered (on)')
        for e in self.get_state('sensor').values():
            if e.get('attributes', {}).get('device_class') != 'battery':
                continue
            if e.get('attributes', {}).get('state_class') != 'measurement':
                continue
            if e['entity_id'] in IGNORE_ENTITIES:
                self._log.debug('Ignore entity %s', e['entity_id'])
                continue
            a = e.get('attributes', {})
            ename = f"{e['entity_id']} ({a['friendly_name']})"
            state = e.get('state', 0)
            try:
                state = float(state)
            except ValueError:
                self._log.error(f'{ename}: state {state} ({type(state)}) not a float')
                continue
            if state <= BATTERY_THRESHOLD:
                problems.append(f'{ename} is {e["state"]}')
        for e in self.get_state('sensor').values():
            if not ID_RE.match(e['entity_id']):
                continue
            a = e.get('attributes', {})
            ename = f"{e['entity_id']} ({a['friendly_name']})"
            if e.get('state') not in OK_STATES:
                problems.append(f'{ename} is in state {e["state"]}')
        if len(problems) < 1:
            self._log.info('No problems found.')
            return
        self._log.warning('Problems: %s', problems)
        self.call_service(
            'logbook/log', name='ZwaveChecker Problem',
            message=' | '.join(problems)
        )
        self.call_service(
            NOTIFY_SERVICE, title='ZwaveChecker Found Problems',
            message='\n'.join(problems)
        )
        self.call_service(
            'persistent_notification/create',
            title='ZwaveChecker Problems',
            message='\n'.join(problems)
        )
        self._do_notify_pushover(
            'ZWaveChecker Problems', '; '.join(problems), sound='falling'
        )
