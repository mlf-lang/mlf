"""Load the independent file-format fixtures without consulting Git history.

Only the fixed reference reader/schema inputs have an integrity pin. Maintained
drivers and current compiler inputs are identified by each run's receipt.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys

DIRECTORY = Path(__file__).with_name('oracles') / 'file-format'


def verify(raw, digest, label):
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('fixed C4 oracle identity: ' + label)
    return raw


def load_oracles(pins, *, directory=DIRECTORY):
    """Validate all fixtures before loading their isolated module namespace."""
    for name, digest in pins.items():
        if Path(name).name != name:
            raise ValueError('fixed C4 oracle filename')
        verify((directory / name).read_bytes(), digest, name)
    modules = []
    names = ('artifact_binary_reference', 'artifact_binary_typed')
    saved = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules.append(module)
    finally:
        # The typed reader imports its verified sibling, never a live reader
        # already present in the caller's namespace.
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return directory, *modules
