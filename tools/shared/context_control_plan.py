"""Ordered per-group cache observations and dependencies for focused execution."""

REPAIRS = ('missing-context', 'corrupt-context', 'corrupt-record')
QUERY_CHAIN = ('query-cold', 'query-warm', 'query-install-legacy', 'query-mixed-old-new',
               'query-rebuilt-warm', 'query-one-value-change', 'query-changed-warm')
LEFT_PAIRS = tuple((f'left-{kind}', f'lock-after-{kind}') for kind in ('legacy', 'source'))
PAIRS = (*LEFT_PAIRS, ('empty-directory-failure', 'lock-after-empty-directory'),
         ('cleanup-dual-failure', 'lock-after-cleanup-dual'), ('concurrent-a', 'concurrent-b'))
EXPECTED_COMMANDS = (
    'helper', 'raw-final', *QUERY_CHAIN, *(f'query-{repair}' for repair in REPAIRS),
    *(name for pair in LEFT_PAIRS for name in pair), 'empty-stale-success',
    *(name for pair in PAIRS[len(LEFT_PAIRS):] for name in pair),
    'memo-helper', 'memo-query', 'context-directory-setup', 'context-directory-reject',
    'context-stage-cleanup-failure', 'window-helper',
)


def commands_for(selected=None):
    """Return actual launch order. Only the chosen ID earns a focused result."""
    if selected is None:
        return list(EXPECTED_COMMANDS)
    if selected not in EXPECTED_COMMANDS:
        raise ValueError(f'unknown context control: {selected}')
    needed = {selected}
    if selected in QUERY_CHAIN:
        needed.update(QUERY_CHAIN[:QUERY_CHAIN.index(selected)])
    if selected in (f'query-{repair}' for repair in REPAIRS):
        needed.update(QUERY_CHAIN)
    for pair in PAIRS:
        if selected in pair:
            needed.update(pair)
    if selected == 'context-directory-reject':
        needed.add('context-directory-setup')
    return [name for name in EXPECTED_COMMANDS if name in needed]
