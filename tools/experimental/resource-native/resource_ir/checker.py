"""All-path resource checking for the deliberately closed JSON IR.

No heap execution, trace, runtime group identity, or callback oracle is used here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any

VERSION = "resource-ir-field-sum/1"
SCALAR_SHAPES = {'#i64', '#bool'}
SCALAR_PRIMITIVES = {'addInt': '#i64', 'subInt': '#i64', 'mulInt': '#i64',
                     'eqInt': '#bool', 'ltInt': '#bool'}


class CheckError(ValueError):
    def __init__(self, path: str, code: str, message: str):
        self.path, self.code, self.message = path, code, message
        super().__init__(f"{path}: {code}: {message}")


def fail(path: str, code: str, message: str) -> None:
    raise CheckError(path, code, message)


def object_keys(value: Any, keys: set[str], path: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else type(value).__name__
        fail(path, "SCHEMA", f"expected exact keys {sorted(keys)}, got {actual}")
    return value


def name(value: Any, path: str, *, variable: bool = False) -> str:
    if not isinstance(value, str) or not value or (variable and value.startswith("$")):
        fail(path, "SCHEMA", "expected a nonempty name (user variables cannot start with '$')")
    return value


def sequence(value: Any, path: str) -> list:
    if not isinstance(value, list):
        fail(path, "SCHEMA", "expected a list")
    return value


@dataclass(frozen=True)
class Value:
    group: int
    kind: str  # key / ref
    mode: str = "own"  # own / loan
    layout: str | None = None
    ready: bool = False
    anchor: str | None = None
    ticket: bool = False
    identity: int | None = None  # rigid object identity; Once permission follows this object


class Order:
    """Symbolic <= facts; existential names need not denote distinct groups.

    An edge upper->lower can be non-strict. Only a path containing a strict
    edge proves strict descent. Distinct symbolic names alone prove nothing.
    """
    def __init__(self) -> None:
        self.edges: list[tuple[int, int, bool]] = []

    def copy(self) -> Order:
        other = Order()
        other.edges = self.edges.copy()
        return other

    def add(self, upper: int, lower: int, strict: bool = False) -> None:
        self.edges.append((upper, lower, strict))

    def below(self, lower: int, upper: int, *, strict: bool = False) -> bool:
        todo = [(upper, False)]
        seen = set()
        while todo:
            current, has_strict = todo.pop()
            if (current, has_strict) in seen:
                continue
            seen.add((current, has_strict))
            if current == lower and (has_strict or not strict):
                return True
            todo.extend((b, has_strict or s) for a, b, s in self.edges if a == current)
        return False


@dataclass
class State:
    values: dict[str, Value]
    used: set[str]
    order: Order
    home: int | None
    result_layout: str | None
    require_ready: bool = False
    finish_allowed: bool = False
    result_identity: int | None = None

    def copy(self) -> State:
        return State(self.values.copy(), self.used.copy(), self.order.copy(), self.home,
                     self.result_layout, self.require_ready, self.finish_allowed, self.result_identity)


@dataclass(frozen=True)
class CheckedProgram:
    """Immutable snapshot. Public execution rechecks the decoded snapshot.

    A hash binds diagnostics to the exact JSON, not a production CheckedTerm.
    """
    canonical_json: str
    sha256: str
    checked_code_bodies: int
    checked_operations: int
    checked_branches: int
    checked_function_bodies: int = 0

    def data(self) -> dict:
        return json.loads(self.canonical_json)

    def report(self) -> dict:
        return {"status": "accepted", "checker": VERSION, "sha256": self.sha256,
                "checked_code_bodies": self.checked_code_bodies,
                "checked_operations": self.checked_operations,
                "checked_branch_arms": self.checked_branches,
                "checked_function_bodies": self.checked_function_bodies,
                "scope": "explicit resource IR only; no source/MLF integration proof"}


class Checker:
    def __init__(self, program: Any):
        if not isinstance(program, dict) or type(program.get("version")) is not int or program["version"] not in (1, 2, 3, 4, 5, 6, 7):
            fail("program.version", "VERSION", "only resource IR versions 1 through 7 are supported")
        self.v2 = program["version"] >= 2
        self.v3 = program["version"] >= 3
        self.v4 = program["version"] >= 4
        self.v5 = program["version"] >= 5
        self.v6 = program["version"] >= 6
        self.v7 = program["version"] == 7
        keys = {"version", "layouts", "codes", "entry"} | ({"signatures", "functions"} if self.v2 else set())
        if self.v6: keys.add("families")
        self.program = object_keys(program, keys, "program")
        self.families = program.get("families", {})
        self.layouts = program["layouts"]
        self.codes = program["codes"]
        self.signatures = program.get("signatures", {})
        self.functions = program.get("functions", {})
        self.next_group = 0
        self.next_identity = 0
        self.ops = 0
        self.branches = 0

    def fresh(self) -> int:
        self.next_group += 1
        return self.next_group

    def identity(self) -> int:
        self.next_identity += 1
        return self.next_identity

    def signature(self, shape: str) -> dict | None:
        return self.signatures[shape[1:]] if self.v2 and shape.startswith("@") else None

    def once(self, shape: str | None) -> bool:
        return bool(shape and self.signature(shape) and self.signature(shape)["protocol"] == "once")

    def layout(self, value: Any, path: str) -> str:
        value = name(value, path)
        if value.startswith('%'):
            if not self.v6 or value[1:] not in self.families:
                fail(path, 'FAMILY', 'unknown or version-ineligible nominal family shape')
        elif value.startswith('#'):
            if not self.v4 or value not in SCALAR_SHAPES:
                fail(path, 'LAYOUT', 'unknown or version-ineligible intrinsic scalar shape')
        elif value.startswith("@") and self.v2:
            if value[1:] not in self.signatures:
                fail(path, "SIGNATURE", f"unknown callable signature {value!r}")
        elif value not in self.layouts:
            fail(path, "LAYOUT", f"unknown layout {value!r}")
        return value

    def family(self, value: Any, path: str) -> list[str]:
        value = name(value, path)
        if value not in self.families:
            fail(path, 'FAMILY', 'unknown nominal family')
        return self.families[value]['variants']

    def variant_fields(self, family: str, variant: str) -> list[str]:
        return self.families[family].get('fields', {}).get(variant, [])

    def schemas(self) -> None:
        if not isinstance(self.families, dict) or len(self.families) > 64:
            fail('families', 'FAMILY', 'expected at most 64 finite nominal families')
        for family, spec in self.families.items():
            name(family, 'families')
            if family.startswith(('@', '#', '%')):
                fail('families', 'FAMILY', 'family names cannot occupy reserved namespaces')
            object_keys(spec, {'variants', 'fields'} if self.v7 else {'variants'}, 'families.' + family)
            variants = sequence(spec['variants'], 'families.' + family + '.variants')
            if not 1 <= len(variants) <= 64:
                fail('families.' + family, 'FAMILY', 'a family needs 1 to 64 variants')
            for variant in variants: name(variant, 'families.' + family + '.variants')
            if len(set(variants)) != len(variants):
                fail('families.' + family, 'FAMILY', 'variant names must be unique within their family')
        if not isinstance(self.layouts, dict) or not self.layouts:
            fail("layouts", "SCHEMA", "expected nonempty layout object")
        if not isinstance(self.signatures, dict) or not isinstance(self.functions, dict):
            fail("program", "SCHEMA", "signatures and functions must be objects")
        if self.v7:
            for family, spec in self.families.items():
                fields = spec['fields']
                if not isinstance(fields, dict) or set(fields) != set(spec['variants']):
                    fail('families.' + family, 'FIELDS', 'complete variant field inventory required')
                for variant in spec['variants']:
                    types = sequence(fields[variant], 'families.' + family + '.fields.' + variant)
                    if len(types) > 32:
                        fail('families.' + family, 'FIELDS', 'at most 32 fields per variant')
                    for shape in types:
                        shape = self.layout(shape, 'families.' + family + '.fields.' + variant)
                        if shape not in SCALAR_SHAPES and not shape.startswith('%'):
                            fail('families.' + family, 'FIELD_SHAPE', 'sum fields admit only intrinsic Int/Bool or registered sum')
        for signature, spec in self.signatures.items():
            name(signature, "signatures")
            if signature.startswith(("@", "#", "%")):
                fail("signatures", "SCHEMA", "signature names cannot start with @, # or %")
            object_keys(spec, {"argument", "result", "protocol", "result_identity"}, f"signatures.{signature}")
            if spec["protocol"] not in ("repeat", "once") or spec["result_identity"] not in ("argument", "unknown"):
                fail(f"signatures.{signature}", "SCHEMA", "invalid callable protocol/identity contract")
        for signature, spec in self.signatures.items():
            self.layout(spec["argument"], f"signatures.{signature}.argument")
            self.layout(spec["result"], f"signatures.{signature}.result")
            if spec["result_identity"] == "argument" and spec["argument"] != spec["result"]:
                fail(f"signatures.{signature}", "IDENTITY", "argument-identity result must have the same shape")
        if not isinstance(self.layouts, dict) or not self.layouts:
            fail("layouts", "SCHEMA", "expected nonempty layout object")
        for layout, fields in self.layouts.items():
            name(layout, "layouts")
            if layout.startswith(('#', '%')) or (self.v2 and layout.startswith("@")):
                fail("layouts", "SCHEMA", "data layout names cannot use reserved @, # or % namespaces")
            if not isinstance(fields, dict):
                fail(f"layouts.{layout}", "SCHEMA", "fields must be an object")
            for field, target in fields.items():
                name(field, f"layouts.{layout}")
                self.layout(target, f"layouts.{layout}.{field}")
                if self.once(target):
                    fail(f"layouts.{layout}.{field}", "ONCE_CARRIER", "shared data fields cannot carry Once permission")
        if not isinstance(self.codes, dict):
            fail("codes", "SCHEMA", "expected code object")
        for code, spec in self.codes.items():
            name(code, "codes")
            path = f"codes.{code}"
            object_keys(spec, {"result", "captures", "body"}, path)
            self.layout(spec["result"], path + ".result")
            if self.once(spec["result"]):
                fail(path, "ONCE_CARRIER", "shared thunks cannot memoize Once results")
            if not isinstance(spec["captures"], dict):
                fail(path + ".captures", "SCHEMA", "expected capture object")
            for capture, contract in spec["captures"].items():
                name(capture, path + ".captures", variable=True)
                object_keys(contract, {"layout", "relation"}, path + f".captures.{capture}")
                self.layout(contract["layout"], path + f".captures.{capture}.layout")
                if self.once(contract["layout"]):
                    fail(path, "ONCE_CARRIER", "thunk capture of Once is outside this bounded contract")
                if contract["relation"] not in ("same", "down", "below"):
                    fail(path, "SCHEMA", "capture relation must be same, down, or below")
            sequence(spec["body"], path + ".body")
        for function, spec in self.functions.items():
            path = f"functions.{function}"
            name(function, "functions")
            object_keys(spec, {"signature", "parameter", "captures", "body"}, path)
            signature = name(spec["signature"], path + ".signature")
            if signature not in self.signatures:
                fail(path, "SIGNATURE", "function references an undeclared signature")
            parameter = name(spec["parameter"], path + ".parameter", variable=True)
            if not isinstance(spec["captures"], dict) or parameter in spec["captures"]:
                fail(path, "SCHEMA", "captures must be an object and cannot shadow the parameter")
            for capture, contract in spec["captures"].items():
                name(capture, path + ".captures", variable=True)
                object_keys(contract, {"layout", "relation"}, path + f".captures.{capture}")
                self.layout(contract["layout"], path + f".captures.{capture}.layout")
                if contract["relation"] not in ("same", "down", "below"):
                    fail(path, "SCHEMA", "capture relation must be same, down, or below")
                if self.once(contract["layout"]) and self.signatures[signature]["protocol"] != "once":
                    fail(path, "ONCE_CARRIER", "Repeat environments cannot duplicate a Once capture")
            sequence(spec["body"], path + ".body")

    def get(self, state: State, variable: Any, path: str, *, kind: str | None = None,
            own: bool = False) -> Value:
        variable = name(variable, path)
        if variable not in state.values:
            fail(path, "NOT_LIVE", f"{variable!r} has no live capability")
        value = state.values[variable]
        if kind and value.kind != kind:
            fail(path, "KIND", f"{variable!r} must be a {kind}")
        if own and value.mode != "own":
            fail(path, "OWNERSHIP", f"{variable!r} needs an independent owner, not a loan")
        if value.mode == "loan" and value.anchor != "$activation":
            if value.anchor not in state.values or state.values[value.anchor].mode != "own":
                fail(path, "ANCHOR", "loan's exact owner anchor is not live")
        return value

    def bind(self, state: State, variable: Any, value: Value, path: str) -> None:
        variable = name(variable, path, variable=True)
        if variable in state.used:
            fail(path, "SSA", f"{variable!r} cannot be rebound, even after consumption")
        state.used.add(variable)
        state.values[variable] = value

    def consume(self, state: State, variable: Any, path: str, *, allow_ticket: bool = False) -> Value:
        value = self.get(state, variable, path, own=True)
        loans = [n for n, v in state.values.items() if v.mode == "loan" and v.anchor == variable]
        if loans:
            fail(path, "LIVE_LOAN", f"cannot consume exact anchor {variable!r}; live loans: {loans}")
        if value.ticket and not allow_ticket:
            fail(path, "UNFILLED_HOLE", "construction ticket must be filled before consuming this owner")
        del state.values[variable]
        return value

    def authority(self, state: State, variable: Any, path: str) -> Value:
        value = self.get(state, variable, path)
        if value.mode != "own" and variable != "$home":
            fail(path, "AUTHORITY", "allocation/order premise needs an owner or activation-backed $home")
        return value

    def slots(self, state: State, group: int, supplied: Any, expected: dict[str, str], path: str,
              *, allow_once: bool = False) -> None:
        if not isinstance(supplied, dict) or set(supplied) != set(expected):
            fail(path, "FIELDS", f"expected exactly {sorted(expected)}")
        for field, layout in expected.items():
            value = self.get(state, supplied[field], path + f".{field}", kind="ref", own=True)
            if value.layout != layout:
                fail(path, "LAYOUT", f"field {field} expects {layout}, got {value.layout}")
            if self.once(value.layout) and not allow_once:
                fail(path, "ONCE_CARRIER", "this shared carrier cannot store Once permission")
            if not state.order.below(value.group, group):
                fail(path, "UPWARD_SUPPORT", f"field/capture {field} is not proven same-group or downward")

    def finish(self, state: State, path: str) -> None:
        remaining = [n for n in state.values if n != "$home"]
        if remaining:
            fail(path, "UNDISCHARGED", f"all local owners/loans/tickets must be discharged: {remaining}")

    def block(self, body: Any, state: State, path: str) -> None:
        body = sequence(body, path)
        if not body:
            fail(path, "TERMINAL", "block needs return, finish, or terminal choose")
        for index, instruction in enumerate(body):
            p = f"{path}[{index}]"
            if not isinstance(instruction, dict) or not isinstance(instruction.get("op"), str):
                fail(p, "SCHEMA", "instruction must have a string op")
            op = instruction["op"]
            schemas = {
                "new_root": {"out", "imports"}, "new_below": {"out", "ceiling", "imports"},
                "alloc": {"out", "in", "layout", "fields"}, "thunk": {"out", "in", "code", "captures"},
                "hole": {"out", "in", "layout"}, "fill": {"hole", "value"},
                "borrow": {"out", "value"}, "end_borrow": {"value"}, "retain": {"out", "value"},
                "drop": {"value"}, "field": {"out", "value", "field"}, "force": {"out", "value"},
                "loop": {"out", "cursor", "count", "as", "body"},
                "choose": {"condition", "then", "else"}, "return": {"value"}, "finish": set(),
            }
            if self.v2:
                schemas.update({"closure": {"out", "in", "function", "captures"},
                                "call": {"out", "in", "function", "argument"},
                                "application": {"out", "in", "function", "argument"}})
            if self.v3:
                schemas["application_borrow"] = {"out", "in", "function", "argument"}
            if self.v4:
                schemas.update({'scalar': {'out', 'in', 'kind', 'value'},
                                'prim2': {'out', 'in', 'primitive', 'left', 'right'},
                                'finish_scalar': {'value'}})
            if self.v5:
                schemas['select_i64'] = {'out', 'in', 'condition', 'then', 'else'}
            if self.v6:
                schemas.update({'construct_nullary': {'out', 'in', 'family', 'variant'},
                                'case_i64': {'out', 'in', 'family', 'scrutinee', 'arms'}})
            if self.v7:
                schemas.update({'construct_sum': {'out', 'in', 'family', 'variant', 'fields'},
                                'case_fields_i64': {'out', 'in', 'family', 'scrutinee', 'arms'}})
            if op not in schemas:
                fail(p, "UNSUPPORTED", f"unsupported operation {op!r}")
            object_keys(instruction, {"op"} | schemas[op], p)
            self.ops += 1
            i = instruction
            terminal = op in ("return", "finish", "finish_scalar", "choose")
            if terminal and index != len(body) - 1:
                fail(p, "TERMINAL", "instructions after terminal are not allowed")
            if op in ("new_root", "new_below"):
                imports = sequence(i["imports"], p + ".imports")
                imported = [self.authority(state, x, p + ".imports") for x in imports]
                if op == "new_below":
                    ceiling = self.authority(state, i["ceiling"], p + ".ceiling")
                    if any(not state.order.below(v.group, ceiling.group, strict=True) for v in imported):
                        fail(p, "STRICT_IMPORT", "each import must be strictly below the ceiling; Down is insufficient")
                group = self.fresh()
                if op == "new_below":
                    state.order.add(ceiling.group, group, True)
                for value in imported:
                    state.order.add(group, value.group, True)
                self.bind(state, i["out"], Value(group, "key"), p)
            elif op == 'scalar':
                authority = self.authority(state, i['in'], p + '.in')
                if i['kind'] not in ('i64', 'bool'):
                    fail(p, 'SCALAR_KIND', 'only exact i64 and bool scalar kinds are supported')
                if i['kind'] == 'i64':
                    if type(i['value']) is not int or not -(1 << 63) <= i['value'] < (1 << 63):
                        fail(p, 'SCALAR_VALUE', 'i64 literal must be a canonical signed 64-bit JSON integer')
                elif type(i['value']) is not bool:
                    fail(p, 'SCALAR_VALUE', 'bool literal must be a JSON boolean')
                self.bind(state, i['out'], Value(authority.group, 'ref', layout='#' + i['kind'],
                                               ready=True, identity=self.identity()), p)
            elif op == 'prim2':
                authority = self.authority(state, i['in'], p + '.in')
                primitive = name(i['primitive'], p + '.primitive')
                if primitive not in SCALAR_PRIMITIVES:
                    fail(p, 'PRIMITIVE', 'primitive is outside the exact five-operation scalar contract')
                for key in ('left', 'right'):
                    operand = self.get(state, i[key], p + '.' + key, kind='ref', own=True)
                    if operand.layout != '#i64':
                        fail(p, 'LAYOUT', 'scalar binary primitive requires intrinsic i64 operands')
                    if not operand.ready:
                        fail(p, 'DEMAND', 'scalar primitive operands must be explicitly forced/ready')
                self.bind(state, i['out'], Value(authority.group, 'ref', layout=SCALAR_PRIMITIVES[primitive],
                                               ready=True, identity=self.identity()), p)
            elif op in ('construct_nullary', 'construct_sum'):
                authority = self.authority(state, i['in'], p + '.in')
                variants = self.family(i['family'], p + '.family')
                variant = name(i['variant'], p + '.variant')
                if variant not in variants:
                    fail(p, 'VARIANT', 'constructor variant is not registered in this family')
                types = self.variant_fields(i['family'], variant)
                supplied = sequence(i['fields'], p + '.fields') if op == 'construct_sum' else []
                if len(supplied) != len(types):
                    fail(p, 'ARITY', 'constructor must supply the full declared field vector')
                for index, (variable, shape) in enumerate(zip(supplied, types)):
                    field = self.get(state, variable, p + f'.fields[{index}]', kind='ref', own=True)
                    if field.layout != shape: fail(p, 'LAYOUT', 'constructor field has wrong exact shape')
                    if not state.order.below(field.group, authority.group):
                        fail(p, 'UPWARD_SUPPORT', 'constructor field not proven Down(authority)')
                self.bind(state, i['out'], Value(authority.group, 'ref', layout='%' + i['family'],
                                               ready=True, identity=self.identity()), p)
            elif op == 'case_fields_i64':
                authority = self.authority(state, i['in'], p + '.in')
                variants = self.family(i['family'], p + '.family')
                scrutinee = self.get(state, i['scrutinee'], p + '.scrutinee', kind='ref', own=True)
                if scrutinee.layout != '%' + i['family']:
                    fail(p, 'FAMILY', 'factory scrutinee requires exact declared family')
                if not scrutinee.ready: fail(p, 'DEMAND', 'factory needs explicitly forced/ready parent')
                if not state.order.below(scrutinee.group, authority.group):
                    fail(p, 'UPWARD_SUPPORT', 'parent is not proven Down(factory authority)')
                arms = i['arms']
                if not isinstance(arms, dict) or set(arms) != set(variants):
                    fail(p, 'ARMS', 'factory needs exactly every declared variant arm')
                for variant in variants:
                    arm_path = p + '.arms.' + variant
                    arm = object_keys(arms[variant], {'code', 'captures'}, arm_path)
                    code = name(arm['code'], arm_path + '.code')
                    if code not in self.codes or self.codes[code]['result'] != '#i64':
                        fail(arm_path, 'FACTORY', 'factory arm must name checked Int-result thunk code')
                    expected = self.codes[code]['captures']; supplied = arm['captures']
                    if not isinstance(supplied, dict) or set(supplied) != set(expected):
                        fail(arm_path, 'CAPTURES', 'factory capture names must match thunk signature exactly')
                    if len(supplied) > 64: fail(arm_path, 'CAPTURE_LIMIT', 'at most 64 captures per arm')
                    field_count = external_count = 0
                    for capture in sorted(expected):
                        binding = supplied[capture]; contract = expected[capture]
                        if not isinstance(binding, dict): fail(arm_path, 'CAPTURE_BINDING', 'typed capture binding required')
                        if binding.get('kind') == 'field':
                            object_keys(binding, {'kind', 'index'}, arm_path + '.' + capture)
                            index = binding['index']; fields = self.variant_fields(i['family'], variant)
                            if type(index) is not int or not 0 <= index < len(fields):
                                fail(arm_path, 'FIELD_INDEX', 'capture field index outside complete variant vector')
                            if contract['layout'] != fields[index]: fail(arm_path, 'LAYOUT', 'field capture shape differs')
                            if contract['relation'] != 'down':
                                fail(arm_path, 'CAPTURE_RELATION', 'field capture proves Down only, never same/strict')
                            field_count += 1
                        elif binding.get('kind') == 'external':
                            object_keys(binding, {'kind', 'value'}, arm_path + '.' + capture)
                            value = self.get(state, binding['value'], arm_path + '.' + capture, kind='ref', own=True)
                            if value.layout != contract['layout']: fail(arm_path, 'LAYOUT', 'external capture shape differs')
                            if not state.order.below(value.group, authority.group):
                                fail(arm_path, 'UPWARD_SUPPORT', 'external capture not proven Down(authority)')
                            if contract['relation'] == 'same' and value.group != authority.group:
                                fail(arm_path, 'CAPTURE_RELATION', 'same external capture needs exact group proof')
                            if contract['relation'] == 'below' and not state.order.below(value.group, authority.group, strict=True):
                                fail(arm_path, 'CAPTURE_RELATION', 'strict external capture needs strict proof')
                            external_count += 1
                        else: fail(arm_path, 'CAPTURE_BINDING', 'unknown factory capture binding kind')
                    if field_count > 32 or external_count > 32:
                        fail(arm_path, 'CAPTURE_LIMIT', 'at most 32 field and 32 external bindings per arm')
                group = self.fresh(); state.order.add(authority.group, group)
                self.bind(state, i['out'], Value(group, 'ref', layout='#i64', identity=self.identity()), p)
            elif op == 'case_i64':
                authority = self.authority(state, i['in'], p + '.in')
                variants = self.family(i['family'], p + '.family')
                if any(self.variant_fields(i['family'], v) for v in variants):
                    fail(p, 'FACTORY', 'field-bearing families require case_fields_i64')
                scrutinee = self.get(state, i['scrutinee'], p + '.scrutinee', kind='ref', own=True)
                if scrutinee.layout != '%' + i['family']:
                    fail(p, 'FAMILY', 'case scrutinee must have the exact declared nominal family')
                if not scrutinee.ready:
                    fail(p, 'DEMAND', 'case scrutinee must be explicitly forced/ready')
                arms = i['arms']
                if not isinstance(arms, dict) or set(arms) != set(variants):
                    fail(p, 'ARMS', 'case requires exactly every declared constructor, no default')
                variables = [name(arms[v], p + '.arms.' + v) for v in variants]
                if len(set(variables)) != len(variables) or i['in'] in variables:
                    fail(p, 'OWNERSHIP', 'case consumes independent branch capabilities, not its authority')
                for variable in variables:
                    value = self.get(state, variable, p + '.arms', kind='ref', own=True)
                    if value.layout != '#i64':
                        fail(p, 'LAYOUT', 'case alternatives must be intrinsic Int cursors')
                    if not state.order.below(value.group, authority.group):
                        fail(p, 'UPWARD_SUPPORT', 'case alternative is not proven Down(authority)')
                for variable in variables: self.consume(state, variable, p + '.arms')
                group = self.fresh(); state.order.add(authority.group, group)
                self.bind(state, i['out'], Value(group, 'ref', layout='#i64'), p)
            elif op == 'select_i64':
                authority = self.authority(state, i['in'], p + '.in')
                condition = self.get(state, i['condition'], p + '.condition', kind='ref', own=True)
                if condition.layout != '#bool':
                    fail(p, 'LAYOUT', 'Int selection requires intrinsic Bool condition')
                if not condition.ready:
                    fail(p, 'DEMAND', 'selection condition must be explicitly forced/ready')
                if i['then'] == i['else'] or i['in'] in (i['then'], i['else']):
                    fail(p, 'OWNERSHIP', 'selection consumes two distinct branch capabilities, not its authority')
                for key in ('then', 'else'):
                    alternative = self.get(state, i[key], p + '.' + key, kind='ref', own=True)
                    if alternative.layout != '#i64':
                        fail(p, 'LAYOUT', 'selection alternatives must both have intrinsic Int shape')
                    if not state.order.below(alternative.group, authority.group):
                        fail(p, 'UPWARD_SUPPORT', 'selection alternative is not proven Down(authority)')
                self.consume(state, i['then'], p + '.then')
                self.consume(state, i['else'], p + '.else')
                group = self.fresh()
                state.order.add(authority.group, group)
                # Abstract selected group, not physical allocation; neither readiness
                # nor a specific alternative's symbolic identity is established.
                self.bind(state, i['out'], Value(group, 'ref', layout='#i64'), p)
            elif op in ("alloc", "thunk", "hole", "closure"):
                authority = self.authority(state, i["in"], p + ".in")
                if op in ("thunk", "closure"):
                    code = name(i["code"] if op == "thunk" else i["function"], p + ".code")
                    definitions = self.codes if op == "thunk" else self.functions
                    if code not in definitions:
                        fail(p, "UNKNOWN_CODE", "all callback bodies must be present and checked")
                    spec = definitions[code]
                    expected = {n: c["layout"] for n, c in spec["captures"].items()}
                    layout = spec["result"] if op == "thunk" else "@" + spec["signature"]
                    self.slots(state, authority.group, i["captures"], expected, p + ".captures",
                               allow_once=op == "closure" and self.once(layout))
                    for capture, contract in spec["captures"].items():
                        value = self.get(state, i["captures"][capture], p)
                        relation = contract["relation"]
                        if relation == "same" and value.group != authority.group:
                            fail(p, "CAPTURE_RELATION", "same-group capture needs identity proof, not merely Down")
                        if relation == "below" and not state.order.below(value.group, authority.group, strict=True):
                            fail(p, "CAPTURE_RELATION", "strict capture relation is not established")
                    for variable in i["captures"].values():
                        if self.once(self.get(state, variable, p).layout):
                            self.consume(state, variable, p)
                else:
                    layout = self.layout(i["layout"], p + ".layout")
                    if op == "hole" and self.once(layout):
                        fail(p, "ONCE_CARRIER", "Once holes/fill are unsupported")
                    if op == "alloc":
                        if layout not in self.layouts:
                            fail(p, "KIND", "callables require checked closure allocation")
                        self.slots(state, authority.group, i["fields"], self.layouts[layout], p + ".fields")
                self.bind(state, i["out"], Value(authority.group, "ref", layout=layout,
                                                ready=op in ("alloc", "closure"), ticket=op == "hole",
                                                identity=self.identity()), p)
            elif op in ("call", "application", "application_borrow"):
                authority = self.authority(state, i["in"], p + ".in")
                borrowed_publication = op == "application_borrow"
                callee = self.get(state, i["function"], p + ".function", kind="ref", own=not borrowed_publication)
                argument = self.get(state, i["argument"], p + ".argument", kind="ref", own=not borrowed_publication)
                signature = self.signature(callee.layout)
                if signature is None:
                    fail(p, "CALLABLE", "call/application needs a declared callable shape")
                if borrowed_publication and (signature["protocol"] != "repeat" or self.once(argument.layout)
                                             or self.once(signature["result"])):
                    fail(p, "BORROW_PROTOCOL", "borrowed publication requires a Repeat callee and shareable argument/result")
                if op == "call" and not callee.ready:
                    fail(p, "DEMAND", "direct call needs a ready callable; Force it explicitly")
                if argument.layout != signature["argument"]:
                    fail(p, "LAYOUT", "call argument does not match callable signature")
                if not state.order.below(callee.group, authority.group) or not state.order.below(argument.group, authority.group):
                    fail(p, "CALL_CEILING", "callee and argument must be downward from caller/application ceiling")
                if op in ("application", "application_borrow"):
                    if self.once(signature["result"]):
                        fail(p, "ONCE_CARRIER", "shared applications cannot memoize Once results")
                    # Shareable inputs are retained; affine permissions are moved.
                    for variable, value in ((i["function"], callee), (i["argument"], argument)):
                        if self.once(value.layout):
                            self.consume(state, variable, p)
                    result = Value(authority.group, "ref", layout=signature["result"], identity=self.identity())
                else:
                    self.consume(state, i["function"], p)
                    self.consume(state, i["argument"], p)
                    if signature["result_identity"] == "argument":
                        result = replace(argument, ticket=False)
                    else:
                        group = self.fresh()
                        state.order.add(authority.group, group)
                        result = Value(group, "ref", layout=signature["result"],
                                       ready=self.once(signature["result"]), identity=self.identity())
                self.bind(state, i["out"], result, p)
            elif op == "fill":
                hole = self.get(state, i["hole"], p, kind="ref", own=True)
                target = self.get(state, i["value"], p, kind="ref", own=True)
                if not hole.ticket:
                    fail(p, "FILL_TICKET", "fill needs the original unspent construction ticket")
                if target.layout != hole.layout:
                    fail(p, "LAYOUT", "raw fill target has the wrong layout")
                if not state.order.below(target.group, hole.group):
                    fail(p, "UPWARD_FILL", "raw fill target must be same-group or downward, even before Force")
                state.values[i["hole"]] = replace(hole, ticket=False)
            elif op == "borrow":
                value = self.get(state, i["value"], p, kind="ref", own=True)
                self.bind(state, i["out"], replace(value, mode="loan", anchor=i["value"], ticket=False), p)
            elif op == "end_borrow":
                value = self.get(state, i["value"], p)
                if value.mode != "loan" or i["value"] == "$home":
                    fail(p, "BORROW", "end_borrow needs a local loan")
                del state.values[i["value"]]
            elif op == "retain":
                value = self.get(state, i["value"], p, kind="ref")
                if self.once(value.layout):
                    fail(p, "ONCE_DUP", "retain/loan promotion cannot copy Once call permission")
                self.bind(state, i["out"], replace(value, mode="own", anchor=None, ticket=False), p)
            elif op == "drop":
                self.consume(state, i["value"], p)
            elif op == "field":
                value = self.get(state, i["value"], p, kind="ref", own=True)
                if not value.ready:
                    fail(p, "DEMAND", "field access requires an explicitly forced/ready host")
                if value.layout not in self.layouts:
                    fail(p, "KIND", "callable environments are not publicly projectable data")
                field = name(i["field"], p + ".field")
                if field not in self.layouts[value.layout]:
                    fail(p, "FIELDS", f"unknown field {field!r}")
                group = self.fresh()
                state.order.add(value.group, group)
                self.bind(state, i["out"], Value(group, "ref", mode="loan",
                          layout=self.layouts[value.layout][field], anchor=i["value"], identity=self.identity()), p)
            elif op == "force":
                value = self.get(state, i["value"], p, kind="ref", own=True)
                if self.once(value.layout):
                    fail(p, "ONCE_CARRIER", "Once values are ready direct-call values, never forced/memoized")
                self.consume(state, i["value"], p)
                group = self.fresh()
                state.order.add(value.group, group)
                self.bind(state, i["out"], Value(group, "ref", layout=value.layout, ready=True, identity=self.identity()), p)
            elif op == "loop":
                cursor = self.get(state, i["cursor"], p, kind="ref", own=True)
                if self.once(cursor.layout):
                    fail(p, "ONCE_CARRIER", "Once cursor loops are unsupported")
                if not cursor.ready:
                    fail(p, "DEMAND", "loop invariant requires a ready cursor")
                if type(i["count"]) is not int or i["count"] < 0:
                    fail(p, "SCHEMA", "loop count must be a nonnegative integer")
                binder = name(i["as"], p + ".as", variable=True)
                self.consume(state, i["cursor"], p)
                loop_group = self.fresh()
                inner = State({"$home": Value(loop_group, "key", "loan", anchor="$activation"),
                               binder: Value(loop_group, "ref", layout=cursor.layout, ready=True, identity=self.identity())},
                              {"$home", binder}, Order(), loop_group, cursor.layout, True)
                self.block(i["body"], inner, p + ".body")
                group = self.fresh()
                state.order.add(cursor.group, group)
                self.bind(state, i["out"], Value(group, "ref", layout=cursor.layout, ready=True, identity=self.identity()), p)
            elif op == "choose":
                if type(i["condition"]) is not bool:
                    fail(p, "SCHEMA", "condition must be a boolean")
                self.branches += 2
                self.block(i["then"], state.copy(), p + ".then")
                self.block(i["else"], state.copy(), p + ".else")
            elif op == "return":
                if state.result_layout is None:
                    fail(p, "RETURN", "entry must finish; only callbacks/loop bodies return")
                result = self.get(state, i["value"], p, kind="ref", own=True)
                if result.layout != state.result_layout:
                    fail(p, "LAYOUT", "return has the wrong nominal layout")
                if not state.order.below(result.group, state.home):
                    fail(p, "UPWARD_RETURN", "raw return must be Down(fixed activation home)")
                if state.require_ready and not result.ready:
                    fail(p, "DEMAND", "loop must return a ready cursor")
                if state.result_identity is not None and result.identity != state.result_identity:
                    fail(p, "IDENTITY", "declared argument identity is not preserved by the actual return")
                self.consume(state, i["value"], p)
                self.finish(state, p)
            elif op == 'finish_scalar':
                if not state.finish_allowed or state.result_layout is not None:
                    fail(p, 'RETURN', 'finish_scalar is entry-only')
                result = self.get(state, i['value'], p, kind='ref', own=True)
                if result.layout not in SCALAR_SHAPES:
                    fail(p, 'LAYOUT', 'finish_scalar requires intrinsic i64 or bool')
                if not result.ready:
                    fail(p, 'DEMAND', 'finish_scalar requires an explicitly forced/ready scalar')
                self.consume(state, i['value'], p)
                self.finish(state, p)
            elif op == "finish":
                if not state.finish_allowed:
                    fail(p, "RETURN", "callback/loop needs an owned return, not finish")
                self.finish(state, p)
            if terminal:
                return
        fail(path, "TERMINAL", "block has no terminal instruction")

    def check(self) -> CheckedProgram:
        self.schemas()
        for code, spec in self.codes.items():
            home = self.fresh()
            state = State({"$home": Value(home, "key", "loan", anchor="$activation")},
                          {"$home"}, Order(), home, spec["result"])
            for capture, contract in spec["captures"].items():
                group = home if contract["relation"] == "same" else self.fresh()
                if group != home:
                    state.order.add(home, group, contract["relation"] == "below")
                state.values[capture] = Value(group, "ref", layout=contract["layout"], identity=self.identity())
                state.used.add(capture)
            self.block(spec["body"], state, f"codes.{code}.body")
        for function, spec in self.functions.items():
            signature = self.signatures[spec["signature"]]
            home, closure_group, argument_group = self.fresh(), self.fresh(), self.fresh()
            state = State({"$home": Value(home, "key", "loan", anchor="$activation")},
                          {"$home"}, Order(), home, signature["result"], self.once(signature["result"]))
            state.order.add(home, closure_group)
            state.order.add(home, argument_group)
            for capture, contract in spec["captures"].items():
                group = closure_group if contract["relation"] == "same" else self.fresh()
                if group != closure_group:
                    state.order.add(closure_group, group, contract["relation"] == "below")
                state.values[capture] = Value(group, "ref", layout=contract["layout"],
                                              ready=self.once(contract["layout"]), identity=self.identity())
                state.used.add(capture)
            argument = Value(argument_group, "ref", layout=signature["argument"],
                             ready=self.once(signature["argument"]), identity=self.identity())
            state.values[spec["parameter"]] = argument
            state.used.add(spec["parameter"])
            if signature["result_identity"] == "argument":
                state.result_identity = argument.identity
            self.block(spec["body"], state, f"functions.{function}.body")
        self.block(self.program["entry"], State({}, set(), Order(), None, None,
                                              finish_allowed=True), "entry")
        canonical = json.dumps(self.program, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return CheckedProgram(canonical, hashlib.sha256(canonical.encode()).hexdigest(),
                              len(self.codes), self.ops, self.branches, len(self.functions))


def check(program: Any) -> CheckedProgram:
    # Own the input snapshot *before* analysis. Later mutation of a caller's
    # nested dictionaries cannot change what is serialized/executed afterward.
    try:
        snapshot = json.dumps(program, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        fail("program", "SCHEMA", f"input must be a finite JSON value: {exc}")
    return Checker(loads(snapshot)).check()


def loads(text: str) -> dict:
    """Reject duplicate JSON keys rather than silently accepting the last claim."""
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                fail("json", "DUPLICATE_KEY", f"duplicate object key {key!r}")
            result[key] = value
        return result
    def constant(value: str) -> None:
        fail("json", "SCHEMA", f"non-JSON constant {value!r}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
