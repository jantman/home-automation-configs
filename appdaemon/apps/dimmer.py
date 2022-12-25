from sane_app_logging import SaneLoggingApp


class Dimmer(hass.Hass, SaneLoggingApp):
    """
    Dimmer AppDaemon app.

    Handles dimming/brightening lights based on Zigbee button presses.
    """

    def initialize(self):
        self._setup_logging(self.__class__.__name__, False)
        self._log.info("Initializing Dimmer...")
        self._log.debug('listen_event(zha_event)')
        self.listen_event(self._handle_event, event='zha_event')
        self._log.info('Done initializing Dimmer')

    def _handle_event(self, event_name, data, _):
        self._log.info('Got %s event data=%s', event_name, data)
