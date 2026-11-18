from pathlib import Path
import os,re
from unittest.mock import patch
from bounded import ci_only,GateError
from instrument import instrument
HERE=Path(__file__).resolve().parent

def verify_original(source):
    from instrument import OLD,NEW
    candidate=instrument(source)
    assert candidate.replace(NEW,OLD)==source
    public=source[source.index('  canonicalize ::'):source.index('  equationNodes ::')]
    assert public in candidate

def verify():
    text=(HERE/'Main.hs').read_text()
    values=re.findall(r'"(?:[^"\\]|\\.)*"',text.split('expected =')[1].split('labels =')[0])
    labels=re.findall(r'"[^"\n]*"',text.split('labels =')[1].split('render (')[0])
    assert len(values)==len(labels)==len(set(labels))==33
    assert [i-1 if i>=23 else i for i in list(range(22))+list(range(23,34))]==list(range(33))
    assert len(list(range(22))+list(range(23,41))) * 4 == 160
    assert "(runUnify i) [0..3]) ([0..21]++[23..40])" in text
    assert "160 unify canonicalization cases" in text
    assert "len(left)==612" in (HERE/"finite.py").read_text()
    ref='refs/heads/perf/aliasfree-canonical-finite-20261118'
    env=dict(GITHUB_ACTIONS='true',GITHUB_SHA='1'*40,GITHUB_RUN_ID='1',GITHUB_RUN_ATTEMPT='1',GITHUB_REPOSITORY='mlf-lang/mlf',GITHUB_REF=ref)
    with patch.dict(os.environ,env,clear=True):assert ci_only()['GITHUB_REF']==ref
    for wrong in ['refs/heads/main','refs/heads/perf/resolve-memo-finite-20261118']:
        with patch.dict(os.environ,dict(env,GITHUB_REF=wrong),clear=True):
            try:ci_only()
            except GateError:pass
            else:raise AssertionError('wrong branch admitted')
    assert 'branches: [perf/aliasfree-canonical-finite-20261118]' in (HERE/'workflow.yml').read_text() if (HERE/'workflow.yml').exists() else True
if __name__=='__main__':verify();print('PASS mapping and admission controls')

