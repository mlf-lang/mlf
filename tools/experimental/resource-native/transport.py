"""Strict transport + bounded lowering. This module is NOT an ordinary checker.

A hand-built envelope can test transport/lowering, but is never evidence of a
real CheckedTerm. run_bridge.py owns authentic binary invocation and provenance.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
MAX_BYTES = 1_000_000
MAX_NODES = 10_000
MAX_DEPTH = 100


class BridgeError(ValueError):
    pass


def exact(value: Any, keys: set[str], path: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise BridgeError(f"{path}: schema requires exact keys {sorted(keys)}")
    return value


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise BridgeError(f"{path}: expected Unicode scalar string")
    return value


def integer(value: Any, path: str) -> int:
    if type(value) is not int:
        raise BridgeError(f"{path}: expected integer identity")
    return value


def name(value: Any, path: str) -> int:
    exact(value, {"id", "hint"}, path)
    text(value["hint"], path+".hint")
    return integer(value["id"], path+".id")


def strict_pairs(pairs: list) -> dict:
    result = {}
    for k,v in pairs:
        if k in result:
            raise BridgeError("duplicate JSON object key: "+k)
        result[k] = v
    return result


def bounded(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count=[0]
    count[0]+=1
    if count[0] > MAX_NODES or depth > MAX_DEPTH:
        raise BridgeError("transport exceeds bounded node/depth contract")
    if isinstance(value,dict):
        for k,v in value.items():
            text(k,"key"); bounded(v,depth+1,count)
    elif isinstance(value,list):
        for v in value: bounded(v,depth+1,count)
    elif isinstance(value,str):
        text(value,"string")
    elif type(value) not in (int,bool,type(None)):
        raise BridgeError("non-integral transport number")


def validate_kind(value: Any) -> None:
    if not isinstance(value,dict):raise BridgeError("kind must be an object")
    tag=value.get("tag")
    if tag=="star": exact(value,{"tag"},"kind")
    elif tag=="arrow":
        exact(value,{"tag","from","to"},"kind");validate_kind(value["from"]);validate_kind(value["to"])
    else:raise BridgeError("unknown kind")


def validate_type(value: Any) -> None:
    if not isinstance(value,dict):raise BridgeError("type must be an object")
    tag=value.get("tag")
    if tag=="var":exact(value,{"tag","id"},"type");integer(value["id"],"type.id")
    elif tag=="bottom":exact(value,{"tag"},"type")
    elif tag=="bottom_kind":exact(value,{"tag","kind"},"type");validate_kind(value["kind"])
    elif tag=="arrow":
        exact(value,{"tag","from","to"},"type");validate_type(value["from"]);validate_type(value["to"])
    elif tag=="constructor":
        exact(value,{"tag","name","arguments"},"type");text(value["name"],"type.name")
        if not isinstance(value["arguments"],list):raise BridgeError("type arguments must be a list")
        for a in value["arguments"]:validate_type(a)
    elif tag=="apply":
        exact(value,{"tag","function","argument"},"type");validate_type(value["function"]);validate_type(value["argument"])
    elif tag=="forall":
        exact(value,{"tag","id","bound","body"},"type");integer(value["id"],"type.id")
        validate_type(value["bound"]);validate_type(value["body"])
    else:raise BridgeError("unknown type constructor")


def projection(node, annotated=True):
    if type(node) is not dict:raise BridgeError("runtime node must be object")
    tag=node.get("tag")
    recurse=lambda n:projection(n,annotated)
    if tag in ("unit","var"):
        exact(node,{"tag"} | ({"name"} if tag=="var" else set()),tag)
        if tag=="var":name(node["name"],"var.name")
        return dict(node)
    if tag=="constructor":
        exact(node,{"tag","name"}|({"arguments"} if annotated else set()),tag)
        text(node["name"],"constructor.name")
        if annotated:
            if type(node["arguments"]) is not list:raise BridgeError("constructor arguments must be list")
            for t in node["arguments"]:validate_type(t)
        return {"tag":tag,"name":node["name"]}
    if tag=="lambda":
        exact(node,{"tag","parameter","body"}|({"parameter_type"} if annotated else set()),tag)
        name(node["parameter"],"lambda.parameter")
        if annotated:validate_type(node["parameter_type"])
        return {"tag":tag,"parameter":node["parameter"],"body":recurse(node["body"])}
    if tag=="application":
        exact(node,{"tag","function","argument"},tag)
        return {"tag":tag,"function":recurse(node["function"]),"argument":recurse(node["argument"])}
    if tag=="let":
        exact(node,{"tag","name","value","body"},tag);name(node["name"],"let.name")
        return {"tag":tag,"name":node["name"],"value":recurse(node["value"]),"body":recurse(node["body"])}
    if tag=="letrec":
        exact(node,{"tag","bindings","body"},tag)
        if type(node["bindings"]) is not list or not node["bindings"]:raise BridgeError("empty/invalid recursion bindings")
        bindings=[]
        for b in node["bindings"]:
            exact(b,{"name","value"}|({"type"} if annotated else set()),"recursive binding")
            name(b["name"],"recursive name")
            if annotated:validate_type(b["type"])
            bindings.append({"name":b["name"],"value":recurse(b["value"])})
        return {"tag":tag,"bindings":bindings,"body":recurse(node["body"])}
    if tag=="case":
        exact(node,{"tag","scrutinee","alternatives"}|({"result_type"} if annotated else set()),tag)
        if annotated:validate_type(node["result_type"])
        if type(node["alternatives"]) is not list:raise BridgeError("invalid alternatives")
        alternatives=[]
        for a in node["alternatives"]:
            exact(a,{"pattern","body"},"alternative");p=a["pattern"]
            exact(p,{"constructor","fields"},"pattern");text(p["constructor"],"pattern constructor")
            if type(p["fields"]) is not list:raise BridgeError("invalid pattern fields")
            for n in p["fields"]:
                if n is not None:name(n,"pattern field")
            alternatives.append({"pattern":p,"body":recurse(a["body"])})
        return {"tag":tag,"scrutinee":recurse(node["scrutinee"]),"alternatives":alternatives}
    if annotated and tag=="type_lambda":
        exact(node,{"tag","id","bound","body"},tag);integer(node["id"],"type id");validate_type(node["bound"])
        return recurse(node["body"])
    if annotated and tag=="type_application":
        exact(node,{"tag","value","witness"},tag);text(node["witness"],"witness")
        return recurse(node["value"])
    raise BridgeError("unsupported runtime syntax: "+str(tag))


def annotated_erasure(node):return projection(node,True)
def validate_erased(node):projection(node,False)


@dataclass(frozen=True)
class Envelope:
    """Validated transport only; does not assert that ordinary checking occurred."""
    canonical_json: str
    sha256: str

    def data(self) -> dict:
        return json.loads(self.canonical_json)


def parse_envelope(raw: str, *, manifest: dict | None = None) -> Envelope:
    if len(raw.encode("utf-8")) > MAX_BYTES:raise BridgeError("transport byte bound exceeded")
    try:
        value=json.loads(raw,object_pairs_hook=strict_pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(BridgeError("nonfinite JSON")))
    except (json.JSONDecodeError,RecursionError) as e:
        raise BridgeError("invalid/beyond-depth JSON transport") from e
    bounded(value)
    exact(value,{"format","producer","checked_type","checked_type_pretty","checked_term_pretty", "declaration_bindings","representation","annotated","erased"},"envelope")
    if value["format"]!="mlf-checked-recursion-export/1":raise BridgeError("unsupported export format")
    exact(value["producer"],{"source_commit","dependency_digest"},"producer")
    if manifest is None:manifest=json.loads((BASE/"validation/source-manifest.json").read_text())
    if value["producer"]!={k:manifest[k] for k in ("source_commit","dependency_digest")}:
        raise BridgeError("producer source identity mismatch (matching it is not proof of origin)")
    validate_type(value["checked_type"])
    text(value["checked_type_pretty"],"checked_type_pretty");text(value["checked_term_pretty"],"checked_term_pretty")
    inventory=value["declaration_bindings"]
    if not isinstance(inventory,dict):raise BridgeError("bad declaration inventory")
    if inventory.get("status")=="available":
        exact(inventory,{"status","bindings"},"bindings")
        if not isinstance(inventory["bindings"],list):raise BridgeError("bad binding list")
        for b in inventory["bindings"]:
            exact(b,{"name","type"},"binding");name(b["name"],"binding.name");validate_type(b["type"])
    elif inventory.get("status")=="unavailable":
        exact(inventory,{"status","diagnostic"},"bindings");text(inventory["diagnostic"],"bindings.diagnostic")
    else:raise BridgeError("unknown declaration inventory status")
    representation=value["representation"]
    exact(representation,{"builtin_unit","custom_datatypes"},"representation")
    if representation["builtin_unit"]!={"constructor":"()","datatype":"()","arity":0,"fields":[]}:
        raise BridgeError("invalid original builtin unit metadata")
    integer(representation["builtin_unit"]["arity"],"unit arity")
    Representation(representation)
    validate_erased(value["erased"])
    if annotated_erasure(value["annotated"]) != value["erased"]:
        raise BridgeError("annotated metadata projection differs from actual X.erase transport")
    canonical=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return Envelope(canonical,hashlib.sha256(canonical.encode()).hexdigest())


# Representation compatibility only, never an ordinary-checking replacement.
@dataclass(frozen=True)
class Nominal:
    """Disjoint from builtin Unit and callable tuple shapes, even for data Unit."""
    name: str

Shape = str | tuple | Nominal

def strip(node):
    while node["tag"] in ("type_lambda","type_application"):
        node=node["body"] if node["tag"]=="type_lambda" else node["value"]
    return node


def constructor_spine(node):
    arguments=[];cursor=strip(node)
    while cursor["tag"]=="application":
        arguments.append(cursor["argument"]);cursor=strip(cursor["function"])
    if cursor["tag"]=="constructor":return cursor,list(reversed(arguments))
    return None


def free_vars(node):
    node=strip(node);tag=node["tag"]
    if tag in ("unit","constructor"):return set()
    if tag=="var":return {node["name"]["id"]}
    if tag=="lambda":return free_vars(node["body"])-{node["parameter"]["id"]}
    if tag=="application":return free_vars(node["function"])|free_vars(node["argument"])
    if tag=="let":return free_vars(node["value"])|(free_vars(node["body"])-{node["name"]["id"]})
    if tag=="letrec":
        local={b["name"]["id"] for b in node["bindings"]}
        return (set().union(*(free_vars(b["value"]) for b in node["bindings"]))|free_vars(node["body"]))-local
    if tag=="case":
        answer=free_vars(node["scrutinee"])
        for a in node["alternatives"]:
            answer|=free_vars(a["body"])-{n["id"] for n in a["pattern"]["fields"] if n is not None}
        return answer
    raise BridgeError("unsupported free-variable node")


class Representation:
    def __init__(self,metadata):
        ds=metadata["custom_datatypes"]
        if type(ds) is not list:raise BridgeError("invalid datatype list")
        self.datatypes={};self.constructors={};self.records={}
        for d in ds:
            exact(d,{"datatype","constructor","arity","fields"},"datatype")
            tn=text(d["datatype"],"datatype name");cn=text(d["constructor"],"constructor name")
            if tn=="()" or tn in self.datatypes or cn=="()" or cn in self.constructors:raise BridgeError("duplicate/reserved datatype identity")
            if type(d["fields"]) is not list or integer(d["arity"],"arity")!=len(d["fields"]):raise BridgeError("datatype field arity mismatch")
            for t in d["fields"]:validate_type(t)
            derived=dict(d);derived["shape"]=Nominal(tn);self.datatypes[tn]=derived;self.constructors[cn]=derived;self.records[derived["shape"]]=derived
        for d in self.datatypes.values():d["field_shapes"]=[self.type_shape(t) for t in d["fields"]]

    def type_shape(self,t):
        if t.get("tag")=="constructor" and not t["arguments"]:
            if t["name"]=="()":return "Unit"
            if t["name"] in self.datatypes:return self.datatypes[t["name"]]["shape"]
        if t.get("tag")=="arrow":return (self.type_shape(t["from"]),self.type_shape(t["to"]))
        raise BridgeError("unsupported runtime representation: closed Unit/nominal/arrow types only")

    def shape_of(self,node,env):
        node=strip(node);tag=node["tag"]
        if tag=="unit":return "Unit"
        if tag=="constructor":
            if node["arguments"]:raise BridgeError("polymorphic constructor instantiation unsupported")
            if node["name"] not in self.constructors:raise BridgeError("constructor missing original datatype metadata")
            d=self.constructors[node["name"]];shape=d["shape"]
            for arg in reversed(d["field_shapes"]):shape=(arg,shape)
            return shape
        if tag=="var":
            ident=node["name"]["id"]
            if ident not in env:raise BridgeError("free erased variable")
            return env[ident]
        if tag=="lambda":
            ident=node["parameter"]["id"]
            if ident in env:raise BridgeError("duplicate in-scope binder identity")
            parameter=self.type_shape(node["parameter_type"])
            return (parameter,self.shape_of(node["body"],env|{ident:parameter}))
        if tag=="application":
            f=self.shape_of(node["function"],env);a=self.shape_of(node["argument"],env)
            if type(f) is not tuple or f[0]!=a:raise BridgeError("representation mismatch at application")
            return f[1]
        if tag=="let":
            ident=node["name"]["id"]
            if ident in env:raise BridgeError("duplicate in-scope let identity")
            return self.shape_of(node["body"],env|{ident:self.shape_of(node["value"],env)})
        if tag=="letrec":
            ids=[b["name"]["id"] for b in node["bindings"]]
            if len(set(ids))!=len(ids) or set(ids)&set(env):raise BridgeError("duplicate recursive identity")
            inner=env|{b["name"]["id"]:self.type_shape(b["type"]) for b in node["bindings"]}
            for b in node["bindings"]:
                if self.shape_of(b["value"],inner)!=inner[b["name"]["id"]]:raise BridgeError("recursive representation mismatch")
            return self.shape_of(node["body"],inner)
        if tag=="case":
            shape=self.shape_of(node["scrutinee"],env)
            if shape not in self.records:raise BridgeError("case requires declared single-constructor datatype")
            if len(node["alternatives"])!=1:raise BridgeError("case requires exactly one alternative")
            a=node["alternatives"][0];d=self.records[shape];p=a["pattern"]
            if p["constructor"]!=d["constructor"] or len(p["fields"])!=d["arity"]:raise BridgeError("case metadata mismatch")
            ids=[n["id"] for n in p["fields"] if n is not None]
            if len(set(ids))!=len(ids) or set(ids)&set(env):raise BridgeError("duplicate pattern identity")
            inner=env|{n["id"]:s for n,s in zip(p["fields"],d["field_shapes"]) if n is not None}
            result=self.type_shape(node["result_type"])
            if self.shape_of(a["body"],inner)!=result:raise BridgeError("case result representation mismatch")
            return result
        raise BridgeError("unsupported representation node")
