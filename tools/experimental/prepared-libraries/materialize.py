#!/usr/bin/env python3
"""Materialize independent finite fixture oracles against one generated registry.

All changed sources are copies in a fresh owned directory. This command never
runs the compiler and never learns expected results from the ordinary route.
Only exact lexical paths and authenticated protected names are substituted in
the checked-in fixture definitions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path,
                        default=Path(__file__).with_name("fixtures") / "controls.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    job, fixture_path = args.job.resolve(strict=True), args.fixtures.resolve(strict=True)
    request_path, product_path, build_path = job / "request.json", job / "artifacts/generation.json", job / "build/receipt.json"
    request = json.loads(request_path.read_text())
    product = json.loads(product_path.read_text())
    build = json.loads(build_path.read_text())
    fixtures = json.loads(fixture_path.read_text())
    if (fixtures.get("format") != "MLF-PREPARED-LIBRARY-FIXTURES-1"
            or request.get("format") != "MLF-PREPARED-LIBRARY-JOB-1"
            or product.get("format") != "MLF-PREPARED-LIBRARY-GENERATION-1"):
        raise ValueError("unsupported fixture/job/generation format")
    required_steps = {"build-generate-prepared-libraries", "generate", "build-prepared-library-probe"}
    completed_steps = {row["label"] for row in build["commands"] if row["exit_code"] == 0}
    if not required_steps <= completed_steps or not build.get("immutable_inputs_verified_after"):
        raise ValueError("fixture materialization requires successful immutable producer and probe steps")
    # A later independent loader-control build may have failed. Preserve that
    # failure receipt; do not reinterpret it as full qualification completion.
    probe_record = build["prepared-library-probe"]
    if sha(Path(probe_record["path"])) != probe_record["sha256"]:
        raise ValueError("completed producer's probe changed")
    if build["generated_product"] != product or product["input_identity"] != request["input_identity"]:
        raise ValueError("generated product is not the completed build's exact product")
    if request["roots"] != fixtures["library_roots"] or request["mode"] != "ImplicitPrelude":
        raise ValueError("this fixture matrix requires its prescribed roots and Prelude profile")
    authenticated = {product["generated_source"]: product["generated_sha256"]}
    for artifact in product["artifacts"]:
        for field in ["metadata", "object"]:
            authenticated[artifact[field + "_path"]] = artifact[field + "_sha256"]
    for path, digest in authenticated.items():
        if sha(Path(path)) != digest:
            raise ValueError("generated registry/artifact changed: " + path)
    inventory = {row["module"]: row for row in request["library_inventory"]}
    if len(inventory) != len(request["library_inventory"]):
        raise ValueError("duplicate module in frozen source inventory")
    selected = []
    for name, path, digest in zip(product["modules"], product["source_paths"], product["source_sha256"], strict=True):
        row = inventory[name]
        if row["path"] != path or row["sha256"] != digest or sha(Path(row["buffer_path"])) != digest:
            raise ValueError("generated source evidence changed: " + name)
        selected.append(dict(module=name, source_path=path, buffer_path=row["buffer_path"]))
    value_names = [name for name in product["binding_names"] if re.fullmatch(r"[a-z][A-Za-z0-9_]*", name)]
    class_names = [name for name in product["class_names"] if re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name)]
    if not value_names or not class_names:
        raise ValueError("fixture collisions require actual generated value and class support identities")
    common = {row["module"]: row["source_path"] for row in selected}
    common.update(protected_value=value_names[0], protected_dictionary="Dict_" + class_names[0])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = {fixture_path, request_path, product_path, build_path, Path(__file__).resolve(), Path(probe_record["path"]),
              *map(Path, authenticated), *(Path(row["buffer_path"]) for row in selected)}
    cases = []
    case_names = set()
    for fixture in fixtures["cases"]:
        name = fixture["name"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name in case_names:
            raise ValueError("fixture names must be unique file-safe identifiers")
        case_names.add(name)
        directory = output / name
        directory.mkdir()
        root = directory / "Root.emlf"
        substitutions = {**common, "root": str(root)}

        def expand(text: str) -> str:
            def replace(match: re.Match) -> str:
                if match[1] not in substitutions:
                    raise ValueError("unknown fixture placeholder: " + match[1])
                return substitutions[match[1]]
            return re.sub(r"\{\{([^{}]+)\}\}", replace, text)

        root.write_text(expand(fixture["source"]))
        inputs.add(root)
        sources = {row["module"]: dict(row) for row in selected}
        for module, text in fixture.get("extra_modules", {}).items():
            if module in sources:
                raise ValueError("extra module shadows a frozen registry module")
            target = directory / "extra" / (module.replace(".", "/") + ".emlf")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expand(text))
            sources[module] = dict(module=module, source_path=str(target), buffer_path=str(target))
            inputs.add(target)
        mutated = set()
        for mutation in fixture.get("mutations", []):
            module = mutation["module"]
            if module in mutated or module not in sources:
                raise ValueError("mutation must name one distinct frozen source")
            mutated.add(module)
            row = sources[module]
            text = Path(row["buffer_path"]).read_text()
            if "replace" in mutation:
                before, after = mutation["replace"]
                if text.count(before) != 1:
                    raise ValueError("mutation replacement must match exactly one source fragment")
                text = text.replace(before, after)
            text += mutation.get("append", "")
            target = directory / "mutated" / (module.replace(".", "/") + Path(row["source_path"]).suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            row["buffer_path"] = str(target)
            if mutation.get("relocate", False):
                row["source_path"] = str(target)
            inputs.add(target)
        case_request = dict(source_path=str(root), buffer_path=str(root), include_paths=[],
                            source_map=list(sources.values()), no_prelude=fixture.get("no_prelude", False),
                            arguments=fixture.get("arguments", []))
        if "registry_variant" in fixture:
            case_request["registry_variant"] = fixture["registry_variant"]
        target = directory / "request.json"
        dump(target, case_request)
        inputs.add(target)
        case = {key: fixture[key] for key in ["name", "accepted", "reused"]}
        case["request"] = str(target)
        case["execute"] = fixture.get("execute", ["interpreter", "native"] if fixture["accepted"] else [])
        for field in ["error", "error_phase", "layout_entities"]:
            if field in fixture:
                case[field] = fixture[field]
        if case["execute"]:
            oracle = dict(exit_code=fixture.get("exit_code", 0),
                          stdout_hex=expand(fixture["stdout"]).encode("utf-8").hex(),
                          stderr_hex=expand(fixture.get("stderr", "")).encode("utf-8").hex())
            for engine in case["execute"]:
                if engine not in {"interpreter", "native"}:
                    raise ValueError("unknown fixture execution engine")
                case[engine] = dict(oracle)
        cases.append(case)
    pins = {str(path): sha(path) for path in sorted(inputs)}
    manifest = dict(format="MLF-PREPARED-LIBRARY-CONTROLS-1", inputs=list(pins), input_sha256=pins,
                    input_identity=request["input_identity"], producer_full_build_complete=build["complete"],
                    protected_name_substitutions={
                        key: common[key] for key in ["protected_value", "protected_dictionary"]}, cases=cases)
    dump(output / "manifest.json", manifest)
    print(output / "manifest.json")


if __name__ == "__main__":
    main()
