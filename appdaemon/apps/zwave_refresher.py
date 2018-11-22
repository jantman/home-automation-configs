"""
AppDaemon app that runs every 5 minutes and refreshes problematic ZWave entities
"""

import logging
import datetime
import appdaemon.plugins.hass.hassapi as hass

from sane_app_logging import SaneLoggingApp

RUN_INTERVAL = 300  # seconds
INTER_ENTITY_DELAY = 15  # seconds

REFRESH_NODES = {
    'zwave.ge_45606_2way_dimmer_switch': 19,
    'zwave.ge_45606_2way_dimmer_switch_2': 20,
    'zwave.2gig_technologies_ct101_thermostat_iris': 5
}

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


class ZwaveRefresher(hass.Hass, SaneLoggingApp):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ZwaveRefresher...")
        self.run_every(
            self._refresh_zwave,
            datetime.datetime.now() + datetime.timedelta(seconds=5),
            RUN_INTERVAL
        )
        self._log.info('Done initializing ZwaveRefresher')
        self.listen_event(self._refresh_zwave, event='ZWAVE_REFRESHER')

    def _refresh_zwave(self, *args, **kwargs):
        self._log.info('Refreshing problematic Z-Wave entities...')
        delay = 0
        for ename, eid in REFRESH_NODES.items():
            delay += INTER_ENTITY_DELAY
            self.run_in(self._refresh_node, delay, node_id=eid, node_name=ename)
        self._log.info('Done. Entities will refresh within %d seconds', delay)

    def _refresh_node(self, kwargs):
        node_name = kwargs['node_name']
        node_id = kwargs['node_id']
        self._log.debug('Refreshing ZWave Node %s (%s)', node_id, node_name)
        self.call_service('zwave/refresh_node', node_id=node_id)
