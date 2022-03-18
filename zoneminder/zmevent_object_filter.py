import logging

logger = logging.getLogger(__name__)


class IgnoredObject(object):
    """Class to filter out an object from object detection results."""

    def __init__(
        self, name, labels, monitor_num=None, bounding_box=None,
        zone_names=None, min_score=None, callable=None, no_zone=False
    ):
        """
        Initialize an IgnoredObject instance. When object detection is run on
        Frames, each found object is passed through the ``should_ignore()``
        method of each instance of this class. If that method returns True, the
        object information will be drawn in gray on the analyzed image and will
        not be passed on in the list of detected objects.

        Only the ``labels`` parameter is required. Other parameters are additive
        if specified.

        :param name: unique name for this filter
        :type name: str
        :param labels: list of string object detection labels to ignore
        :type labels: list
        :param monitor_num: monitor number this filter is valid for. Leaving
          None means all monitors.
        :type monitor_num: int
        :param bounding_box: 4-tuple of center x, center y, width, height of a
          bounding box. If the center of the detection is within this box, it
          will be matched.
        :type bounding_box: tuple
        :param zone_names: list of zone names to ignore this object in.
          Effectively meaningless when ``bounding_box`` is set.
        :type zone_names: list
        :param min_score: minimum score required; objects that match other
          conditions and have a score below this will be ignored. Specified as
          a float from 0 to 1.
        :type min_score: float
        :param callable: a custom callable to execute; if this returns True,
          ignore the Frame. This will be passed one argument, a reference to
          an instance of this class as well as the label, x, y, zones, and score
        :param no_zone: Ignore this object if it was found outside of all
          defined zones.
        """
        assert isinstance(labels, type([])) or labels is None
        assert name is not None
        self.name = name
        self._labels = labels
        self._monitor_num = monitor_num
        self._bounding_box = bounding_box
        self._zone_names = zone_names
        self._min_score = min_score
        self._callable = callable
        self._no_zone = no_zone

    def should_ignore(self, label, x, y, w, h, zones, score, monitor_id):
        """
        Return True if this object should be ignored based on the parameters of
        this filter, False otherwise.

        :param label: the label of the object
        :type label: str
        :param x: the X coordinate of the center of the object
        :type x: int
        :param y: the Y coordinate of the center of the object
        :type y: int
        :param w: the width of the bounding box around the object
        :type w: int
        :param h: the height of the bounding box around the object
        :type h: int
        :param zones: list of zone names the object bounding box is in
        :type zones: list
        :param score: the score/confidence of the detection, as a decimal
          percentage (0 to 1)
        :type score: float
        :param monitor_id: the Monitor ID
        :type monitor_id: str
        :return: whether or not to ignore the object
        :rtype: bool
        """
        if self._monitor_num != monitor_id:
            return False
        if self._labels is not None and label not in self._labels:
            # labels specified, but no matches with this detection
            return False
        if self._zone_names is not None:
            zone_match = None
            for zn in self._zone_names:
                if zn in zones:
                    zone_match = zn
                    break
            if zone_match is None:
                # zones specified, but none match
                return False
            # else zones specified, and we have a match
        # else zones not specified
        if self._bounding_box is not None:
            bb_x, bb_y, bb_w, bb_h = self._bounding_box
            if not (bb_x - bb_w) < x < (bb_x + bb_w):
                return False
            if not (bb_y - bb_h) < y < (bb_y + bb_h):
                return False
        if self._min_score is not None and score >= self._min_score:
            return False
        # all conditions matched; ignore
        if (
            self._callable is not None and
            not self._callable(self, label, x, y, w, h, zones, score)
        ):
            return False
        if self._no_zone and self._zone_names is None:
            return True
        return True
