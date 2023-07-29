import sys


def time_to_unix_time(t: int) -> int:
    """
    Return a timestamp in integer seconds since January 1, 1970.
    """
    if sys.platform in ['esp32', 'esp8266']:
        # 946684800.0 is 2000-01-01 00:00:00 UTC which is used as the
        # epoch on ESP systems
        return t + 946684800
    else:
        return t
