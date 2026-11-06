#!/usr/bin/env python3
"""Static inventory/syntax check only: no compiler, producer, or subprocess calls."""
import ast
import hashlib
from pathlib import Path
import support


def main():
    here = Path(__file__).resolve().parent
    data = support.check_inventory()
    for path in here.glob('*.py'):
        compile(path.read_bytes(), str(path), 'exec')
    if data['transport_execution_count'] != 40 or data['descendant_execution_count'] != 4:
        raise ValueError('finite expected counts changed')
    if data['candidate']['changed_paths'] != ['host/ghc/cbits/host.c', 'runtime/mlf_system.h']:
        raise ValueError('implementation change scope changed')
    real = ast.parse((here / 'real_controls.py').read_text())
    names = next(ast.literal_eval(node.value) for node in ast.walk(real)
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'names' for t in node.targets))
    if names != data['transport_cases']:
        raise ValueError('transport inventory differs from unchanged case list')
    # Guard the original independent expectation blocks, not candidate output.
    for name, specification in data['expectation_blocks'].items():
        text = (here / name).read_text()
        block = text.split(specification['start'], 1)[1].split(specification['stop'], 1)[0]
        if hashlib.sha256(block.encode()).hexdigest() != specification['sha256']:
            raise ValueError('independent expectation block changed: ' + name)
    for path in here.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            text = path.read_text()
            if ('/' + 'workspace' + '/') in text or ('/' + 'home' + '/' + 'agent' + '/') in text:
                raise ValueError('private absolute path in public package: ' + str(path))
    print('PASS static inventory and Python syntax; no runtime controls executed')


if __name__ == '__main__':
    main()
