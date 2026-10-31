#!/usr/bin/env python3
"""Fresh LLVM partitioning followed by complete ordinary Clang -O2 per part.

Other invocations pass through unchanged. No IR, object or user-program cache.
The installation receipt must be authenticated before selecting this driver.
"""
import concurrent.futures, hashlib, json, os, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path


def selection(args):
    # A narrow driver contract avoids guessing at arbitrary Clang language,
    # linker, plugin, response-file or multi-source semantics.
    allowed={'-O2','-c','-Wno-override-module'}
    sources=[];output=None;i=0
    while i<len(args):
        value=args[i]
        if value=='-o' and i+1<len(args):
            if output is not None:return None
            output=Path(args[i+1]);i+=2;continue
        if value in allowed:i+=1;continue
        if not value.startswith('-') and value.endswith('.ll'):
            sources.append((i,Path(value)));i+=1;continue
        return None
    if '-c' not in args or '-O2' not in args or len(sources)!=1 or output is None:return None
    return sources[0],output


def main():
    settings=json.loads(Path(__file__).resolve().with_name('driver.json').read_text())
    clang=settings['clang']['path'];args=sys.argv[1:];chosen=selection(args)
    if chosen is None:
        os.execv(clang,[clang,*args])
    (source_index,source),output=chosen
    output=output.resolve();source=source.resolve(strict=True)
    if source==output:os.execv(clang,[clang,*args])
    start=time.monotonic();deadline=start+settings['timeout_seconds'];processes=set();lock=threading.Lock();records=[];cancelled=[False]
    def stop():
        cancelled[0]=True
        with lock:children=list(processes)
        for child in children:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        for child in children:child.wait()
    def interrupted(signum,frame):
        cancelled[0]=True
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    def run(command,label):
        began=time.monotonic()
        with lock:
            if cancelled[0]:raise RuntimeError('compilation cancelled')
            child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            processes.add(child)
        try:
            while True:
                if cancelled[0]:raise RuntimeError('compilation cancelled')
                if child.poll() is not None:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('parallel compilation deadline exceeded')
                try:
                    stdout,stderr=child.communicate(timeout=min(.1,remaining));break
                except subprocess.TimeoutExpired:
                    continue
            row={'label':label,'argv':command,'exit_code':child.returncode,'seconds':time.monotonic()-began,
                 'stdout':stdout.decode(errors='replace'),'stderr':stderr.decode(errors='replace')}
            with lock:records.append(row)
            if child.returncode:raise RuntimeError(label+' failed: '+row['stderr'])
            return row
        except BaseException:
            stop();raise
        finally:
            with lock:processes.discard(child)
    receipt={'format':1,'complete':False,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'jobs':settings['jobs'],'installed_tools':settings,'commands':records}
    try:
        with tempfile.TemporaryDirectory(prefix='.mlf-parallel-',dir=output.parent) as temporary:
            work=Path(temporary);prefix=work/'part-'
            run([settings['helper']['path'],str(source),str(prefix),str(settings['jobs'])],'partition')
            def compile_part(index):
                part=Path(str(prefix)+str(index)+'.bc');obj=work/(str(index)+'.o')
                if not part.is_file():raise RuntimeError('missing generated partition')
                command=[clang,'-O2','-Wno-override-module','-c',str(part),'-o',str(obj)]
                run(command,'compile-'+str(index));return obj
            with concurrent.futures.ThreadPoolExecutor(max_workers=settings['jobs']) as pool:
                objects=list(pool.map(compile_part,range(settings['jobs'])))
            combined=work/'combined.o'
            run([clang,'-nostdlib','-r',*map(str,objects),'-o',str(combined)],'combine')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=receipt['source_sha256']:
                raise RuntimeError('source changed during compilation')
            if cancelled[0]:raise RuntimeError('compilation cancelled')
            receipt['output_sha256']=hashlib.sha256(combined.read_bytes()).hexdigest()
            os.replace(combined,output)
            receipt['complete']=True
    except BaseException as error:
        receipt['error']=str(error);stop();raise
    finally:
        receipt['seconds']=time.monotonic()-start
        output.with_suffix(output.suffix+'.parallel.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
