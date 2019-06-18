#!/usr/bin/env python
"""
Diff Normal/Day/Night profiles from an Amcrest camera config.json file.
"""

import json
import sys
from tabulate import tabulate
from copy import deepcopy


def dictdiff(a, b, c, prefix='', ignore_keys=[]):
    # Assumes values are all of the same type if they exist
    result = []
    for k in set(list(a.keys()) + list(b.keys()) + list(c.keys())):
        if k in ignore_keys:
            continue
        if any([isinstance(x.get(k, None), dict) for x in [a, b, c]]):
            result.extend(
                dictdiff(
                    a.get(k, {}),
                    b.get(k, {}),
                    c.get(k, {}),
                    prefix=f'{prefix}.{k}'
                )
            )
            continue
        if (
            a.get(k, None) != b.get(k, None) or
            b.get(k, None) != c.get(k, None) or
            a.get(k, None) != c.get(k, None)
        ):
            result.append(
                [
                    f'{prefix}.{k}',
                    a.get(k, '<unset>'),
                    b.get(k, '<unset>'),
                    c.get(k, '<unset>')
                ]
            )
    return result


def configdiff(fpath):
    with open(fpath, 'r') as fh:
        conf = json.load(fh)
    diffs = []
    night = deepcopy(conf['VideoInOptions'][0]['NightOptions'])
    del conf['VideoInOptions'][0]['NightOptions']
    normal = deepcopy(conf['VideoInOptions'][0]['NormalOptions'])
    del conf['VideoInOptions'][0]['NormalOptions']
    day = conf['VideoInOptions'][0]
    diffs.extend(
        dictdiff(
            day, night, normal, prefix='VideoInOptions[0]',
            ignore_keys=[
                'SunriseHour', 'SunriseMinute', 'SunriseSecond',
                'SunsetHour', 'SunsetMinute', 'SunsetSecond'
            ]
        )
    )
    diffs.extend(
        dictdiff(
            conf['VideoInPreviewOptions'][0]['DayOptions'],
            conf['VideoInPreviewOptions'][0]['NightOptions'],
            conf['VideoInPreviewOptions'][0]['NormalOptions'],
            prefix='VideoInPreviewOptions[0]',
            ignore_keys=[
                'BeginHour', 'BeginMinute', 'BeginSecond',
                'EndHour', 'EndMinute', 'EndSecond'
            ]
        )
    )
    print(tabulate(
        sorted(diffs),
        headers=['Field', 'Day', 'Night', 'Normal']
    ))


if __name__ == "__main__":
    configdiff(sys.argv[1])
