import sys
import os
import socket
from platform import node
import logging

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from zmevent_config import STATSD_HOST, STATSD_PORT

logger = logging.getLogger(__name__)
NODE_NAME = node()


def statsd_increment_counter(name, increment=1):
    _statsd_send(
        'zmevent.%s.%s:%d|c' % (NODE_NAME, name, increment)
    )


def statsd_set_gauge(name, value):
    _statsd_send(
        'zmevent.%s.%s:%s|g' % (NODE_NAME, name, value)
    )


def statsd_send_time(name, value):
    # value should be seconds, as in time.time() - time.time()
    _statsd_send(
        'zmevent.%s.%s:%d|ms' % (NODE_NAME, name, int(value * 1000))
    )


def _statsd_send(send_str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((STATSD_HOST, STATSD_PORT))
    logger.debug('Sending data: "%s"', send_str)
    sock.sendall(send_str.encode('utf-8'))
    logger.debug('Data sent to statsd')
    sock.close()
