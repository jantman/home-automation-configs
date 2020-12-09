"""
AppDaemon app that runs daily at the time specified by RUN_AT_TIME, iterates
all ZHA entities, and checks that their state is "online"
"""

import logging
from datetime import time
import appdaemon.plugins.hass.hassapi as hass

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

#: Time to run every day.
RUN_AT_TIME = time(4, 0, 0)

#: Service to notify. Must take "title" and "message" kwargs.
NOTIFY_SERVICE = 'notify/gmail'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


class ZhaChecker(hass.Hass, SaneLoggingApp, PushoverNotifier):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ZhaChecker...")
        self._hass_secrets = self._get_hass_secrets()
        self.run_daily(self._check_zha, RUN_AT_TIME)
        self._log.info('Done initializing ZhaChecker')
        self.listen_event(self._check_zha, event='ZHA_CHECKER')

    def _check_zha(self, *args, **kwargs):
        problems = []
        for e in self.get_state('zha', attribute='all').values():
            if e is None:
                continue
            state = e.get('state', 'unknown')
            ename = '%s (%s)' % (e['entity_id'], a['friendly_name'])
            if state != 'online':
                self._log.debug(
                    '%s - state=%s', ename, state
                )
                problems.append('%s: state %s' % (ename, state))
        if len(problems) < 1:
            self._log.info('No problems found.')
            return
        self._log.warning('Problems: %s', problems)
        self.call_service(
            'logbook/log', name='ZhaChecker Problem',
            message=' | '.join(problems)
        )
        self.call_service(
            NOTIFY_SERVICE, title='ZhaChecker Found Problems',
            message='\n'.join(problems)
        )
        self.call_service(
            'persistent_notification/create',
            title='ZhaChecker Problems',
            message='\n'.join(problems)
        )
        self._do_notify_pushover(
            'ZhaChecker Problems', '; '.join(problems), sound='falling'
        )
