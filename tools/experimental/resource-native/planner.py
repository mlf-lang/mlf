"""Bounded syntax-directed fine-group and temporary-operand-borrow planning.

Candidate generator only. No evaluator, collector, heap-order oracle, principal
inference, or proof by trace appears in this file. The actual v3 IR checker is
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
        self.source_map={"functions":{},"applications":{},"cases":{},"knots":{}}
        self.layouts={"Unit":{}}
        self.layout_names={meta["shape"]:"D"+str(i) for i,meta in enumerate(self.rep.datatypes.values())}
        for d,meta in self.rep.datatypes.items():
            self.layouts[self.layout_names[meta["shape"]]]={"f"+str(i):self.shape_name(t) for i,t in enumerate(meta["field_shapes"])}
        self.groups=groups
        self.borrows=borrows
        self.decisions=[]
        self.borrow_sites=[]

    def fresh(self,prefix="v"):
        self.next_var+=1
        return prefix+str(self.next_var)

    def shape_name(self,shape):
        if shape=="Unit":return "Unit"
        if isinstance(shape,baseline.Nominal):return self.layout_names[shape]
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

    def emit(self,node:dict,env:dict[int,Reference],home:str,body:list,path:str)->Reference:
        node=baseline.strip(node);tag=node["tag"]
        spine=baseline.constructor_spine(node)
        if spine:
            head,args=spine;metadata=self.rep.constructors.get(head["name"])
            if metadata is None or len(args)!=metadata["arity"]:
                raise BridgeError("custom constructors must be fully saturated")
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
    data=envelope.data();representation=baseline.Representation(data["representation"])
    shape=representation.shape_of(data["annotated"],{})
    checked=data["checked_type"]
    while checked["tag"]=="forall":checked=checked["body"]
    if representation.type_shape(checked)!=shape:raise BridgeError("checked artifact representation mismatch")
    if shape!="Unit":raise BridgeError("bounded execution requires final Unit; recursive records/callables may escape internally")
    emitter=Planner(groups,borrows,representation)
    body=[{"op":"new_root","out":"root","imports":[]}]
    result=emitter.emit(data["annotated"],{},"root",body,"root")
    ready=emitter.fresh("result")
    body.extend([{"op":"force","out":ready,"value":result.variable},{"op":"drop","value":ready},
                 {"op":"drop","value":"root"},{"op":"finish"}])
    program={"version":3,"layouts":emitter.layouts,"codes":emitter.codes,"signatures":emitter.signatures,
             "functions":emitter.functions,"entry":body}
    encoded=json.dumps(program,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {"program":program,"binding":{"export_sha256":envelope.sha256,
             "candidate_sha256":hashlib.sha256(encoded.encode()).hexdigest(),
             "source_map":emitter.source_map,"allocation_decisions":emitter.decisions,"borrow_sites":emitter.borrow_sites,
             "modes":{"fine_groups":groups,"operand_borrows":borrows},
             "status":"candidate-not-resource-checked","fragment":"closed-monomorphic-single-constructor-letrec-lazy-v1"}}
