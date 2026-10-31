"""Checked resource IR to static C callbacks (candidate backend, not source proof).

Public generate rechecks exact IR with the accepted Python resource checker.
Only prepare_source establishes genuine CheckedTerm provenance. No generated C
is executed here; the native runner additionally requires the C-runtime gate.
"""
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
import prepare

MAX_POINTER_CELLS=512

OPS={'new_root','new_below','alloc','closure','thunk','application','application_borrow',
     'hole','fill','retain','drop','borrow','end_borrow','field','force','return','finish'}

class CodegenError(ValueError):pass

@dataclass(frozen=True)
class Generated:
    source: str
    canonical_ir: str
    checked_sha256: str
    binding_json: str
    def binding(self):return json.loads(self.binding_json)

class Emitter:
    def __init__(self,program,checked_sha):
        self.p=program;self.sha=checked_sha;self.strings={};self.static_objects=[]
        self.shape_ids={name:'shape_'+str(i) for i,name in enumerate(sorted(list(program['layouts'])+['@'+s for s in program['signatures']]))}
        self.code_ids={('function',name):'code_'+str(i) for i,name in enumerate(sorted(program['functions']))}
        offset=len(self.code_ids)
        self.code_ids.update({('thunk',name):'code_'+str(offset+i) for i,name in enumerate(sorted(program['codes']))})
        self.field_orders={name:sorted(fields) for name,fields in program['layouts'].items()}
        self.capture_orders={}
        self.maps={'shapes':self.shape_ids,'fields':self.field_orders,'callbacks':{},'ssa':{},'frame_pointer_cells':{}}
        self.parts=[]

    def string(self,value):
        if value not in self.strings:self.strings[value]='text_'+str(len(self.strings))
        return self.strings[value]
    def shape(self,name):return '&'+self.shape_ids[name]
    def array(self,values):return '(RtHandle *const[]){'+','.join(values)+'}' if values else 'NULL'
    def field_descriptor(self,identifier,names,shapes):
        if not names:return 'NULL'
        self.parts.append('static const RtField '+identifier+'[] = {'+','.join('{'+self.string(n)+','+self.shape(shapes[n])+'}' for n in names)+'};')
        self.static_objects.append(identifier)
        return identifier

    def descriptors(self):
        self.parts.append('/* Exact canonical checked shape/callback descriptors. */')
        for var in self.shape_ids.values():self.parts.append('static const RtShape '+var+';')
        for var in self.code_ids.values():
            self.parts.append('static const RtCode '+var+';')
            self.parts.append('static RtHandle *body_'+var+'(RtContext *,RtHandle *,RtHandle **,RtHandle *);')
        for name,var in self.shape_ids.items():
            if name.startswith('@'):
                sig=self.p['signatures'][name[1:]]
                init=f'{self.string(name)},RT_REPEAT,0,NULL,{self.shape(sig["argument"])},{self.shape(sig["result"])}'
            else:
                fields=self.p['layouts'][name];names=self.field_orders[name]
                table=self.field_descriptor('fields_'+var,names,fields)
                init=f'{self.string(name)},RT_DATA,{len(names)},{table},NULL,NULL'
            self.parts.append('static const RtShape '+var+' = {'+init+'};');self.static_objects.append(var)
        for (kind,name),var in self.code_ids.items():
            spec=self.p['functions' if kind=='function' else 'codes'][name];names=sorted(spec['captures'])
            self.capture_orders[kind,name]=names
            table=self.field_descriptor('captures_'+var,names,{n:spec['captures'][n]['layout'] for n in names})
            shape='@'+spec['signature'] if kind=='function' else spec['result']
            identity=int(kind=='function' and self.p['signatures'][spec['signature']]['result_identity']=='argument')
            self.parts.append(f'static const RtCode {var} = {{{self.string(name)},RT_{"FUNCTION" if kind=="function" else "THUNK"},{self.shape(shape)},{len(names)},{table},body_{var},{identity}}};')
            self.static_objects.append(var);self.maps['callbacks'][var]={'kind':kind,'name':name,'captures':names}

    def block(self,body,scope,initial=None):
        # All effectful helpers occur in separate statements. Array expressions
        # contain only previously evaluated live pointers, never helper calls.
        # Conservative sum of all declared local pointers and compound-array
        # elements, without relying on compiler lifetime/slot reuse. C parameter
        # and fixed helper-frame overhead remain separately platform bounded.
        pointer_cells=(4+len(initial or {})) if scope!='entry' else 1
        for instruction in body:
            pointer_cells+=int('out' in instruction)
            if instruction['op'] in ('new_root','new_below'):pointer_cells+=len(instruction['imports'])
            elif instruction['op']=='alloc':pointer_cells+=len(instruction['fields'])
            elif instruction['op'] in ('closure','thunk'):pointer_cells+=len(instruction['captures'])
        if pointer_cells>MAX_POINTER_CELLS:
            raise CodegenError(f'native frame pointer-cell bound exceeded in {scope}: {pointer_cells}>{MAX_POINTER_CELLS}')
        self.maps['frame_pointer_cells'][scope]=pointer_cells
        live=dict(initial or {});out=[];counter=0;mapping={}
        def get(name):
            if name not in live:raise CodegenError('not live at C emission: '+name)
            return live[name][0]
        def shape(name):
            if name not in live:raise CodegenError('missing native shape: '+name)
            return live[name][1]
        def bind(name,s,expr):
            nonlocal counter
            v='local_'+str(counter);counter+=1
            if name in live:raise CodegenError('duplicate native local')
            live[name]=(v,s);mapping[name]=v;out.append(f'  RtHandle *{v} = {expr};')
        for i in body:
            op=i['op']
            if op not in OPS:raise CodegenError('unsupported native opcode: '+op)
            if op in ['new_root','new_below']:
                imports=[get(n) for n in i['imports']]
                prefix='rt_new_root(ctx,' if op=='new_root' else 'rt_new_below(ctx,'+get(i['ceiling'])+','
                bind(i['out'],None,prefix+str(len(imports))+','+self.array(imports)+')')
            elif op in ['alloc','closure','thunk','hole']:
                args=[get(i['in'])]
                if op in ['alloc','hole']:
                    s=i['layout'];args.append(self.shape(s))
                    if op=='alloc':args.append(self.array([get(i['fields'][n]) for n in self.field_orders[s]]))
                else:
                    kind='function' if op=='closure' else 'thunk';name=i[kind if kind=='function' else 'code']
                    spec=self.p['functions' if kind=='function' else 'codes'][name]
                    s='@'+spec['signature'] if kind=='function' else spec['result']
                    args += ['&'+self.code_ids[kind,name],self.array([get(i['captures'][n]) for n in self.capture_orders[kind,name]])]
                args.append(self.string(i['out']))
                bind(i['out'],s,'rt_'+op+'(ctx,'+','.join(args)+')')
            elif op in ['application','application_borrow']:
                sig=self.p['signatures'][shape(i['function'])[1:]]
                bind(i['out'],sig['result'],'rt_'+op+'(ctx,'+','.join([get(i['in']),get(i['function']),get(i['argument']),self.string(i['out'])])+')')
            elif op=='fill':
                out.append('  rt_fill(ctx,'+','.join([get(i['hole']),get(i['value']),self.string(i['hole']),self.string(i['value'])])+');')
            elif op in ['retain','borrow']:
                bind(i['out'],shape(i['value']),'rt_'+op+'(ctx,'+get(i['value'])+')')
            elif op in ['drop','end_borrow']:
                out.append('  rt_'+op+'(ctx,'+get(i['value'])+');');del live[i['value']]
            elif op=='field':
                s=shape(i['value']);field=i['field'];index=self.field_orders[s].index(field)
                bind(i['out'],self.p['layouts'][s][field],'rt_field(ctx,'+','.join([get(i['value']),str(index),self.string(i['out']),self.string(i['value'])])+')')
            elif op=='force':
                s=shape(i['value']);value=get(i['value']);del live[i['value']]
                bind(i['out'],s,'rt_force(ctx,'+','.join([value,self.string(i['out']),self.string(i['value'])])+')')
            elif op=='return':
                out.append('  return rt_return(ctx,'+get(i['value'])+');');del live[i['value']]
            elif op=='finish':out.append('  rt_finish_entry(ctx);')
        expected={'$home'} if scope!='entry' else set()
        if set(live)!=expected:raise CodegenError('native emission left local ownership variables: '+repr(set(live)))
        self.maps['ssa'][scope]=mapping
        return out

    def callbacks(self):
        for (kind,name),var in self.code_ids.items():
            spec=self.p['functions' if kind=='function' else 'codes'][name]
            self.parts.append(f'static RtHandle *body_{var}(RtContext *ctx,RtHandle *home,RtHandle **captures,RtHandle *argument) {{')
            self.parts.append('  (void)home; (void)captures; (void)argument;')
            initial={'$home':('home',None)}
            for index,n in enumerate(self.capture_orders[kind,name]):
                local='capture_'+str(index);self.parts.append(f'  RtHandle *{local} = captures[{index}];')
                initial[n]=(local,spec['captures'][n]['layout'])
            if kind=='function':
                initial[spec['parameter']]=('argument',self.p['signatures'][spec['signature']]['argument'])
            self.parts.extend(self.block(spec['body'],var,initial));self.parts.append('}')
        self.parts.append('static void entry(RtContext *ctx) {');self.parts.extend(self.block(self.p['entry'],'entry'));self.parts.append('}')

    def emit(self):
        self.descriptors();self.callbacks()
        shapes=list(self.shape_ids.values());codes=list(self.code_ids.values())
        self.parts.append('static const RtShape *const shapes[] = {'+','.join('&'+s for s in shapes)+'};');self.static_objects.append('shapes')
        if codes:
            self.parts.append('static const RtCode *const codes[] = {'+','.join('&'+c for c in codes)+'};');self.static_objects.append('codes')
        artifact=self.string(self.sha)
        # Each diagnostic string has its own named array, so declared descriptor
        # bytes are exact sizeof expressions, not UTF-8 character-count guesses.
        total='sizeof(RtProgram)+'+'+'.join('sizeof('+o+')' for o in self.static_objects+list(self.strings.values()))
        self.parts.append(f'static const RtProgram program = {{{artifact},{len(shapes)},shapes,{len(codes)},{"codes" if codes else "NULL"},{total}}};')
        self.parts.extend(['int main(int argc,char **argv) {','  RtOptions options = {1000000,0};',
                           '  if (argc==2 && strcmp(argv[1],"--trace")==0) options.event_limit=100000;',
                           '  else if (argc!=1) { fputs("usage: generated-program [--trace]\\n",stderr); return 64; }',
                           '  return rt_run(&program,entry,&options,stdout,NULL);','}'])
        prefix=['/* Generated from independently checked immutable resource IR. */','#include "rir_runtime.h"','#include <string.h>']
        for value,identifier in self.strings.items():
            encoded=''.join('\\%03o'%b for b in value.encode('utf-8'))
            prefix.append(f'static const char {identifier}[] = "{encoded}";')
        return '\n'.join(prefix+self.parts)+'\n'


