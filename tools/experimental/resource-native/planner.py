"""Bounded syntax-directed fine-group and temporary-operand-borrow planning.

Candidate generator only. No evaluator, collector, heap-order oracle, principal
inference, or proof by trace appears in this file. The actual v7 IR checker is
mandatory and independently audited; a plan explanation never overrides it.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import types

BASE=Path(__file__).resolve().parent
_blob=(BASE/"transport.py").read_bytes()
TRANSPORT_SHA256=hashlib.sha256(_blob).hexdigest()
baseline=types.ModuleType("_resource_recursion_transport")
baseline.__file__=str(BASE/"transport.py");sys.modules[baseline.__name__]=baseline
exec(compile(_blob,baseline.__file__,"exec"),baseline.__dict__)
BridgeError=baseline.BridgeError


@dataclass(frozen=True)
class Reference:
    variable: str
    shape: object
    strict: bool  # actual proof of group < current invocation home, not <=
    mode: str="own"
    anchor: str | None=None

    @property
    def authority(self):
        return self.anchor if self.mode=="loan" else self.variable


class Planner:
    def __init__(self, groups: bool, borrows: bool, representation):
        self.rep=representation
        self.next_var=0;self.next_function=0;self.next_code=0
        self.signatures={};self.signature_names={};self.functions={};self.codes={}
        self.source_map={"functions":{},"applications":{},"cases":{},"knots":{},"primitives":{},"conditionals":{},"sum_cases":{},"sum_families":{},"field_cases":{}}
        self.layouts={"Unit":{}}
        self.layout_names={shape:"D"+str(i) for i,shape in enumerate(self.rep.records)}
        self.family_names={shape:'F'+str(meta.get('view_index',i)) for i,(shape,meta) in enumerate(self.rep.sums.items())}
        self.families={self.family_names[shape]:{'variants':[c['constructor'] for c in meta['constructors']],
            'fields':{c['constructor']:[self.shape_name(t) for t in self.rep.variant_for(shape,c['constructor'])['field_shapes']]
                      for c in meta['constructors']}} for shape,meta in self.rep.sums.items()}
        self.source_map['sum_families']={self.family_names[shape]:{'datatype':meta['datatype'],
            'declaration_index':meta['declaration_index'],'arguments':meta['arguments'],**self.rep.source_view(meta),
            'variants':[{'name':c['constructor'],'id':i,'arity':c['arity'],
                'fields':c['fields']} for i,c in enumerate(meta['constructors'])]}
            for shape,meta in self.rep.sums.items()}
        for shape,meta in self.rep.records.items():
            self.layouts[self.layout_names[shape]]={"f"+str(i):self.shape_name(t) for i,t in enumerate(meta["field_shapes"])}
        self.groups=groups
        self.borrows=borrows
        self.decisions=[]
        self.borrow_sites=[]

    def fresh(self,prefix="v"):
        self.next_var+=1
        return prefix+str(self.next_var)

    def shape_name(self,shape):
        if shape=="Unit":return "Unit"
        if shape in ('#i64', '#bool'):return shape
        if isinstance(shape,baseline.Nominal):return '%'+self.family_names[shape] if shape in self.family_names else self.layout_names[shape]
        if shape in self.signature_names:return "@"+self.signature_names[shape]
        label="S"+str(len(self.signature_names)+1);self.signature_names[shape]=label
        self.signatures[label]={"argument":self.shape_name(shape[0]),"result":self.shape_name(shape[1]),"protocol":"repeat","result_identity":"unknown"}
        return "@"+label

    def allocation(self, home: str, support: list[Reference], body: list, path: str, kind: str):
        """Complete actual carriers become imports; their deep support is owned.

        If a carrier is only Down(home), importing it into a fresh child would
        assert an unproved strict edge. Preserve a visible same-home fallback.
        """
        can_split=self.groups and all(r.strict for r in support)
        imports=list(dict.fromkeys(r.authority for r in support))
        if can_split:
            key=self.fresh("group")
            body.append({"op":"new_below","out":key,"ceiling":home,"imports":imports})
        else:key=home
        self.decisions.append({"path":path,"kind":kind,"home":home,"allocation_key":key,
                               "strategy":"fresh-below" if can_split else "same-home",
                               "reason":"all-support-strict" if can_split else
                                        ("groups-disabled" if not self.groups else "support-only-Down"),
                               "support":[{"reference":r.variable,"authority":r.authority,"strict":r.strict,"mode":r.mode} for r in support]})
        return key,can_split

    @staticmethod
    def close_builder(key: str, split: bool, body: list):
        if split:body.append({"op":"drop","value":key})

    @staticmethod
    def release(ref: Reference, body: list):
        body.append({"op":"end_borrow" if ref.mode=="loan" else "drop","value":ref.variable})

    def operand(self,node:dict,env:dict[int,Reference],home:str,body:list,path:str)->Reference:
        actual=baseline.strip(node)
        if self.borrows and actual["tag"]=="var":
            source=env[actual["name"]["id"]]
            if source.mode!="own":raise BridgeError("compiler environment must own its anchors")
            loan=self.fresh("loan")
            body.append({"op":"borrow","out":loan,"value":source.variable})
            self.borrow_sites.append({"path":path,"loan":loan,"anchor":source.variable,
                                      "use":"immediate-owning-application-slot-publication"})
            return Reference(loan,source.shape,source.strict,"loan",source.variable)
        return self.emit(node,env,home,body,path)

    def conditional_alternative(self,node,env,home,body,path,kind="conditional-alternative-thunk"):
        """Always delay the entire alternative, including let/case/application ASTs."""
        ids=sorted(baseline.free_vars(node));support=[env[i] for i in ids]
        key,split=self.allocation(home,support,body,path,kind)
        actual={};contracts={};inner={}
        for i in ids:
            source=env[i];capture=self.fresh('branchcapture');strict=split or source.strict
            actual[capture]=source.variable
            contracts[capture]={'layout':self.shape_name(source.shape),'relation':'below' if strict else 'down'}
            inner[i]=Reference(capture,source.shape,strict)
        self.next_code+=1;code='C'+str(self.next_code);cb=[]
        result=self.emit(node,inner,'$home',cb,path+'.body')
        if result.shape!='#i64':raise BridgeError('conditional alternative must have actual Int representation')
        for ref in inner.values():self.release(ref,cb)
        cb.append({'op':'return','value':result.variable})
        self.codes[code]={'result':'#i64','captures':contracts,'body':cb}
        out=self.fresh('branch');body.append({'op':'thunk','out':out,'in':key,'code':code,'captures':actual})
        self.close_builder(key,split,body)
        return Reference(out,'#i64',split),code

    def field_case_arm(self,alternative,variant,env,path):
        """Compile one whole arm; no runtime field projection/allocation occurs here."""
        positions={n['id']:(i,shape) for i,(n,shape) in enumerate(zip(alternative['pattern']['fields'],variant['field_shapes'])) if n is not None}
        free=baseline.free_vars(alternative['body']);field_ids=sorted(free&set(positions));external_ids=sorted(free-set(positions))
        if len(field_ids)>32 or len(external_ids)>32 or len(field_ids)+len(external_ids)>64:
            raise BridgeError('field-case callback capture budget exceeded')
        contracts={};bindings={};inner={};source_fields={}
        for ident in field_ids:
            index,shape=positions[ident];capture=self.fresh('payloadcapture')
            contracts[capture]={'layout':self.shape_name(shape),'relation':'down'}
            bindings[capture]={'kind':'field','index':index};inner[ident]=Reference(capture,shape,False)
            source_fields[capture]={'index':index,'binder':ident,'layout':self.shape_name(shape)}
        for ident in external_ids:
            source=env[ident];capture=self.fresh('externalcapture')
            contracts[capture]={'layout':self.shape_name(source.shape),'relation':'below' if source.strict else 'down'}
            bindings[capture]={'kind':'external','value':source.variable};inner[ident]=Reference(capture,source.shape,source.strict)
        self.next_code+=1;code='C'+str(self.next_code);body=[]
        value=self.emit(alternative['body'],inner,'$home',body,path+'.body')
        if value.shape!='#i64':raise BridgeError('field case callback requires actual Int result')
        for ref in inner.values():self.release(ref,body)
        body.append({'op':'return','value':value.variable})
        self.codes[code]={'result':'#i64','captures':contracts,'body':body}
        return {'code':code,'captures':bindings},{'code':code,'field_bindings':source_fields,
            'external_binder_ids':external_ids,'declared_field_count':variant['arity'],
            'captured_field_bitmap':sum(1<<index for index in {x['index'] for x in source_fields.values()})}

    def emit_conditional(self,node,primitive,arguments,env,home,body,path):
        baseline.primitive_arguments(primitive)
        if len(arguments)!=3:raise BridgeError('Int conditional must be directly fully saturated with three operands')
        shape=self.rep.shape_of(node,{i:r.shape for i,r in env.items()})
        if shape!='#i64':raise BridgeError('conditional result representation differs from actual Int instantiation')
        ids=sorted(baseline.free_vars(node));support=[env[i] for i in ids]
        key,split=self.allocation(home,support,body,path,'int-conditional-thunk')
        actual={};contracts={};inner={}
        for i in ids:
            source=env[i];capture=self.fresh('ifcapture');strict=split or source.strict
            actual[capture]=source.variable
            contracts[capture]={'layout':self.shape_name(source.shape),'relation':'below' if strict else 'down'}
            inner[i]=Reference(capture,source.shape,strict)
        self.next_code+=1;code='C'+str(self.next_code);cb=[]
        condition=self.emit(arguments[0],inner,'$home',cb,path+'.condition')
        ready=self.fresh('condition');cb.append({'op':'force','out':ready,'value':condition.variable})
        yes,yes_code=self.conditional_alternative(arguments[1],inner,'$home',cb,path+'.then')
        no,no_code=self.conditional_alternative(arguments[2],inner,'$home',cb,path+'.else')
        selected=self.fresh('selected')
        # Both alternative owners are consumed. The selected exact owner/cursor
        # transfers unchanged; only the other owner is dropped. No branch Force.
        cb.append({'op':'select_i64','out':selected,'in':'$home','condition':ready,'then':yes.variable,'else':no.variable})
        cb.append({'op':'drop','value':ready})
        for ref in inner.values():self.release(ref,cb)
        cb.append({'op':'return','value':selected})
        self.codes[code]={'result':'#i64','captures':contracts,'body':cb}
        self.source_map['conditionals'][code]={'path':path,'id':13,'name':'ifThenElse',
            'type_arguments':primitive['arguments'],'then_code':yes_code,'else_code':no_code,
            'order':['condition','selected-alternative'],'both_alternatives_delayed':True}
        out=self.fresh();body.append({'op':'thunk','out':out,'in':key,'code':code,'captures':actual})
        self.close_builder(key,split,body)
        return Reference(out,'#i64',split)

    def emit(self,node:dict,env:dict[int,Reference],home:str,body:list,path:str)->Reference:
        node=baseline.strip(node);tag=node["tag"]
        # Only actual checked primitive IDs, not source binder names, select
        # these operations. Strict evaluation occurs inside the delayed thunk.
        cursor=node;arguments=[]
        while cursor['tag']=='application':
            arguments.append(cursor['argument']);cursor=baseline.strip(cursor['function'])
        if cursor['tag']=='primitive':
            primitive,result_shape=baseline.primitive_contract(cursor)
            if cursor['id']==13:
                return self.emit_conditional(node,cursor,list(reversed(arguments)),env,home,body,path)
            if cursor['arguments'] != [] or len(arguments)!=2:
                raise BridgeError('scalar primitives must be directly fully saturated with two operands')
            arguments.reverse()
            shape=self.rep.shape_of(node,{i:r.shape for i,r in env.items()})
            if shape!=result_shape:raise BridgeError('primitive result representation mismatch')
            ids=sorted(baseline.free_vars(node));support=[env[i] for i in ids]
            key,split=self.allocation(home,support,body,path,'primitive-thunk')
            actual={};contracts={};inner={}
            for i in ids:
                source=env[i];capture=self.fresh('primcapture');strict=split or source.strict
                actual[capture]=source.variable
                contracts[capture]={'layout':self.shape_name(source.shape),'relation':'below' if strict else 'down'}
                inner[i]=Reference(capture,source.shape,strict)
            self.next_code+=1;code='C'+str(self.next_code)
            self.source_map['primitives'][code]={'path':path,'id':cursor['id'],'name':primitive,'order':['left','right']}
            cb=[]
            left=self.emit(arguments[0],inner,'$home',cb,path+'.left')
            ready_left=self.fresh('left');cb.append({'op':'force','out':ready_left,'value':left.variable})
            right=self.emit(arguments[1],inner,'$home',cb,path+'.right')
            ready_right=self.fresh('right');cb.append({'op':'force','out':ready_right,'value':right.variable})
            result=self.fresh('scalar')
            cb.append({'op':'prim2','out':result,'in':'$home','primitive':primitive,'left':ready_left,'right':ready_right})
            cb.extend([{'op':'drop','value':ready_left},{'op':'drop','value':ready_right}])
            for ref in inner.values():self.release(ref,cb)
            cb.append({'op':'return','value':result})
            self.codes[code]={'result':result_shape,'captures':contracts,'body':cb}
            out=self.fresh();body.append({'op':'thunk','out':out,'in':key,'code':code,'captures':actual})
            self.close_builder(key,split,body)
            return Reference(out,shape,split)
        if tag in ('int64','bool'):
            baseline.scalar_payload(tag,node['value'])
            key,split=self.allocation(home,[],body,path,tag)
            out=self.fresh();kind='i64' if tag=='int64' else 'bool'
            body.append({'op':'scalar','out':out,'in':key,'kind':kind,'value':node['value']})
            self.close_builder(key,split,body)
            return Reference(out,'#'+kind,split)
        spine=baseline.constructor_spine(node)
        if spine:
            head,args=spine;metadata=self.rep.constructor_for(head["name"],head["arguments"])
            if len(args)!=metadata["arity"]:
                raise BridgeError("custom constructors must be fully saturated")
            if metadata['family_kind']=='sum':
                if head['arguments']!=metadata['arguments']:raise BridgeError('sum constructor exact closed instance differs')
                fields=[self.emit(arg,env,home,body,path+'.field['+str(i)+']') for i,arg in enumerate(args)]
                key,split=self.allocation(home,fields,body,path,'nominal-sum-constructor')
                out=self.fresh('variant');instruction={'op':'construct_sum' if fields else 'construct_nullary',
                    'out':out,'in':key,'family':self.family_names[metadata['shape']],'variant':metadata['constructor']}
                if fields:instruction['fields']=[r.variable for r in fields]
                body.append(instruction)
                for ref in fields:self.release(ref,body)
                self.close_builder(key,split,body)
                return Reference(out,metadata['shape'],split)
            fields=[self.emit(arg,env,home,body,path+".function"*(len(args)-i-1)+".argument") for i,arg in enumerate(args)]
            key,split=self.allocation(home,fields,body,path,"constructor")
            out=self.fresh();shape=metadata["shape"]
            body.append({"op":"alloc","out":out,"in":key,"layout":self.shape_name(shape),"fields":{"f"+str(i):r.variable for i,r in enumerate(fields)}})
            for ref in fields:self.release(ref,body)
            self.close_builder(key,split,body)
            return Reference(out,shape,split)
        if tag=="letrec":
            binding_ids={b["name"]["id"] for b in node["bindings"]}
            external=set().union(*(baseline.free_vars(b["value"]) for b in node["bindings"]))-binding_ids
            key,split=self.allocation(home,[env[i] for i in sorted(external)],body,path,"recursive-knot")
            self.source_map["knots"][path]={"allocation_key":key,"bindings":{}}
            # The knot scope resets physical-home facts. A fresh knot is above
            # its imported external supports; otherwise preserve known strictness.
            inner={i:Reference(r.variable,r.shape,split or r.strict) for i,r in env.items() if i in external}
            holes={}
            for b in node["bindings"]:
                shape=self.rep.type_shape(b["type"]);hole=self.fresh("hole")
                body.append({"op":"hole","out":hole,"in":key,"layout":self.shape_name(shape)})
                holes[b["name"]["id"]]=Reference(hole,shape,False)
                self.source_map["knots"][path]["bindings"][str(b["name"]["id"])]=hole
            inner.update(holes)
            for index,b in enumerate(node["bindings"]):
                rhs=self.emit(b["value"],inner,key,body,path+".binding"+str(index))
                body.append({"op":"fill","hole":holes[b["name"]["id"]].variable,"value":rhs.variable})
                self.release(rhs,body)
            # All construction tickets filled before body can publish demand.
            outer=env|{i:Reference(r.variable,r.shape,split) for i,r in holes.items()}
            result=self.emit(node["body"],outer,home,body,path+".body")
            for ref in holes.values():self.release(ref,body)
            self.close_builder(key,split,body)
            return result
        if tag=="case":
            shape=self.rep.shape_of(node,{i:r.shape for i,r in env.items()})
            ids=sorted(baseline.free_vars(node));support=[env[i] for i in ids]
            key,split=self.allocation(home,support,body,path,"case-thunk")
            actual={};contracts={};inner={}
            for i in ids:
                source=env[i];capture=self.fresh("casecapture");strict=split or source.strict
                actual[capture]=source.variable
                contracts[capture]={"layout":self.shape_name(source.shape),"relation":"below" if strict else "down"}
                inner[i]=Reference(capture,source.shape,strict)
            self.next_code+=1;code="C"+str(self.next_code);self.source_map["cases"][code]=path
            cb=[];raw=self.emit(node["scrutinee"],inner,"$home",cb,path+".scrutinee")
            ready=self.fresh("scrutinee");cb.append({"op":"force","out":ready,"value":raw.variable})
            if raw.shape in self.rep.sums:
                # Force scrutinee only. All complete arms become separate thunks.
                # Use validated family declaration order, not source arm order.
                metadata=self.rep.sums[raw.shape];family=self.family_names[raw.shape]
                alternatives={a['pattern']['constructor']:a for a in node['alternatives']}
                if any(c['arity'] for c in metadata['constructors']):
                    arms={};arm_maps={}
                    for variant in self.families[family]['variants']:
                        arm,arm_map=self.field_case_arm(alternatives[variant],self.rep.variant_for(raw.shape,variant),inner,
                            path+'.variant['+variant+']')
                        arms[variant]=arm;arm_maps[variant]=arm_map
                    selected=self.fresh('chosen')
                    # New factory allocates ONLY the chosen whole-AST thunk. It
                    # retains selected lazy field cursors before parent release.
                    cb.append({'op':'case_fields_i64','out':selected,'in':'$home','family':family,
                               'scrutinee':ready,'arms':arms})
                    cb.append({'op':'drop','value':ready})
                    for ref in inner.values():self.release(ref,cb)
                    cb.append({'op':'return','value':selected})
                    self.codes[code]={'result':'#i64','captures':contracts,'body':cb}
                    self.source_map['field_cases'][code]={'path':path,'family':family,'datatype':metadata['datatype'],**self.rep.source_view(metadata),
                        'variants':self.families[family]['variants'],'fields':self.families[family]['fields'],
                        'arms':arm_maps,'order':['scrutinee','selected-field-capture','chosen-alternative'],
                        'all_alternatives_checked_and_delayed':True,'all_payload_fields_preserved':True,
                        'factory_result_is_new_thunk':True}
                    out=self.fresh();body.append({'op':'thunk','out':out,'in':key,'code':code,'captures':actual})
                    self.close_builder(key,split,body)
                    return Reference(out,'#i64',split)
                arms={};arm_codes={}
                for variant in self.families[family]['variants']:
                    alt=alternatives[variant]
                    branch,branch_code=self.conditional_alternative(alt['body'],inner,'$home',cb,
                        path+'.variant['+variant+']','sum-case-alternative-thunk')
                    arms[variant]=branch.variable;arm_codes[variant]=branch_code
                selected=self.fresh('selected')
                cb.append({'op':'case_i64','out':selected,'in':'$home','family':family,'scrutinee':ready,'arms':arms})
                cb.append({'op':'drop','value':ready})
                for ref in inner.values():self.release(ref,cb)
                cb.append({'op':'return','value':selected})
                self.codes[code]={'result':'#i64','captures':contracts,'body':cb}
                self.source_map['sum_cases'][code]={'path':path,'family':family,'datatype':metadata['datatype'],**self.rep.source_view(metadata),
                    'variants':self.families[family]['variants'],'arm_codes':arm_codes,
                    'order':['scrutinee','selected-alternative'],'all_alternatives_delayed':True}
                out=self.fresh();body.append({'op':'thunk','out':out,'in':key,'code':code,'captures':actual})
                self.close_builder(key,split,body)
                return Reference(out,'#i64',split)
            alt=node["alternatives"][0];metadata=self.rep.records[raw.shape];fields={}
            for i,(n,fieldshape) in enumerate(zip(alt["pattern"]["fields"],metadata["field_shapes"])):
                if n is None:continue
                loan=self.fresh("fieldloan");owned=self.fresh("field")
                cb.extend([{"op":"field","out":loan,"value":ready,"field":"f"+str(i)},
                           {"op":"retain","out":owned,"value":loan},{"op":"end_borrow","value":loan}])
                fields[n["id"]]=Reference(owned,fieldshape,raw.strict)
            cb.append({"op":"drop","value":ready})
            result=self.emit(alt["body"],inner|fields,"$home",cb,path+".alternative")
            for ref in list(inner.values())+list(fields.values()):self.release(ref,cb)
            cb.append({"op":"return","value":result.variable})
            self.codes[code]={"result":self.shape_name(shape),"captures":contracts,"body":cb}
            out=self.fresh();body.append({"op":"thunk","out":out,"in":key,"code":code,"captures":actual})
            self.close_builder(key,split,body)
            return Reference(out,shape,split)
        if tag=="unit":
            key,split=self.allocation(home,[],body,path,"unit")
            out=self.fresh();body.append({"op":"alloc","out":out,"in":key,"layout":"Unit","fields":{}})
            self.close_builder(key,split,body)
            return Reference(out,"Unit",split)
        if tag=="var":
            source=env[node["name"]["id"]]
            out=self.fresh();body.append({"op":"retain","out":out,"value":source.variable})
            return Reference(out,source.shape,source.strict)
        if tag=="lambda":
            shape=self.rep.shape_of(node,{i:r.shape for i,r in env.items()})
            signature=self.shape_name(shape)[1:]
            self.next_function+=1;function="F"+str(self.next_function)
            self.source_map["functions"][function]=path
            capture_ids=sorted(baseline.free_vars(node))
            support=[env[i] for i in capture_ids]
            key,split=self.allocation(home,support,body,path,"closure")
            actual={};contracts={};inner={}
            for i in capture_ids:
                capture=self.fresh("capture");source=env[i]
                # Fresh-group creation proves strict separation above ALL imports.
                # With same-home fallback, only preexisting strict facts survive.
                strict=split or source.strict
                actual[capture]=source.variable
                contracts[capture]={"layout":self.shape_name(source.shape),"relation":"below" if strict else "down"}
                inner[i]=Reference(capture,source.shape,strict)
            parameter=self.fresh("argument")
            # Generic function argument has only A<=P. Never invent A<P.
            inner[node["parameter"]["id"]]=Reference(parameter,shape[0],False)
            function_body=[]
            result=self.emit(node["body"],inner,"$home",function_body,path+".body")
            for source in inner.values():self.release(source,function_body)
            function_body.append({"op":"return","value":result.variable})
            self.functions[function]={"signature":signature,"parameter":parameter,"captures":contracts,"body":function_body}
            out=self.fresh();body.append({"op":"closure","out":out,"in":key,"function":function,"captures":actual})
            self.close_builder(key,split,body)
            return Reference(out,shape,split)
        if tag=="application":
            function=self.operand(node["function"],env,home,body,path+".function")
            argument=self.operand(node["argument"],env,home,body,path+".argument")
            key,split=self.allocation(home,[function,argument],body,path,"application")
            out=self.fresh();self.source_map["applications"][out]=path
            operation="application_borrow" if "loan" in (function.mode,argument.mode) else "application"
            body.append({"op":operation,"out":out,"in":key,"function":function.variable,"argument":argument.variable})
            # Publication creates real owning slots while all exact loan anchors
            # remain live. Only then may temporary loans/owners be discharged.
            self.release(function,body);self.release(argument,body)
            self.close_builder(key,split,body)
            return Reference(out,function.shape[1],split)
        if tag=="let":
            value=self.emit(node["value"],env,home,body,path+".value")
            result=self.emit(node["body"],env | {node["name"]["id"]:value},home,body,path+".body")
            self.release(value,body)
            return result
        raise BridgeError("unsupported planning node")


def plan(envelope,*,groups:bool=False,borrows:bool=False)->dict:
    if type(groups) is not bool or type(borrows) is not bool:raise BridgeError("planning modes must be booleans")
    data=envelope.data();multiple_views=data.get("format")=="mlf-checked-module-export/2"
    representation=(baseline.MultiViewRepresentation if multiple_views else baseline.Representation)(data["representation"])
    shape=representation.shape_of(data["annotated"],{})
    checked=data["checked_type"]
    while checked["tag"]=="forall":checked=checked["body"]
    if representation.type_shape(checked)!=shape:raise BridgeError("checked artifact representation mismatch")
    if shape not in ('Unit','#i64','#bool'):raise BridgeError('bounded execution requires final Unit, Int64 or Bool; recursive records/callables may escape internally')
    emitter=Planner(groups,borrows,representation)
    body=[{"op":"new_root","out":"root","imports":[]}]
    result=emitter.emit(data["annotated"],{},"root",body,"root")
    ready=emitter.fresh("result")
    body.append({"op":"force","out":ready,"value":result.variable})
    if shape=='Unit':body.extend([{"op":"drop","value":ready},{"op":"drop","value":"root"},{"op":"finish"}])
    else:body.extend([{"op":"drop","value":"root"},{"op":"finish_scalar","value":ready}])
    program={"version":7,"families":emitter.families,"layouts":emitter.layouts,"codes":emitter.codes,"signatures":emitter.signatures,
             "functions":emitter.functions,"entry":body}
    encoded=json.dumps(program,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {"program":program,"binding":{"export_sha256":envelope.sha256,
             "candidate_sha256":hashlib.sha256(encoded.encode()).hexdigest(),
             "source_map":emitter.source_map,"allocation_decisions":emitter.decisions,"borrow_sites":emitter.borrow_sites,
             "modes":{"fine_groups":groups,"operand_borrows":borrows},
             "status":"candidate-not-resource-checked","fragment":"checked-module-concrete-family-views-v1" if multiple_views else "checked-single-closed-instance-field-sum-lazy-v6"}}
