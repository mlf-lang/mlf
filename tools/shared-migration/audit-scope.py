#!/usr/bin/env python3
"""Summarize an Audit.hs TSV and reject unsigned/open runtime cycles."""
import pathlib,json,collections,sys
rows=[l.split('\t') for l in pathlib.Path(sys.argv[1]).read_text().splitlines()]
modules=collections.defaultdict(dict)
for row in rows:
    if row[1]=='GROUP_BINDING' and row[3]=='top':
        modules[row[0]][row[4]]=(row[5].split(',') if row[5] else [],row[6],row[7])
cycles=[]; errors=[]
for module,bindings in modules.items():
    indices={}; low={}; stack=[]; active=set()
    def visit(name):
        indices[name]=low[name]=len(indices); stack.append(name); active.add(name)
        for dependency in bindings[name][0]:
            if dependency not in indices:
                visit(dependency); low[name]=min(low[name],low[dependency])
            elif dependency in active:
                low[name]=min(low[name],indices[dependency])
        if low[name]==indices[name]:
            component=[]
            while True:
                member=stack.pop(); active.remove(member); component.append(member)
                if member==name: break
            if len(component)>1 or name in bindings[name][0]:
                cycles.append([module,component])
                errors.extend([module,n,bindings[n][1]] for n in component if bindings[n][1]!='[]')
    for name in bindings:
        if name not in indices: visit(name)
summary={'module_count':sum(r[1]=='MODULE' for r in rows),
         'string_pattern_leaves':sum(r[1]=='STRING_PATTERN' for r in rows),
         'string_pattern_modules':dict(collections.Counter(r[0] for r in rows if r[1]=='STRING_PATTERN')),
         'ordinary_local_bindings':sum(r[1]=='GROUP_BINDING' and r[3].startswith('sequential') for r in rows),
         'ordinary_self_capture_hazards':sum(r[1]=='GROUP_BINDING' and r[3].startswith('sequential') and r[4] in r[5].split(',') for r in rows),
         'cyclic_top_level_SCCs':len(cycles),'cyclic_bindings':sum(len(c[1]) for c in cycles),
         'missing_or_open_cyclic_signatures':errors,'cycles':cycles}
pathlib.Path(sys.argv[2]).write_text(json.dumps(summary,indent=2)+'\n')
if errors: raise SystemExit('Unsigned/open recursive implementation bindings: '+repr(errors))
print(json.dumps({k:v for k,v in summary.items() if k not in ['cycles','string_pattern_modules']}))
