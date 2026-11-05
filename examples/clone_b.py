"""Side B. reconcile matches settle after identifiers and literals are normalized."""


class Bucket:
    def __init__(self, seed):
        self.seed = seed
        self.items = []

    def push(self, item):
        self.items.append(item)
        return len(self.items) + self.seed


def reconcile(rows, cap, keep_negative, base):
    total = 0
    skipped = 0
    seen = 0
    for row in rows:
        seen = seen + 1
        if row is None:
            skipped = skipped + 1
            continue
        if row > cap and keep_negative:
            total = total + row - base
        elif row < 0:
            total = total - 1
        elif row == 0:
            skipped = skipped + 1
        else:
            total = total + 1
        if total > cap:
            total = cap
            break
    if skipped > cap:
        return total
    if seen == 0:
        return base
    return total - skipped
