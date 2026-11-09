#!/usr/bin/env python3
"""Cheap shell-orchestration controls; these do not qualify any compiler."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CASES = ['pass', 'dirty-source', 'unauthenticated', 'build-failure', 'bad-build-report',
         'harness-failure', 'missing-marker', 'native-failure',
         'mutated-source', 'mutated-tool', 'post-auth-failure']

def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)

for case in CASES:
    with tempfile.TemporaryDirectory(prefix='tuple-list-gate-') as temp:
        root = Path(temp)
        (root / 'tools/release').mkdir(parents=True)
        shutil.copy(ROOT / 'tools/release/qualify-tuple-list.sh', root / 'tools/release/')
        (root / 'source').write_text('original\n')
        (root / 'mlf.lock').write_text('{}')
        (root / '.mlf-build/shared-candidate').mkdir(parents=True)
        (root / '.mlf-build/shared-candidate/manifest.json').write_text('{}')
        executable(root / 'mock-bin/git', '#!/bin/sh\nif [ "$1" = ls-files ]; then printf "source\\0"; elif [ "$1" = diff ]; then [ "$CASE" != dirty-source ]; else printf "test-source\\n"; fi\n')
        for tool in ['emlf', 'mlfpkg', 'mlf-build-runner', 'compiler-tests']:
            executable(root / '.mlf-build/bin' / tool, '#!/bin/sh\nexit 0\n')
        executable(root / 'tools/release/shared-candidate.sh', '''#!/bin/sh
n=0; test ! -f auth-count || n=$(cat auth-count)
n=$((n + 1)); echo "$n" > auth-count
[ "$CASE" != unauthenticated ] || exit 1
[ "$CASE" != post-auth-failure ] || [ "$n" = 1 ]
''')
        (root / 'tools/release/native-environment.sh').write_text(':\n')
        (root / 'tools/release/qualification-jobs.sh').write_text('export MLF_TEST_BUILD_JOBS=1\n')
        executable(root / 'mlfpkg', '''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys
if os.environ['CASE']=='build-failure': sys.exit(1)
out=pathlib.Path(sys.argv[sys.argv.index('--build-dir')+1]);(out/'bin').mkdir(parents=True)
b=out/'bin/tuple-list';b.write_text('#!/bin/sh\\n[ "$CASE" != harness-failure ] || exit 1\\n[ "$CASE" = missing-marker ] || echo "Tuple/list focused checks passed."\\nexit 0\\n');b.chmod(0o755)
def tool(key):
 p=os.environ[key];return {'path':p,'sha256':hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()}
r={'format':1,'complete':True,'implementation':'MLF','toolchain':{'compiler':tool('MLF_COMPILER'),'manager':tool('MLF_PACKAGE_MANAGER')},'scheduler':[{'helper':tool('MLF_BUILD_RUNNER'),'invocation_id':'fresh'}],'scheduler_results':[{'complete':True,'exit_code':0,'invocation_id':'fresh'}],'pending-publications':[{'name':'tuple-list','files':{'program':hashlib.sha256(b.read_bytes()).hexdigest()}}]}
if os.environ['CASE']=='bad-build-report': r['toolchain']['compiler']['sha256']='0'*64
(out/'build-report.json').write_text(json.dumps(r))
''')
        executable(root / 'tools/release/test-tuple-list.sh', '''#!/bin/sh
[ "$CASE" != native-failure ] || exit 1
mkdir -p "$2"; echo pass > "$2/native.stdout"
[ "$CASE" != mutated-source ] || echo changed >> source
[ "$CASE" != mutated-tool ] || echo changed >> .mlf-build/bin/emlf
exit 0
''')
        # Match the real tracked script mode: the gate must invoke bash.
        (root / 'tools/release/test-tuple-list.sh').chmod(0o644)
        evidence = root / '.mlf-build/tuple-list-qualification'
        evidence.mkdir()
        (evidence / 'verification.json').write_text('{"complete":true}')
        env = dict(os.environ, CASE=case, MLF_CI_SHARED_CANDIDATE='1',
                   PATH=str(root / 'mock-bin') + os.pathsep + os.environ['PATH'])
        run = subprocess.run(['bash', 'tools/release/qualify-tuple-list.sh'], cwd=root,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        receipt = json.loads((evidence / 'verification.json').read_text())
        if case == 'pass':
            assert run.returncode == 0 and receipt['complete'], run.stdout
            manifest = evidence / receipt['run'] / 'artifacts.sha256'
            assert manifest.exists()
            subprocess.run(['sha256sum', '-c', 'artifacts.sha256'], cwd=manifest.parent,
                           check=True, stdout=subprocess.DEVNULL)
        else:
            assert run.returncode != 0 and receipt == {'complete': False}, (case, run.stdout, receipt)
        print('PASS orchestration control:', case)
