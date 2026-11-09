#!/usr/bin/env python3
"""Twenty original transport cases, unchanged, against original and candidate C."""
import json,os,subprocess,sys
from pathlib import Path
import support as common
args=common.arguments();common.check_pair(args)
S=common.HERE/'fixtures';sha=common.sha;build=args.output/'build';out=args.output/'transport'
br=json.loads((build/'receipt.json').read_text());assert br['complete'];common.check_pins(br['inputs']);common.check_pins(br['outputs']);common.authenticate(Path(br['base_producer']))
assert sha(build/'host-base.o')==sha(Path(br['base_producer'])/'host.o'),'control C object differs from qualified producer'
assert not out.exists();out.mkdir();names=['true','exit7','exit124','signal-term','exec-missing','bad-cwd','missing-stdin','timeout','unterminated-spec','missing-fields','zero-timeout','large-timeout','bad-timeout','NUL-cwd','mkdir','mv','shared-redirection','write-bytes','write-bad-parent','write-NUL-path']
assert names==common.inventory()['transport_cases']
r={'complete':False,'performance_measured':False,'cases':names,'inputs':{**common.input_pins(),str(__file__):sha(__file__),str(build/'receipt.json'):sha(build/'receipt.json')},'runs':[]}
def save():(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
def spec(executable,args=(),timeout='3',stdin='',stdout='',stderr=''):
 return ('\0'.join([timeout,stdin,stdout,stderr,executable,*args])+'\0').encode()
def expected(status,number=0,message=''):
 b=message.encode();return f'{status} {number} {len(b)} {b.hex()}\n'.encode()
save()
try:
 for name in names:
  for side in ['base','candidate']:
   d=out/(name+'-'+side);d.mkdir();op=7;a=b'';b=spec('/bin/true');code=0;error='';finished=True;timedout=0;kind='other';verify_files={}
   if name=='exit7':b=spec('/bin/sh',['-c','exit 7']);code=7
   elif name=='exit124':b=spec('/bin/sh',['-c','exit 124']);code=124
   elif name=='signal-term':b=spec('/bin/sh',['-c','kill -TERM $$']);code=143
   elif name=='exec-missing':b=spec(str(d/'no-such-command'));code=127
   elif name=='bad-cwd':a=str(d/'no-dir').encode();code=126
   elif name=='missing-stdin':b=spec('/bin/true',stdin=str(d/'missing-input'));code=126
   elif name=='timeout':b=spec('/bin/sleep',['2'],timeout='1');code=124;timedout=1
   elif name=='unterminated-spec':b=b'3\0\0\0\0/bin/true';error='IO error: invalid process specification';finished=False
   elif name=='missing-fields':b=b'3\0\0';error='IO error: invalid process specification';finished=False
   elif name in ['zero-timeout','large-timeout','bad-timeout']:
    b=spec('/bin/true',timeout={'zero-timeout':'0','large-timeout':'2147483648','bad-timeout':'x'}[name]);error='IO error: invalid process specification';finished=False
   elif name=='NUL-cwd':a=b'a\0b';error='file path contains NUL';finished=False
   elif name=='mkdir':b=spec('/bin/mkdir',['-p',str(d/'nested dir/Unicode-λ')]);kind='mkdir'
   elif name=='mv':
    source=d/'move λ.new';target=d/'move λ';source.write_bytes(b'new\x00bytes');target.write_bytes(b'old');b=spec('/bin/mv',['-f',str(source),str(target)]);kind='mv';verify_files[str(target)]=b'new\x00bytes'
   elif name=='shared-redirection':
    target=d/'shared λ.out';b=spec('/bin/sh',['-c','printf OUT; printf ERR >&2'],stdout=str(target),stderr=str(target));verify_files[str(target)]=b'OUTERR'
   elif name.startswith('write-'):
    op=14;a=str(d/'written λ').encode();b='a\x00λ𐀀\n'.encode()
    if name=='write-bad-parent':a=str(d/'no-parent/file').encode();error='IO error: file write failed';finished=False
    elif name=='write-NUL-path':a=b'invalid\0name';error='file path contains NUL';finished=False
    else:verify_files[a.decode()]=b
   (d/'a.bin').write_bytes(a);(d/'b.bin').write_bytes(b);env=common.env()
   argv=[str(build/('probe-'+side)),str(op),str(d/'a.bin'),str(d/'b.bin')]
   with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:p=subprocess.run(argv,env=env,cwd=d,stdout=so,stderr=se,timeout=10)
   wanted=expected(1,0,error) if error else expected(0,code);assert p.returncode==0 and (d/'stdout').read_bytes()==wanted,(name,side,(d/'stdout').read_bytes(),wanted)
   for path,body in verify_files.items():assert Path(path).read_bytes()==body
   if name=='mkdir':assert (d/'nested dir/Unicode-λ').is_dir()
   if name=='mv':assert not (d/'move λ.new').exists()
   row={'case':name,'side':side,'exit_code':p.returncode,'expected_stdout_hex':wanted.hex(),'stdout_sha256':sha(d/'stdout'),'stderr_sha256':sha(d/'stderr'),'argv':argv}
   r['runs'].append(row);save()
 common.check_pair(args);common.check_pins(br['inputs']);common.check_pins(br['outputs']);common.authenticate(Path(br['base_producer']));r.update(complete=True,case_count=20,execution_count=40,original_error_status_IO_observables_preserved=True,both_real_timeout_and_exit124_cases_passed=True)
except BaseException as e:r['error']=repr(e);raise
finally:save()
print('PASS 20 independent transport cases x original/candidate = 40; no speed claim')
