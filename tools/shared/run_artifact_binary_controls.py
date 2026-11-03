#!/usr/bin/env python3
"""One finite, concentrated codec/typed/raw-IO gate after complete integration.
No compiler is invoked. The outer original guard and authenticated fixture build
are mandatory; this is not a new watchdog or a resource-admission mechanism.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

HERE=Path(__file__).resolve().parent

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def regular(path):
    path=path.absolute();info=path.lstat()
    require(path.resolve(strict=True)==path and stat.S_ISREG(info.st_mode),'real regular input required: '+str(path))
    return path

def failure_sink(name):
    # Metadata only: never open a candidate path while deciding whether it is
    # the one explicitly authorized destructive-failure probe.
    require(sys.platform.startswith('linux') and name == '/dev/full',
            'only literal Linux /dev/full is authorized as a failure sink')
    path = Path(name)
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and stat.S_ISCHR(info.st_mode) and
            path.resolve(strict=True) == path, 'failure sink must be canonical non-symlink character device')
    return {'path': name, 'st_dev': info.st_dev, 'st_ino': info.st_ino,
            'st_rdev': info.st_rdev, 'st_mode': info.st_mode}


def load(name):
    path=regular(HERE/(name+'.py'))
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,'module loader')
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    require(Path(module.__file__).resolve()==path,'module identity')
    return module

def tuples(value):return tuple(tuples(x) for x in value) if isinstance(value,list) else value

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',required=True,type=Path)
    parser.add_argument('--shared-ghc-fixture',required=True,type=Path)
    parser.add_argument('--shared-native-fixture',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--partial-write-sink',required=True,
                        help='Only literal Linux /dev/full; no substitute path.')
    parser.add_argument('--build-receipt',required=True,type=Path,
                        help='Parent-authenticated build receipt; this runner records it, outer gate authenticates it.')
    args=parser.parse_args()
    sink_identity=failure_sink(args.partial_write_sink)
    sink=Path(args.partial_write_sink)
    sys.dont_write_bytecode=True
    fixtures={k:regular(v) for k,v in [('ghc',args.fixture),('shared-ghc',args.shared_ghc_fixture),('shared-native',args.shared_native_fixture)]}
    build_receipt=regular(args.build_receipt)
    output=args.output.absolute()
    require(not output.exists() and output.parent.resolve(strict=True)==output.parent,'fresh real output parent')
    for path in [*fixtures.values(),build_receipt,Path(__file__).resolve()]:
        require(not path.is_relative_to(output),'input inside output')
    inputs=[regular(Path(__file__)),build_receipt,*fixtures.values(),
            *[regular(HERE/(name+suffix)) for name,suffix in [
              ('artifact_binary_reference','.py'),('artifact_binary_cases','.py'),('artifact_binary_typed','.py'),('artifact_binary_integration','.py'),
              ('artifact_structure_contract','.json'),('artifact_binary_golden','.json')]]]
    fingerprints={str(p):sha(p) for p in inputs}
    output.mkdir()
    record={'format':1,'complete':False,'state':'running','inputs':fingerprints,'commands':[],
            'partial_write_sink':sink_identity,
            'reference_cases':[],'limits':{'outer_original_guard_required':True,'fixture_seconds_each':180},
            'scope':['strict wire framing/canonical DAG/resource bounds','all frozen typed constructors and ABI codes',
                     'GHC and native actual raw bytes/SHA snapshot/wire roundtrip',
                     'GHC/native typed Graph admission and public binary pair read/write/reread'],
            'limitations':['Not a 32-bit or Windows qualification.','No crash-durability claim.',
                           'Legacy40 and real Session/Query admission controls are separate mandatory aggregate stages.',
                           'Build-receipt authenticity is owned by the original outer gate, not inferred from its filename.']}
    def save():
        staging=output/'receipt.json.new';staging.write_text(json.dumps(record,indent=2)+'\n');staging.replace(output/'receipt.json')
    save()
    def run(name,argv,stdin=None,expected_status=0,expected_stderr=b''):
        row={'name':name,'argv':[str(x) for x in argv],'state':'running'};record['commands'].append(row);save()
        stdout=output/(name+'.stdout');stderr=output/(name+'.stderr')
        with stdout.open('xb') as out,stderr.open('xb') as err:
            process=subprocess.run(row['argv'],input=stdin,stdout=out,stderr=err,check=False,timeout=180,
                                   cwd=output,env=os.environ.copy())
        row.update(exit_code=process.returncode,stdout={'path':str(stdout),'bytes':stdout.stat().st_size,'sha256':sha(stdout)},
                   stderr={'path':str(stderr),'bytes':stderr.stat().st_size,'sha256':sha(stderr)})
        require(process.returncode==expected_status and stderr.read_bytes()==expected_stderr,'fixture status/stderr oracle: '+name)
        row['state']='passed';save();return stdout.read_bytes()
    try:
        ref=load('artifact_binary_reference');cases=load('artifact_binary_cases');typed=load('artifact_binary_typed')
        vectors=json.loads((HERE/'artifact_binary_golden.json').read_text())['vectors']
        corpus=list(cases.corpus())
        for vector in vectors:
            raw=bytes.fromhex(vector['hex']);roots=tuples(vector['roots'])
            require(ref.read_document(raw,vector['schema']).values()==roots,'literal golden interpretation: '+vector['name'])
            require(ref.tree_document(roots,vector['schema'])==raw,'independent writer literal golden: '+vector['name'])
            corpus.append(cases.Case('literal-golden-'+vector['name'],raw,True,vector['schema'],roots=roots))
        names=[case.name for case in corpus];require(len(names)==len(set(names)),'finite unique case names')
        corpus_root=output/'corpus';corpus_root.mkdir();manifest=[]
        for case in corpus:
            accepted=False
            try:
                document=ref.read_document(case.data,case.schema,case.limits);accepted=True
                if case.roots:require(document.values()==case.roots,'fixed positive semantic roots: '+case.name)
            except ref.Invalid:
                pass
            require(accepted==case.accepts,'independent reference contradicts predeclared outcome: '+case.name)
            path=corpus_root/(case.name+'.bin');path.write_bytes(case.data)
            limit_values=[case.limits.bytes,case.limits.symbols,case.limits.symbol_bytes,case.limits.total_symbol_bytes,
                          case.limits.nodes,case.limits.edges,case.limits.depth,case.limits.work]
            manifest.append('\t'.join([case.name,str(path),'accept' if case.accepts else 'reject',str(case.schema),*[str(x) for x in limit_values]]))
            record['reference_cases'].append({'name':case.name,'accepts':case.accepts,'sha256':sha(path),'bytes':len(case.data),
                                               'schema':case.schema,'limits':limit_values})
        manifest_path=output/'corpus.tsv';manifest_path.write_text('\n'.join(manifest)+'\n');save()
        actual=run('wire-corpus',[fixtures['ghc'],'wire-corpus',manifest_path])
        require(actual==''.join('PASS '+name+'\n' for name in names).encode(),'complete ordered wire result inventory')
        constructor_dir=output/'constructors'
        actual=run('constructors',[fixtures['ghc'],'constructors',constructor_dir])
        expected_roots=typed.fixture_roots()
        require(actual==('PASS constructors '+str(len(expected_roots))+'\n').encode(),'complete constructor count')
        expected_files={'constructors.bin':expected_roots,'scalars.bin':cases.SCALAR_ROOTS,'sharing.bin':cases.SHARED_ROOTS}
        for name,expected in expected_files.items():
            raw=(constructor_dir/name).read_bytes();doc=ref.read_document(raw,7)
            require(doc.values()==expected,'independent complete structured meaning: '+name)
            require(raw==ref.tree_document(expected,7),'independent canonical exact bytes: '+name)
            if name=='sharing.bin':
                require(doc.accounting()['shared_node_references']>0,'real structural sharing')
            record.setdefault('artifacts',{})[name]={'sha256':hashlib.sha256(raw).hexdigest(),**doc.accounting()}
        bounds_dir=output/'typed-bounds'
        require(run('typed-bounds',[fixtures['ghc'],'typed-bounds',bounds_dir])==b'PASS typed-wide-deep-shared-raw\n','typed graph bounds marker')
        expected_tables={
            'wide.bin':([str('field-'+str(i)) for i in range(4096)],[(2,i) for i in range(4096)]+[(3,(1,tuple(range(4096))))],[4096],'wide'),
            'deep.bin':([],[(3,(10,()))]+[(3,(11,(0,i-1))) for i in range(1,2049)],[2048],'Kind'),
            'exponential.bin':([],[(3,(10,()))]+[(3,(11,(i-1,i-1))) for i in range(1,19)],[18],'Kind')}
        for name,(symbols,nodes,roots,family) in expected_tables.items():
            raw=(bounds_dir/name).read_bytes();doc=ref.read_document(raw,7)
            require(raw==ref.explicit_document(symbols,nodes,roots),'typed stress independent canonical DAG: '+name)
            typed.validate_type(doc,doc.roots[0],['list','String'] if family=='wide' else family)
            record.setdefault('artifacts',{})[name]={'sha256':hashlib.sha256(raw).hexdigest(),**doc.accounting()}
        require(record['artifacts']['exponential.bin']['root_expanded_work']==524287,'typed shared DAG finite work anchor')
        raw_dir=output/'raw-ghc'
        actual=run('raw-ghc',[fixtures['ghc'],'raw-io',raw_dir])
        require(actual==b'PASS raw-byte-io-and-digest\n','raw GHC terminal marker')
        for line in (raw_dir/'digests.tsv').read_text().splitlines():
            name,digest=line.split('\t');require(re.fullmatch('[0-9a-f]{64}',digest) is not None and sha(raw_dir/name)==digest,'GHC byteArrayDigest matches hashlib')
        require((raw_dir/'allbytes.bin').read_bytes()==bytes(range(256)),'all 256 raw byte values')
        require((raw_dir/'empty.bin').read_bytes()==b'','empty raw file')
        require((raw_dir/'changed.bin').read_bytes()==b'\xff'+bytes(range(1,256)),'mutation exact snapshot')
        require(run('partial-write-ghc',[fixtures['ghc'],'partial-write',sink])==b'PASS raw-write-failure\n','partial-write marker')
        shared_expected=(('int',-(1<<63)),('int',(1<<63)-1),('bits',-(1<<63)),('bits',9221120237041090561),
                         ('text','α😀\0'),('node',31,(('int',-7),('text','hint'))),('node',31,(('int',-7),('text','hint'))))
        shared_results={}
        for backend in ('shared-ghc','shared-native'):
            directory=output/backend;directory.mkdir()
            result=run(backend,[fixtures[backend]],('raw\n'+str(directory)+'\n'+str(sink)+'\n').encode())
            lines=result.decode('utf-8').splitlines()
            digest_names=['empty.bin','allbytes.bin','changed.bin',*['sha-'+str(n)+'.bin' for n in (1,55,56,63,64,65,127,128,129,4095,4096,4097)]]
            require(len(lines)==len(digest_names)+1 and lines[-1]=='PASS shared-raw-binary','shared fixture exact markers')
            for line,expected_name in zip(lines[:-1],digest_names):
                marker,name,digest=line.split(' ');require(marker=='DIGEST' and name==expected_name,'shared complete ordered digest inventory')
                require(re.fullmatch('[0-9a-f]{64}',digest) is not None and sha(directory/name)==digest,'shared digest matches independent hashlib')
            require(not (directory/'nul-created').exists(),'shared NUL path not truncated')
            raw=(directory/'shared-wire.bin').read_bytes();require(raw==ref.tree_document(shared_expected,7),'shared backend independent golden exact')
            require(ref.read_document(raw,7).values()==shared_expected,'shared backend decoded full scalar/name roots')
            require(run(backend+'-typed',[fixtures[backend]],('typed\n'+str(directory)+'\n').encode())==b'PASS shared-typed-graph-and-admission\n','shared typed/admission exact marker')
            graph=ref.read_document((directory/'typed-raw.bin').read_bytes(),7)
            require(len(graph.roots)==2,'native typed root inventory')
            typed.validate_type(graph,graph.roots[0],'Kind');typed.validate_type(graph,graph.roots[1],'RawUnitObject')
            kind,raw=graph.values();require(kind==('node',11,(('node',10,()),('node',10,()))),'independent native Kind')
            header,term=typed.value_node(raw,241,2)
            fields=typed.value_node(header,240,8)
            require(fields[0]==('text','NativeAdmission') and fields[1:7]==(('node',1,()),)*6 and term==('node',77,(('int',41),)),'independent native raw unit fields')
            bad=ref.read_document((directory/'typed-bad.bin').read_bytes(),7)
            require(len(bad.roots)==1,'negative native raw root count');typed.validate_type(bad,bad.roots[0],'RawUnitObject')
            _,badterm=typed.value_node(bad.values()[0],241,2)
            require(badterm==('node',70,(('node',31,(('int',-1),('text','x'))),)),'negative native raw identity preserved')
            context=(directory/'typed-context.bin').read_bytes();typed.inspect_artifact(context,1)
            token=('text','NativeToken');empty=('node',1,())
            declaration=('node',26,(token,empty,('node',1,(('node',25,(token,empty)),))))
            wanted=(('node',244,(('node',1,(declaration,)),)),)
            require(context==ref.tree_document(wanted,1),'independent native schema1 exact bytes')
            shared_results[backend]={path.name:sha(path) for path in directory.iterdir()}
        require(shared_results['shared-ghc']==shared_results['shared-native'],'GHC/native byte-for-byte file parity')
        record['shared_backend_outputs']=shared_results
        integration=load('artifact_binary_integration')
        integration.run_integration(fixtures['ghc'],output,run,record,typed,ref,
                                    {name:fixtures[name] for name in ('shared-ghc','shared-native')})
        record['physical_inventory']=ref.physical_inventory(output)
        require(all(sha(Path(path))==digest for path,digest in fingerprints.items()),'frozen runner/fixture/reference inputs changed')
        require(failure_sink(str(sink))==sink_identity,'authorized failure sink metadata changed')
        record.update(complete=True,state='passed',post_input_integrity=True,post_sink_integrity=True)
    except BaseException as error:
        record.update(complete=False,state='failed',error=type(error).__name__+': '+str(error))
        try:
            sink_same=failure_sink(str(sink))==sink_identity
        except (OSError,ValueError):
            sink_same=False
        record['post_sink_integrity']=sink_same
        record['post_input_integrity']=sink_same and all(Path(path).exists() and sha(Path(path))==digest for path,digest in fingerprints.items())
    finally:save()
    print(json.dumps({'complete':record['complete'],'commands':len(record['commands']),'reference_cases':len(record['reference_cases'])},sort_keys=True))
    if not record['complete']:raise SystemExit(1)

if __name__=='__main__':main()
