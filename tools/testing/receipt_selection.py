"""Select stable IDs from a receipt producer's authored cases."""

import json
import os

from receipt_adapter import slug


def identity(prefix, label):
    return prefix + slug(label)


def select(prefix, labels):
    """Return the selected original label, or None for the complete suite."""
    if os.environ.get("MLF_TEST_ID_PREFIX", prefix) != prefix:
        return None
    exact = os.environ.get("MLF_TEST_EXACT")
    if exact is None:
        return None
    matches = [label for label in labels if identity(prefix, label) == exact]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous case: {exact}")
    return matches[0]


def inventory_json(prefix, labels):
    return json.dumps([identity(prefix, label) for label in labels])
