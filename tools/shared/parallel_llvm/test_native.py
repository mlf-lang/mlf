#!/usr/bin/env python3
"""Exercise a built splitter through real Clang, including rejection controls."""
import argparse,json,subprocess,tempfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--install',type=Path,required=True);a=p.parse_args()
    install=a.install.resolve();config=json.loads((install/'driver.json').read_text());clang=config['clang']['path']
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory);source=work/'program.ll';obj=work/'program.o';exe=work/'program'
        # The same address-taken local function is reached through a global
        # initializer and directly. Stateful global remains a single cell.
        source.write_text('''@state = private global i32 0
@callback = private global ptr @step
define private i32 @step(i32 %x) {
 %old = load i32, ptr @state
 %new = add i32 %old, %x
 store i32 %new, ptr @state
 ret i32 %new
}
define private i32 @inline_add(i32 %x) alwaysinline {
 %r = add i32 %x, 1
 ret i32 %r
}
define i32 @main() {
 %f = load ptr, ptr @callback
 %same = icmp eq ptr %f, @step
 %a = call i32 %f(i32 2)
 %b = call i32 @step(i32 3)
 %c = call i32 @inline_add(i32 %b)
 %state_ok = icmp eq i32 %c, 6
 %ok = and i1 %same, %state_ok
 %result = select i1 %ok, i32 0, i32 1
 ret i32 %result
}
''')
        subprocess.run([str(install/'clang-parallel'),'-O2','-c',str(source),'-o',str(obj)],check=True)
        receipt=json.loads(obj.with_suffix('.o.parallel.json').read_text())
        assert receipt['complete'] and len([r for r in receipt['commands'] if r['label'].startswith('compile-')])==config['jobs']
        assert any(r['label']=='combine' and '-r' in r['argv'] for r in receipt['commands'])
        subprocess.run([clang,str(obj),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        controls={
            'ctors':'@llvm.global_ctors = appending global [0 x { i32, ptr, ptr }] zeroinitializer\n',
            'blockaddress':'@address = private global ptr blockaddress(@f, %b)\ndefine void @f() {\nentry:\n br label %b\nb:\n ret void\n}\n',
            'alias':'@a = alias i32, ptr @g\n@g = global i32 0\n',
            'tls':'@g = thread_local global i32 0\n',
            'asm':'module asm "nop"\n',
            'reserved':'@__mlf_partition_reserved = global i32 0\n',
            'comdat':'$g = comdat any\n@g = global i32 0, comdat\n'}
        for name,text in controls.items():
            source.write_text(text)
            r=subprocess.run([config['helper']['path'],str(source),str(work/(name+'-')),'4'],capture_output=True)
            assert r.returncode!=0,(name,r.stdout,r.stderr)
        print('native partition, identity/sharing, real object combination and 7 rejection controls passed')
if __name__=='__main__':main()
