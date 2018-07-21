import logging

logger = logging.getLogger(__name__)


class EventFilter(object):
    """
    Subclasses define filters responsible for determining whether an Event
    should be notified on or not.

    Instantiate class and call :py:meth:`~.run`. After that, check the return
    value of the :py:attr:`~.should_notify` property.
    """

    def __init__(self, event):
        """
        Initialize EventFilter.

        :param event: the event to check
        :type event: ZMEvent
        """
        self._event = event
        self._should_notify = True
        self._reason = []
        self._suffix = None

    def run(self):
        """Test for all filter conditions, update should_notify."""
        raise NotImplementedError()

    @property
    def should_notify(self):
        """
        Whether we should send (True) or suppress (False) a notification for
        this event.

        :returns: whether to send a notification or not
        :rtype: bool
        """
        return self._should_notify

    @property
    def reason(self):
        """
        Return the reason why notification should be suppressed or None.

        :return: reason why notification should be suppressed, or None
        :rtype: ``str`` or ``None``
        """
        if len(self._reason) == 0:
            return None
        elif len(self._reason) == 1:
            return self._reason[0]
        return '; '.join(self._reason)

    @property
    def suffix(self):
        """
        Return a suffix to append to the event name describing the suppression
        reason.

        This should be a SHORT string (a few characters).

        :return: event suffix
        :rtype: str
        """
        return self._suffix

    @property
    def as_dict(self):
        return {
            'filter_name': self.__class__.__name__,
            'should_notify': self.should_notify,

        }


class IRChangeFilter(EventFilter):
    """
    Suppress notification for events where the camera changes from B&W to color
    or vice-versa.
    """

    def run(self):
        """Determine if the camera switched from or to IR during this event."""
        f1 = self._event.FirstFrame
        f2 = self._event.LastFrame
        if f1.is_color and not f2.is_color:
            self._should_notify = False
            self._reason.append('Color to BW switch')
            self._suffix = 'Color2BW'
            return
        if not f1.is_color and f2.is_color:
            self._should_notify = False
            self._reason.append('BW to color switch')
            self._suffix = 'BW2Color'
