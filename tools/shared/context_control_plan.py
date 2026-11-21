"""Ordered context phases and the minimum setup for a focused phase."""

REPAIRS = ('missing-context', 'corrupt-context', 'corrupt-record')


def driver_chain(kind):
    mixed = ('query-install-legacy', 'query-mixed-old-new') if kind == 'query' else ()
    return (f'{kind}-cold', f'{kind}-warm', *mixed,
            f'{kind}-one-value-change', f'{kind}-changed-warm')


LEFT_PAIRS = tuple((f'left-{kind}', f'lock-after-{kind}')
                   for kind in ('legacy', 'source', 'session'))
PAIRS = (*LEFT_PAIRS, ('empty-directory-failure', 'lock-after-empty-directory'),
         ('cleanup-dual-failure', 'lock-after-cleanup-dual'), ('concurrent-a', 'concurrent-b'))
EXPECTED_COMMANDS = (
    'helper', 'raw-final',
    *(name for kind in ('query', 'session') for name in (
        *driver_chain(kind), *(f'{kind}-{name}' for name in REPAIRS))),
    *(name for pair in LEFT_PAIRS for name in pair), 'empty-stale-success',
    *(name for pair in PAIRS[len(LEFT_PAIRS):] for name in pair),
    'memo-helper', 'memo-query', 'memo-session', 'context-directory-setup',
    'context-directory-reject', 'context-stage-cleanup-failure', 'decoder-differential',
    'window-helper', 'session-window-raw-final',
)
LEGACY_QUERY_COMMANDS = tuple(name for name in EXPECTED_COMMANDS
                              if not (name.startswith('session-') or name in (
                                  'left-session', 'lock-after-session', 'memo-session')))


def commands_for(mode, selected=None):
    """Return actual launch order. Only the chosen ID earns a focused result."""
    available = LEGACY_QUERY_COMMANDS if mode else EXPECTED_COMMANDS
    if selected is None:
        return list(available)
    if selected not in available:
        raise ValueError(f'unknown context control in selected mode: {selected}')
    needed = {selected}
    for kind in ('query', 'session'):
        chain = driver_chain(kind)
        if selected in chain:
            needed.update(chain[:chain.index(selected)])
        if selected in (f'{kind}-{repair}' for repair in REPAIRS):
            needed.update(chain)
    for pair in PAIRS:
        if selected in pair:
            needed.update(pair)
    if selected in LEFT_PAIRS[-1]:
        needed.add('session-cold')
    if selected == 'context-directory-reject':
        needed.add('context-directory-setup')
    if selected == 'decoder-differential':
        needed.add('helper')
    return [name for name in available if name in needed]
