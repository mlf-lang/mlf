#!/usr/bin/env python3
"""Retain F1 O0/O2 bodies and inventories with explicit Int64 type adaptation.

The legacy build inventory, both optimization levels and exact expected stdout
remain. Guarded command transport replaces its subprocess wrapper; direct
Int64 Core replaces the retired Integer-narrowing rule proof. Original files
are never rewritten.
"""
from pathlib import Path
import argparse, ast, json, re, types, sys
from legacy_controls import prepare
from run_integrated import ROOT, HERE, LIMITS

def machine_worker(text, name, worker=True):
    blocks=[b for b in text.split('-- RHS size:') if re.search(r'^(?:[A-Za-z.]+\.)?'+(r'\$w' if worker else '')+re.escape(name)+r'(?:\s|$)',b,re.M)]
    if len(blocks)!=1:raise ValueError('unique Int64 Core worker '+name)
    block=blocks[0]
    if 'fingerprintIntStep' in block or any(op in block for op in ['integerMul','integerAdd','integerRem']):
        raise ValueError('retired Integer narrowing path in '+name)
    if not all(op in block for op in ['timesInt64#','plusInt64#','remInt64#']):
        raise ValueError('direct Int64 arithmetic missing '+name)

def verify_int64_core(text):
    for name in ['unmatchedMultiplier','unmatchedModulus']:machine_worker(text,name)

def verify_no_retired_rules(counts, optimization):
    if optimization not in ('0','2') or counts!={'mlf/fingerprintIntStep/65599':0,'mlf/fingerprintIntStep/131':0}:
        raise ValueError('retired Integer narrowing rules must be absent')

def verify_separate_int64(text, counts):
    verify_no_retired_rules(counts,'2')
    machine_worker(text,'fingerprintStateChars',worker=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True);p.add_argument('--source',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    helper=ROOT/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('guard');H.__file__=str(helper);exec(compile(helper.read_bytes(),str(helper),'exec'),H.__dict__)
    frozen=ROOT/'tools/performance/fingerprint-fusion';legacy=frozen/'run_controls.py'
    H.require(H.sha(legacy)=='2355ada62d4149d40a5789104ff5ebf5d82d96d3bb8126530baf083fcdaf7fd1','fixed original F1 driver')
    H.require(H.sha(frozen/'controls/CONTROL-INVENTORY.json')=='5bb87dd71402423fb5a05a9c1df8fdce1f932fb385f5092740668914d2108957','fixed F1 control inventory')
    driver_inputs={str(p):H.sha(p) for p in [Path(__file__),HERE/'legacy_controls.py',HERE/'legacy-controls-pins.json',HERE/'run_integrated.py',helper,legacy,frozen/'controls/CONTROL-INVENTORY.json']}
    controls=out/'adapter/controls';prepare(ROOT,controls,'fingerprint')
    # Module/filename adaptation is undone for the unchanged legacy driver.
    adapted=controls/'FingerprintTests.hs';text=adapted.read_text().replace('module FingerprintTests (main) where','module Tests (main) where')
    (controls/'Tests.hs').write_text(text)
    inventory=H.load(frozen/'controls/CONTROL-INVENTORY.json')
    original_inventory=H.sha(frozen/'controls/CONTROL-INVENTORY.json')
    for name,digest in inventory['source_files'].items():H.require(H.sha(frozen/'controls'/name)==digest,'fixed original F1 oracle/control '+name)
    inventory['source_files']={name:H.sha(controls/name) for name in inventory['source_files']}
    inventory['Int64_migration']={'original_inventory_sha256':original_inventory,'extra_signed_pairs':30,
        'old_large_literal_cases_retained_with_Int64_wrap':True,'noncanonical_divergence_seed':-1,
        'old_arbitrary_Integer_semantics_claimed':False}
    H.save(controls/'CONTROL-INVENTORY.json',inventory)
    control_inputs=H.file_pins(controls)
    tree=ast.parse(legacy.read_text());owner=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    old=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    replacement=ast.parse('''def run(label,command,cwd=ROOT):
    result=H.Runner(out,LIMITS).run(command,cwd,out/'guarded'/label)
    so=(out/'guarded'/label/'stdout').read_bytes();se=(out/'guarded'/label/'stderr').read_bytes()
    (out/(label+'.stdout')).write_bytes(so);(out/(label+'.stderr')).write_bytes(se)
    record['commands'].append({'label':label,**result});save()
    return so,se
''').body[0]
    owner.body[owner.body.index(old)]=replacement
    # This old mechanism is intentionally retired: all language Int arithmetic
    # is already Int64. Replace only its one old rule-count assertion.
    sites=[n for n in ast.walk(owner) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require' and any(isinstance(x,ast.Constant) and x.value=='actual Separate lost literal rules' for x in n.args)]
    H.require(len(sites)==1,'one obsolete actual-source F1 assertion')
    check=ast.parse("verify_separate_int64((actual/'Separate.dump-simpl').read_text(), counts)",mode='eval').body
    sites[0].func=check.func;sites[0].args=check.args;sites[0].keywords=[]
    ast.fix_missing_locations(tree)
    context={'__file__':str(legacy),'__name__':'guarded_f1_legacy','H':H,'LIMITS':LIMITS,'verify_separate_int64':verify_separate_int64}
    exec(compile(tree,str(legacy),'exec'),context)
    context.update(ROOT=a.source.resolve(),HERE=out/'adapter',verify_unmatched_core=verify_int64_core,verify_probe_counts=verify_no_retired_rules)
    sys.argv=[str(legacy),'--producer',str(a.producer.resolve()),'--output',str(out/'checks')]
    with H.SerialLock(ROOT/'.mlf-build'):context['main']()
    H.check_pins(driver_inputs);H.check_pins(control_inputs)
    receipt=H.load(out/'checks/receipt.json')
    H.require(receipt['complete'],'complete retained F1 gate')
    H.save(out/'receipt.json',{'complete':True,'legacy_driver_sha256':H.sha(legacy),'driver_inputs':driver_inputs,'control_inputs':control_inputs,
        'legacy_AST_delta':'guarded command transport; obsolete F1 rule-count assertion replaced by direct Int64 worker proof',
        'original_inventory_sha256':original_inventory,'adapter_sha256':H.sha(Path(__file__)),
        'qualified_checks_receipt_sha256':H.sha(out/'checks/receipt.json'),
        'all_original_test_rows_retained':True,'additional_Int64_pairs_per_optimization':30,
        'retired_Integer_narrowing_rules_absent':True,'direct_Int64_workers_verified':True,
        'unbounded_values_wrap_and_may_duplicate':True,'ordinary_production_objects_unchanged':True})
if __name__=='__main__':main()
