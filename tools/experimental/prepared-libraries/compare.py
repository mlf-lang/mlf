"""Independent structural comparison of prepared-library probe reports.

Only lexical bound-variable alpha renaming and explicit Entity correspondences
are admitted. There is no generated-name regex, sorting of layouts, or stripping
of diagnostic digits, source paths, package names, or call-stack text.
"""
from __future__ import annotations

import json


def name_table(report: dict) -> dict[tuple[str, str], object]:
    result = {}
    owners = set()
    for row in report["nominals"]:
        name, identity = (row["namespace"], row["name"]), row["identity"]
        if name[0] not in {"type", "constructor"}:
            raise ValueError("invalid nominal namespace")
        key = (name[0], json.dumps(identity, sort_keys=True, separators=(",", ":")))
        if name in result or key in owners:
            raise ValueError("nominal correspondence is not one-to-one")
        result[name], owners = identity, owners | {key}
    return result


def nominal(name: str, names: dict, namespace: str = "type") -> object:
    if (namespace, name) not in names:
        raise ValueError("unmapped nominal identity: " + name)
    return names[namespace, name]


def kind(value: list) -> object:
    if value == ["star"]:
        return value
    if len(value) == 3 and value[0] == "kind-arrow":
        return [value[0], kind(value[1]), kind(value[2])]
    raise ValueError("invalid kind report")


def xtype(value: list, names: dict, variables: tuple = ()) -> object:
    tag = value[0]
    if tag == "var" and len(value) == 2:
        if value[1] not in variables:
            raise ValueError("reported principal type contains a free variable")
        return ["var", variables[::-1].index(value[1])]
    if value == ["bottom"]:
        return value
    if tag == "bottom-kind" and len(value) == 2:
        return [tag, kind(value[1])]
    if tag in {"arrow", "apply"} and len(value) == 3:
        return [tag, xtype(value[1], names, variables), xtype(value[2], names, variables)]
    if tag == "con" and len(value) == 3:
        return [tag, nominal(value[1], names), [xtype(item, names, variables) for item in value[2]]]
    if tag == "forall" and len(value) == 4:
        if value[1] in variables:
            raise ValueError("target type reuses a binder identity")
        return [tag, xtype(value[2], names, variables), xtype(value[3], names, variables + (value[1],))]
    raise ValueError("invalid target type report")


def field(value: list, names: dict, parameters: tuple) -> object:
    tag = value[0]
    if tag == "parameter" and len(value) == 2:
        if value[1] not in parameters:
            raise ValueError("free datatype field parameter")
        return [tag, parameters[::-1].index(value[1])]
    if tag in {"function", "application"} and len(value) == 3:
        return [tag, field(value[1], names, parameters), field(value[2], names, parameters)]
    if tag == "applied" and len(value) == 3:
        return [tag, nominal(value[1], names), [field(item, names, parameters) for item in value[2]]]
    if tag == "quantified" and len(value) == 4:
        return [tag, kind(value[2]), field(value[3], names, parameters + (value[1],))]
    raise ValueError("invalid datatype field report")


def layouts(report: dict, names: dict) -> list:
    result = []
    for declaration in report["layouts"]:
        params = tuple(item[0] for item in declaration["parameters"])
        if len(set(params)) != len(params):
            raise ValueError("duplicate datatype parameters")
        result.append([nominal(declaration["name"], names),
                       [kind(item[1]) for item in declaration["parameters"]],
                       [[nominal(ctor["name"], names, "constructor"), [field(item, names, params) for item in ctor["fields"]]]
                        for ctor in declaration["constructors"]]])
    return result


def compare(ordinary: dict, prepared: dict, expected: str, require_reuse: bool) -> None:
    for report in [ordinary, prepared]:
        if report.get("format") != "MLF-PREPARED-LIBRARY-PROBE-1":
            raise ValueError("unsupported probe report")
    if ordinary["accepted"] != prepared["accepted"]:
        raise ValueError("prepared route changed source acceptance")
    if ordinary["accepted"] != (expected == "accepted"):
        raise ValueError("both routes violated the independent acceptance oracle")
    if not ordinary["accepted"]:
        if ordinary["error"] != prepared["error"]:
            raise ValueError("prepared route changed error phase or exact diagnostic")
        return
    if prepared["reused"] != require_reuse:
        raise ValueError("prepared reuse/fallback disagrees with the independent route oracle")
    before, after = name_table(ordinary), name_table(prepared)
    if xtype(ordinary["principal_type"], before) != xtype(prepared["principal_type"], after):
        raise ValueError("prepared route changed principal target type")
    if layouts(ordinary, before) != layouts(prepared, after):
        raise ValueError("prepared route changed ordered datatype/constructor layouts")
