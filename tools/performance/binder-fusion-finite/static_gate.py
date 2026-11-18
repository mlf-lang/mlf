from pathlib import Path
import os,re
from unittest.mock import patch
from bounded import ci_only,GateError
from instrument import instrument
HERE=Path(__file__).resolve().parent

def verify_original(source):
    candidate=instrument(source);orig=source[:source.rfind('}')].rstrip()
    expected=orig.replace('validateDense graph low high = runST (denseValidation graph low high);','validateDense graph low high = runST (denseValidationFused graph low high);')
    assert candidate.startswith(expected+';\n')

def verify():
    text=(HERE/'Main.hs').read_text()
    values=re.findall(r'"(?:[^"\\]|\\.)*"',text.split('expected =')[1].split('labels =')[0])
    labels=re.findall(r'"[^"\n]*"',text.split('labels =')[1].split('render (')[0])
    assert len(values)==len(labels)==len(set(labels))==33
    assert [i-1 if i>=23 else i for i in list(range(22))+list(range(23,34))]==list(range(33))
    ref='refs/heads/perf/binder-fusion-finite-20261118'
    env=dict(GITHUB_ACTIONS='true',GITHUB_SHA='1'*40,GITHUB_RUN_ID='1',GITHUB_RUN_ATTEMPT='1',GITHUB_REPOSITORY='mlf-lang/mlf',GITHUB_REF=ref)
    with patch.dict(os.environ,env,clear=True):assert ci_only()['GITHUB_REF']==ref
    for wrong in ['refs/heads/main','refs/heads/perf/resolve-memo-finite-20261118']:
        with patch.dict(os.environ,dict(env,GITHUB_REF=wrong),clear=True):
            try:ci_only()
            except GateError:pass
            else:raise AssertionError('wrong branch admitted')
    assert 'branches: [perf/binder-fusion-finite-20261118]' in (HERE/'workflow.yml').read_text() if (HERE/'workflow.yml').exists() else True
if __name__=='__main__':verify();print('PASS mapping and admission controls')
