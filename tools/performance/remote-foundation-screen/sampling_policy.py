"""Exact source-established atomic temporary filenames; active scans only."""
import re
def transient(relative,step):
    if relative=='outer-supervisor.tmp':return 'outer-receipt'
    if step in ('A','C')and relative=='steps/'+step+'/supervisor.tmp':return 'inner-receipt'
    if relative in ('work/unit.mlfci.new','work/unit.mlfco.new'):return 'crate-atomic'
    prefix='work/query-cache/query-graph-v2/'
    if not relative.startswith(prefix):return None
    tail=relative[len(prefix):]
    if tail=='CURRENT.new':return 'current-atomic'
    if re.fullmatch(r'generations/[0-9a-f]{64}\.mlfqg\.new',tail):return 'generation-atomic'
    if re.fullmatch(r'staging/[0-9a-f]{64}\.mlfqr',tail):return 'staged-result'
    return None
def allowed_missing(relative,step,active):
    return transient(relative,step)if active else None

def sample_lstat(path,root,step,active,lstat=None):
    """Shared production/test lstat boundary; only exact active ENOENT is tolerated."""
    try:return (path.lstat() if lstat is None else lstat()),None
    except FileNotFoundError:
        kind=allowed_missing(path.relative_to(root).as_posix(),step,active)
        if kind is None:raise
        return None,kind

def terminal_quiescent(receipt,helper_exited):
    """No receipt or live helper never establishes terminal cleanup."""
    return (helper_exited is True and isinstance(receipt,dict)
            and receipt.get('phase')=='terminal'
            and receipt.get('cleanup_complete') is True
            and receipt.get('survivors')==[])
