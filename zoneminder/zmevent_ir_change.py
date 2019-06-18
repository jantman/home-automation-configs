import logging
import os
import pickle

logger = logging.getLogger(__name__)

PICKLE_PATH = '/tmp/camera_ir_state.pickle'


def read_state():
    """
    State file is a dict where keys are integer MonitorIds and values are
    boolean, True for B&W/Night Mode or False for Color/Day Mode
    """
    if not os.path.exists(PICKLE_PATH):
        logger.debug('%s does not exist; returning empty data', PICKLE_PATH)
        return {}
    with open(PICKLE_PATH, 'rb') as f:
        data = pickle.load(f)
    logger.debug('Loaded from %s: %s', PICKLE_PATH, data)
    return data


def write_state(s):
    logger.debug('Pickling to %s: %s', PICKLE_PATH, s)
    with open(PICKLE_PATH, 'wb') as f:
        pickle.dump(s, f, pickle.HIGHEST_PROTOCOL)


def handle_ir_change(event, filter_inst):
    state = read_state()
    if filter_inst.suffix == 'Color2BW':
        logger.info(
            'Enter Night mode for Monitor %s (Event %s)',
            event.MonitorId, event.EventId
        )
        state[event.MonitorId] = True
    else:
        logger.info(
            'Enter Day mode for Monitor %s (Event %s)',
            event.MonitorId, event.EventId
        )
        state[event.MonitorId] = False
    write_state(state)
    logger.warning('handle_ir_change wrote new state: %s', state)
