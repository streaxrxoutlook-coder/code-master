"""Side A of the type-2 pair. Names differ from clone_b.py; structure does not."""

import math

LIMIT = 5


def settle(entries, ceiling, allow_negative, floor_value):
    total = 0
    skipped = 0
    seen = 0
    for entry in entries:
        seen = seen + 1
        if entry is None:
            skipped = skipped + 1
            continue
        if entry > ceiling and allow_negative:
            total = total + entry - floor_value
        elif entry < 0:
            total = total - 1
        elif entry == 0:
            skipped = skipped + 1
        else:
            total = total + 1
        if total > ceiling:
            total = ceiling
            break
    if skipped > ceiling:
        return total
    if seen == 0:
        return floor_value
    return total - skipped


def only_a(marker, table):
    label = "alpha"
    width = int(math.log2(LIMIT)) if LIMIT > 1 else 0
    for row in table:
        if row is None:
            continue
        label = label + "/" + row
    return label + ":" + marker + ":" + str(width)
