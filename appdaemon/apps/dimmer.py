import appdaemon.plugins.hass.hassapi as hass

from sane_app_logging import SaneLoggingApp


class Dimmer(hass.Hass, SaneLoggingApp):
    """
    Dimmer AppDaemon app.

    Handles dimming/brightening lights based on Zigbee button presses.
    """

    DEVICE_IEEE_to_ENTITY = {
        'b0:ce:18:14:03:69:f5:7b': 'light.br_bulbs',
        'b0:ce:18:14:03:5d:fa:25': 'light.office_bulbs',
        'b0:ce:18:14:03:69:ff:9f': 'light.lr_bulbs',
    }

    def initialize(self):
        self._setup_logging(self.__class__.__name__, False)
        self._log.info("Initializing Dimmer...")
        self._log.debug('listen_event(zha_event)')
        self.listen_event(self._handle_event, event='zha_event')
        self._log.info('Done initializing Dimmer')

    def _handle_event(self, event_name, data, _):
        """
        => Living Room
        
        Dim:
        {'device_ieee': 'b0:ce:18:14:03:69:ff:9f', 'unique_id': 'b0:ce:18:14:03:69:ff:9f:1:0x0008', 'device_id': 'a294b56eca5c03d3b111a0e90ed7cb12', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [1, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:52:33.939790+00:00', 'context': {'id': '01GN5GY1GKXXC94R4JGKFK66HZ', 'parent_id': None, 'user_id': None}}}
        
        Brighten:
        {'device_ieee': 'b0:ce:18:14:03:69:ff:9f', 'unique_id': 'b0:ce:18:14:03:69:ff:9f:1:0x0008', 'device_id': 'a294b56eca5c03d3b111a0e90ed7cb12', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [0, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:52:57.626937+00:00', 'context': {'id': '01GN5GYRMTMB0M080RTKA09TPY', 'parent_id': None, 'user_id': None}}}

        => Office

        Dim:
        {'device_ieee': 'b0:ce:18:14:03:5d:fa:25', 'unique_id': 'b0:ce:18:14:03:5d:fa:25:1:0x0008', 'device_id': '72ae842dc92d358c59556a3d0156f209', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [1, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:55:36.664267+00:00', 'context': {'id': '01GN5H3KYRTWBFB84NT9RBGRG2', 'parent_id': None, 'user_id': None}}}

        Brighten:
        {'device_ieee': 'b0:ce:18:14:03:5d:fa:25', 'unique_id': 'b0:ce:18:14:03:5d:fa:25:1:0x0008', 'device_id': '72ae842dc92d358c59556a3d0156f209', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [0, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:56:01.361150+00:00', 'context': {'id': '01GN5H4C2H5M9YW7SJVG9HJ4VN', 'parent_id': None, 'user_id': None}}}

        => Bedroom

        Dim:
        {'device_ieee': 'b0:ce:18:14:03:69:f5:7b', 'unique_id': 'b0:ce:18:14:03:69:f5:7b:1:0x0008', 'device_id': 'ea7dab636baf4db1fb6fe3ed680c9129', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [1, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:56:44.657134+00:00', 'context': {'id': '01GN5H5PBHG3GT0Z010VP5TB2X', 'parent_id': None, 'user_id': None}}}

        Brighten:
        {'device_ieee': 'b0:ce:18:14:03:69:f5:7b', 'unique_id': 'b0:ce:18:14:03:69:f5:7b:1:0x0008', 'device_id': 'ea7dab636baf4db1fb6fe3ed680c9129', 'endpoint_id': 1, 'cluster_id': 8, 'command': 'step', 'args': [0, 1, 0], 'params': {}, 'metadata': {'origin': 'LOCAL', 'time_fired': '2022-12-25T20:57:05.552525+00:00', 'context': {'id': '01GN5H6ARG6F07SWH2G0VTP0WH', 'parent_id': None, 'user_id': None}}}
        """
        self._log.info('Got %s event data=%s', event_name, data)
        entity_id = self.DEVICE_IEEE_to_ENTITY.get(data['device_ieee'])
        if entity_id is None:
            self._log.error('Unknown device_ieee: %s', data['device_ieee'])
            return
        if data['command'] != 'step':
            self._log.info(
                'Ignoring unknown command %s for device_ieee %s',
                data['command'], data['device_ieee']
            )
            return
        if data['args'] == [1, 1, 0]:
            self.dim(entity_id)
        elif data['args'] == [0, 1, 0]:
            self.brighten(entity_id)
        else:
            self._log.info(
                'Ignoring unknown step args %s for device_ieee %s',
                data['args'], data['device_ieee']
            )

    def dim(self, entity_id):
        self._log.debug('Request to dim %s', entity_id)
        state = self.get_state(entity_id, attribute='all')
        self._log.debug('Entity %s current state: %s', entity_id, state)

    def brighten(self, entity_id):
        self._log.debug('Request to brighten %s', entity_id)
        state = self.get_state(entity_id, attribute='all')
        self._log.debug('Entity %s current state: %s', entity_id, state)
