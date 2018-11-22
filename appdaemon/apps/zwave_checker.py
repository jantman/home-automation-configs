"""
AppDaemon app that runs daily at the time specified by RUN_AT_TIME, iterates
all ZWave entities, and checks their battery level and is_failed. If any of
them have is_failed True or a battery level below BATTERY_THRESHOLD, create
a persistent notification, add a logbook entry, and notify via
NOTIFY_SERVICE.
"""

import logging
from datetime import time
import appdaemon.plugins.hass.hassapi as hass
from email.message import EmailMessage

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

#: Threshold below which battery level will trigger an alert.
BATTERY_THRESHOLD = 50

#: Time to run every day.
RUN_AT_TIME = time(4, 0, 0)

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


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
        for e in self.get_state('zwave').values():
            if e is None:
                continue
            a = e.get('attributes', {})
            ename = '%s (%s)' % (e['entity_id'], a['friendly_name'])
            failed = a.get('is_failed', False)
            batt = a.get('battery_level', 100)
            prob = []
            if failed:
                prob.append('Failed')
            if batt <= BATTERY_THRESHOLD:
                prob.append('Battery Level: %d' % batt)
            if len(prob) == 0:
                self._log.debug(
                    '%s - failed=%s battery_level=%s', ename, failed, batt
                )
                continue
            problems.append('%s: %s' % (ename, '; '.join(prob)))
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
        msg = EmailMessage()
        msg.set_content('ZWaveChecker Problems:\n\n%s' % '\n'.join(problems))
        msg['Subject'] = 'ZWaveChecker Problems'
        msg['From'] = self._hass_secrets['gmail_username']
        msg['To'] = self._hass_secrets['gmail_username']
        self._do_notify_email(msg)
