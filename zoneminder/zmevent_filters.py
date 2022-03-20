import logging

logger = logging.getLogger(__name__)


class EventFilter(object):
    """
    Subclasses define filters responsible for determining whether an Event
    should be notified on or not.

    Instantiate class and call :py:meth:`~.run`. After that, check the return
    value of the :py:attr:`~.matched` property.
    """

    def __init__(self, event):
        """
        Initialize EventFilter.

        :param event: the event to check
        :type event: ZMEvent
        """
        self._event = event
        self._matched = False
        self._reasons = []
        self._suffix = None

    def run(self):
        """Test for all filter conditions, update should_notify."""
        raise NotImplementedError()

    @property
    def matched(self):
        """
        Whether or not the filter matched this event.

        :returns: whether filter matched or not
        :rtype: bool
        """
        return self._matched

    @property
    def reason(self):
        """
        Return the reason why notification should be suppressed or None.

        :return: reason why notification should be suppressed, or None
        :rtype: ``str`` or ``None``
        """
        if len(self._reasons) == 0:
            return None
        elif len(self._reasons) == 1:
            return self._reasons[0]
        return '; '.join(self._reasons)

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
            'matched': self.matched,
            'reason': self.reason,
            'suffix': self.suffix
        }


class IRChangeFilter(EventFilter):
    """
    Suppress notification for events where the camera changes from B&W to color
    or vice-versa.
    """

    def _image_is_color(self, img):
        bands = img.split()
        histos = [x.histogram() for x in bands]
        if histos[1:] == histos[:-1]:
            return False
        return True

    def run(self):
        """Determine if the camera switched from or to IR during this event."""
        f1 = self._event.AllFrames[self._event.FirstFrameId].image
        f2 = self._event.AllFrames[self._event.LastFrameId].image
        f1_is_color = self._image_is_color(f1)
        f2_is_color = self._image_is_color(f2)
        if f1_is_color and not f2_is_color:
            logger.info(
                'IRChangeFilter matched Color2BW for Event %s: Frame %s is %s '
                'and Frame %s is %s', self._event.EventId,
                self._event.FirstFrameId, f1_is_color, self._event.LastFrameId,
                f2_is_color
            )
            self._matched = True
            self._reasons.append('Color to BW switch')
            self._suffix = 'Color2BW'
        elif not f1_is_color and f2_is_color:
            logger.info(
                'IRChangeFilter matched BW2Color for Event %s: Frame %s is %s '
                'and Frame %s is %s', self._event.EventId,
                self._event.FirstFrameId, f1_is_color, self._event.LastFrameId,
                f2_is_color
            )
            self._matched = True
            self._reasons.append('BW to color switch')
            self._suffix = 'BW2Color'
        else:
            logger.info(
                'IRChangeFilter found no match for Event %s: Frame %s is %s '
                'and Frame %s is %s', self._event.EventId,
                self._event.FirstFrameId, f1_is_color, self._event.LastFrameId,
                f2_is_color
            )


class LowScoreFilter(EventFilter):
    """
    Suppress notification for events with a MaxScore below THRESHOLD
    """

    THRESHOLD = 4

    def run(self):
        if (
            self._event.MaxScore is not None and
            self._event.MaxScore < self.THRESHOLD
        ):
            logger.info(
                'LowScoreFilter matched for Event %s: MaxScore=%s',
                self._event.EventId, self._event.MaxScore
            )
            self._matched = True
            self._reasons.append(
                'LowScore filter MaxScore=%s' % self._event.MaxScore
            )
            self._suffix = 'LowScore'
        else:
            logger.info(
                'LowScoreFilter found no match for Event %s',
                self._event.EventId,
            )
