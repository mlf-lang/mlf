"""Static protocol and genuine serialized plan resolution, never a runtime entry."""
from pathlib import Path
import ast,hashlib,json,re,symtable
D=Path(__file__).resolve().parent;R=D.parent
checks=[]
def yes(v):assert v
def case(name,fn):fn();checks.append({'name':name,'passed':True})
def pin(p):b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
c=json.loads((D/'BINDINGS.json').read_bytes())
def checkpin(p):yes(pin(Path(p['path']))==p)
case('actual setup review exactly frozen independent PASS pin',lambda:checkpin(c['setup_review']))
case('frozen91 plan identity',lambda:checkpin(c['plan_commands']))
t=ast.parse((D/'semantic_parsers.py').read_text());nodes=[n for n in t.body if isinstance(n,ast.FunctionDef)]
for n in ast.walk(ast.Module(body=nodes,type_ignores=[])):
    if isinstance(n,ast.Name):assert n.id not in {'Path','open','os','subprocess','module','__import__'}
ns={'json':json,'re':re};exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pure-serialized-plan-resolution>','exec'),ns)
plan=json.loads(Path(c['plan_commands']['path']).read_bytes());worker=json.loads(Path(c['setup_worker']['path']).read_bytes())
rows=ns['resolved_commands'](plan,c['setup_work'],worker)
case('complete actual serialized runtime/argv resolution91',lambda:yes(len(rows)==91 and [r['ordinal'] for r in rows]==list(range(1,92))))
counts={}
for r in rows:counts[r['kind']]=counts.get(r['kind'],0)+1
case('exact12+12+33+12+12+10 ledger counts',lambda:yes(counts==plan['counts']))
case('exact24 mandatory reports, none original-reference',lambda:yes(sum('report_sink' in r for r in rows)==24 and all('report_sink' not in r for r in rows if r['kind'].startswith('reference_'))))
case('RTS sinks remain exact parent SETUP active tree',lambda:yes(all(r['report_sink'].startswith(c['setup_work']+'/active/') for r in rows if 'report_sink' in r)))
for r in rows:
    if r['kind']=='runtime':
        role=r['label'].removeprefix('runtime-').removesuffix('-before').removesuffix('-after');b=worker['runtime_after'][role]
        case('actual runtime argv '+r['label'],lambda r=r,b=b:yes(r['argv_template']==[b['loader']['resolved'],'--list',b['executable']['resolved']]))
    if r['kind']=='ghc_typed':
        a=r['argv_template'];sources=list(r['expected_home_modules'].values())
        case('exact declared GHC inputs/interfaces '+r['cell'],lambda a=a,r=r,sources=sources:yes(all(a.count(p)==1 for p in sources) and len(r['expected_relative_interfaces'])==len(sources) and all(x in a for x in ['-fno-code','-fwrite-interface','-no-link','-fforce-recomp','-hide-all-packages'])))
controller=(D/'controller.py').read_text();ct=ast.parse(controller);wt=ast.parse((D/'worker.py').read_text());functions={n.name:n for n in ct.body if isinstance(n,ast.FunctionDef)}
table=symtable.symtable(controller,'controller.py','exec');defined={x.get_name() for x in table.get_symbols() if x.is_assigned() or x.is_imported() or x.is_namespace()};builtins=set(dir(__builtins__));unknown={}
def visit(t):
    if t.get_type()!='module':
        miss={x.get_name() for x in t.get_symbols() if x.is_global() and x.is_referenced()}-defined-builtins-{'__file__','__name__'}
        if miss:unknown[t.get_name()]=sorted(miss)
    for ch in t.get_children():visit(ch)
visit(table);case('no unresolved controller globals',lambda:yes(not unknown))
attrs={n.attr for n in ast.walk(wt) if isinstance(n,ast.Attribute) and (isinstance(n.value,ast.Name) and n.value.id=='C' or isinstance(n.value,ast.Attribute) and isinstance(n.value.value,ast.Name) and n.value.value.id=='self' and n.value.attr=='C')}
case('all worker-controller API methods present',lambda:yes(not attrs-set(functions)-{'PB','READY'}))
case('disabled controller exact single READY declaration',lambda:yes(controller.count('\nREADY = False\n')==1))
case('entry strictly follows all definitions',lambda:yes(isinstance(ct.body[-1],ast.If) and sum(isinstance(n,ast.If) for n in ct.body)==1))
case('original immutable guard pin retained',lambda:yes(c['guard']['sha256']=='53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e'))
case('no semantic scope or actual admission created',lambda:yes(not Path(c['work']).exists()))
case('all actual12 counts and owners remain unknown',lambda:yes(c['actual_query_counts'] is None and c['actual_owner_observations'] is None and c['actual_qualification_review'] is None))
case('no48-leg/native/performance worker implemented',lambda:yes(c['sampling_runner_included'] is False and c['performance_sample_count']==0 and c['command_count']==91))
old=(R/'main-gap-setup-v5-source/controller.py').read_text();ot=ast.parse(old);of={n.name:n for n in ot.body if isinstance(n,ast.FunctionDef)}
equal=sorted(k for k in functions.keys()&of.keys() if ast.dump(functions[k],include_attributes=False)==ast.dump(of[k],include_attributes=False))
case('mature pure/helper functions exact AST ancestry',lambda:yes({'safe','sha','pin','load','save','module','source_check','row_sha','interface','runtime_module','completed_epoch_identity'}<=set(equal)))
result={'schema':'main-gap-semantic-protocol-pure-checks-v1','complete':True,'count':len(checks),'checks':checks,
    'genuine_setup_worker':c['setup_worker'],'resolved_row_count':len(rows),'resolved_kind_counts':counts,
    'unchanged_mature_function_AST':equal,'raw_semantic_oracles_do_not_include_RTS_or_guard_logs':True,
    'controller_top_level_imported':False,'guard_runtime_loader_lock_target_executed':False,'source_gate_passed':None}
(D/'protocol-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('protocol pure checks',len(checks))
