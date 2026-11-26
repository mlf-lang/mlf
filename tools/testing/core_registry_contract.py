"""Validate current Core descriptors against the current catalog.

The checked-in descriptor contract is the independent oracle used by compiler
discovery and execution-report checks. It is reviewed as ordinary test data;
its meaning does not depend on historical test renames or source migrations.
"""
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_contract(contract, catalog):
    require(isinstance(contract, dict) and set(contract) == {"schema_version", "cases"}
            and type(contract["schema_version"]) is int and contract["schema_version"] == 1,
            "invalid Core descriptor contract schema")
    cases = contract["cases"]
    require(isinstance(cases, list) and cases, "empty Core descriptor contract")
    identities, families, order = set(), {}, []
    for row in cases:
        require(isinstance(row, dict) and set(row) == {"id", "name", "family"}
                and all(isinstance(value, str) and value for value in row.values()),
                "invalid Core descriptor")
        family, identity = row["family"], row["id"]
        require(re.fullmatch(r"core/[a-z0-9]+(?:-[a-z0-9]+)*", family) is not None
                and identity.startswith(family + "/") and len(identity) > len(family) + 1,
                "Core descriptor has the wrong family")
        require(identity not in identities, "duplicate Core descriptor ID")
        identities.add(identity)
        if not order or family != order[-1]:
            require(family not in families, "interleaved Core descriptor families")
            order.append(family)
            families[family] = []
        families[family].append(row)
    current = [row for row in catalog["families"] if row["unit"] == "core"]
    require(order == [row["id"] for row in current], "Core catalog family order differs")
    for family in current:
        name, evidence = family["id"], family["evidence"]
        rows, labels = families[name], evidence["executions"]
        if name == "core/substring-adapter":
            # Separately named boundary cases use their public coverage metric.
            require(not labels and len(rows) == evidence["metrics"]["substring-executed"],
                    "substring descriptor count differs from catalog coverage")
        else:
            expected = [{"id": name + "/" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"),
                         "name": label, "family": name} for label in labels]
            require(rows == expected, "Core public descriptors differ from catalog: " + name)
    return cases