def generate(program:dict,*,expected_sha256:str|None=None)->Generated:
    reference=prepare.frozen_reference();lock,source=reference.kernel_identity(prepare.BASE/'validation/kernel-lock.json')
    kernel=reference.load_kernel(lock,source);checked=kernel.check(program);p=checked.data()
    if expected_sha256 is not None and checked.sha256!=expected_sha256:raise CodegenError('codegen artifact differs from actual prepared snapshot')
    # C ABI diagnostic/schema names are NUL-terminated strings. Distinct checked
    # JSON names must never collapse under strcmp/strlen. Reject before emission.
    def reject_nul(value):
        if isinstance(value,str) and "\0" in value:raise CodegenError('embedded NUL is outside the native name ABI')
        if isinstance(value,dict):
            for key,item in value.items():reject_nul(key);reject_nul(item)
        elif isinstance(value,list):
            for item in value:reject_nul(item)
    reject_nul(p)
    if p['version']!=3:raise CodegenError('native backend requires checked version3')
    if any(s['protocol']!='repeat' for s in p['signatures'].values()):raise CodegenError('Once is outside the native subset')
    for block in [p['entry']]+[v['body'] for v in p['codes'].values()]+[v['body'] for v in p['functions'].values()]:
        for instruction in block:
            if instruction['op'] not in OPS:raise CodegenError('unsupported native opcode: '+instruction['op'])
    emitter=Emitter(p,checked.sha256);source=emitter.emit()
    binding={'checked_ir_sha256':checked.sha256,'generated_c_sha256':hashlib.sha256(source.encode()).hexdigest(),
             'mapping':emitter.maps,'max_frame_pointer_cells':MAX_POINTER_CELLS,'native_C_executed':False,'ordinary_provenance_claim':False,
             'scope':'rechecked resource IR to static C; genuine source origin only from prepare_source'}
    return Generated(source,checked.canonical_json,checked.sha256,json.dumps(binding,sort_keys=True,separators=(',',':')))
