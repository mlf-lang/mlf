#!/usr/bin/env python3
"""Build an optional LLVM API splitter and a pinned ordinary-Clang driver."""
import argparse, hashlib, json, os, shlex, shutil, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def identify(path):
    path=Path(path).resolve(strict=True)
    return {'path':str(path),'sha256':sha(path)}

def authenticate(output):
    output=Path(output).resolve(strict=True)
    receipt=json.loads((output/'receipt.json').read_text())
    if receipt.get('format')!=1 or receipt.get('complete') is not True:
        raise ValueError('incomplete parallel driver installation')
    if set(receipt.get('outputs',{}))!={'partition','clang-parallel','driver.json','driver-config.h'}:
        raise ValueError('parallel driver output inventory mismatch')
    for name,item in receipt['outputs'].items():
        if item['path']!=str(output/name) or sha(output/name)!=item['sha256']:
            raise ValueError('parallel driver output changed: '+name)
    for field in ['inputs','llvm_libraries','header_inputs']:
        if not receipt.get(field):raise ValueError('missing parallel driver inputs: '+field)
        for path,digest in receipt[field].items():
            if sha(path)!=digest:raise ValueError('parallel driver input changed: '+path)
    settings=json.loads((output/'driver.json').read_text())
    if settings['helper']!=receipt['outputs']['partition'] or settings['jobs']!=receipt['jobs']:
        raise ValueError('parallel driver configuration mismatch')
    if receipt['inputs'].get(settings['clang']['path'])!=settings['clang']['sha256']:
        raise ValueError('parallel driver Clang identity mismatch')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify',type=Path,help='Authenticate an existing installation; performs no build')
    p.add_argument('--llvm-config')
    p.add_argument('--clang')
    p.add_argument('--output',type=Path)
    p.add_argument('--jobs',type=int,default=4,choices=range(1,65))
    a=p.parse_args()
    if a.verify is not None:
        authenticate(a.verify);print(a.verify / 'receipt.json');return
    if not a.llvm_config or not a.clang or not a.output:p.error('--llvm-config, --clang and --output are required for a build')
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    config=Path(shutil.which(a.llvm_config) or a.llvm_config).resolve(strict=True)
    clang=Path(shutil.which(a.clang) or a.clang).resolve(strict=True)
    cxx=config.parent/'clang++'
    def llvm(*args):return subprocess.check_output([str(config),*args],text=True).strip()
    version=llvm('--version')
    # One installed LLVM distribution supplies parser, ABI headers and libraries.
    flags=shlex.split(llvm('--cxxflags','--ldflags','--system-libs','--libs','core','irreader','bitwriter','transformutils'))
    helper=output/'partition'
    header=output/'driver-config.h'
    header.write_text(''.join('#define '+key+' '+json.dumps(str(value))+'\n' for key,value in [
        ('MLF_CLANG',clang),('MLF_HELPER',helper),('MLF_CONFIG',output/'driver.json')]))
    sources=[HERE/'partition.cpp',HERE/'runner.cpp']
    command=[str(cxx),*map(str,sources),'-o',str(helper),*flags,'-O2','-Werror=return-type']
    launcher_command=[str(clang),'-O2',str(HERE/'launcher.c'),'-I'+str(output),'-o',str(output/'clang-parallel')]
    receipt={'format':1,'complete':False,'llvm_version':version,'jobs':a.jobs,
             'inputs':{str(path):sha(path) for path in [config,cxx.resolve(),clang,*sources,HERE/'launcher.c',HERE/'driver.py',Path(__file__).resolve()]},
             'llvm_libraries':{str(Path(path).resolve()):sha(path) for path in shlex.split(llvm('--libfiles'))},
             'build_command':command,'launcher_command':launcher_command,'header_inputs':{},'dependency_commands':[]}
    def save():(output/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    save()
    for source in [*sources,HERE/'launcher.c']:
        depfile=output/(source.name+'.d')
        dependency_command=([str(clang),str(source),'-I'+str(output)] if source.suffix=='.c' else [str(cxx),str(source),*flags])+['-MM','-MF',str(depfile)]
        subprocess.run(dependency_command,check=True,capture_output=True)
        dependency_text=' '.join(line.removesuffix(chr(92)) for line in depfile.read_text().splitlines())
        dependencies=shlex.split(dependency_text.split(':',1)[1])
        receipt['header_inputs'].update({str(Path(path).resolve()):sha(path) for path in dependencies})
        receipt['dependency_commands'].append(dependency_command)
    save()
    subprocess.run(command,check=True)
    subprocess.run(launcher_command,check=True)
    settings={'format':1,'clang':identify(clang),'helper':identify(helper),'jobs':a.jobs,'timeout_seconds':1800}
    (output/'driver.json').write_text(json.dumps(settings,indent=2,sort_keys=True)+'\n')
    receipt['outputs']={name:identify(output/name) for name in ['partition','clang-parallel','driver.json','driver-config.h']}
    for path,digest in {**receipt['inputs'],**receipt['llvm_libraries'],**receipt['header_inputs']}.items():
        if sha(path)!=digest:raise RuntimeError('build input changed: '+path)
    receipt['complete']=True;save();authenticate(output);print(output/'clang-parallel')
if __name__=='__main__':main()
