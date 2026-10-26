#!/usr/bin/env python3
"""Stage an immutable, ordinary-provenance fixed-library preparation job.

This command copies and hashes inputs. It does not build or run a compiler,
select imports with a second parser, or publish generated production sources.
Generate.hs selects the requested closure using the real source parser/loader.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATA_PATH = Path("bootstrap/MLF/PreparedLibraryData.hs")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library-manifest", type=Path, required=True)
    parser.add_argument("--module", action="append", required=True, dest="modules")
    parser.add_argument("--lexical-root", help="Exact ordinary loader path prefix; defaults to the absolute manifest directory")
    parser.add_argument("--no-prelude", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_manifest = (ROOT / "shared-sources.json").resolve(strict=True)
    library_manifest = args.library_manifest.resolve(strict=True)
    source_description = json.loads(source_manifest.read_text())
    library_description = json.loads(library_manifest.read_text())
    if source_description.get("format") != 1 or library_description.get("format") != 1:
        raise ValueError("unsupported source/library manifest format")
    inventory = library_description.get("library", {}).get("modules", {})
    if not inventory or not isinstance(inventory, dict):
        raise ValueError("library manifest must contain an explicit module-to-file map")
    if len(args.modules) != len(set(args.modules)) or not set(args.modules) <= set(inventory):
        raise ValueError("requested roots must be distinct members of the library inventory")
    registered = {row["module"] for row in source_description["modules"]}
    required = {"Bootstrap.PreparedLibraries", "Bootstrap.PreparedLibraryLiteral", "MLF.PreparedLibraryData"}
    if not required <= registered:
        raise ValueError("canonical prepared-library sources must be registered before staging: "
                         + ", ".join(sorted(required - registered)))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "sources"
    recorded: dict[str, dict[str, object]] = {}

    def copy(path: Path) -> dict[str, object]:
        path = path.resolve(strict=True)
        relative = path.relative_to(ROOT)
        key = relative.as_posix()
        if key in recorded:
            return recorded[key]
        data = path.read_bytes()
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        pin = {"path": str(path), "snapshot": str(target), "sha256": sha_bytes(data), "bytes": len(data)}
        if sha_bytes(path.read_bytes()) != pin["sha256"]:
            raise RuntimeError("input changed while snapshotting: " + str(path))
        recorded[key] = pin
        return pin

    for source in source_description["modules"]:
        copy(ROOT / source["path"])
    for source in source_description["host_only"]:
        copy(ROOT / source)
    for path in [source_manifest, library_manifest, ROOT / "host/ghc/cbits/host.c",
                 ROOT / "runtime/mlf_runtime.c",
                 ROOT / "runtime/mlf_process_supervisor.c", *sorted((ROOT / "runtime").glob("*.h")),
                 *sorted(HERE.rglob("*.py")), *sorted(HERE.rglob("*.hs")),
                 *sorted(HERE.rglob("*.emlf")), *sorted(HERE.rglob("*.json")),
                 *sorted(HERE.rglob("*.md"))]:
        copy(path)
    libraries = []
    lexical_root = args.lexical_root if args.lexical_root is not None else str(library_manifest.parent)
    for name, relative in inventory.items():
        pin = copy(library_manifest.parent / relative)
        if Path(relative).is_absolute():
            raise ValueError("library module paths must be manifest-relative")
        # Match Module.joinPath without resolving symlinks, dot segments, or
        # normalizing the exact lexical filename supplied to the source parser.
        lexical_path = lexical_root + ("" if lexical_root.endswith("/") else "/") + relative
        libraries.append({"module": name, "path": lexical_path, "buffer_path": pin["snapshot"],
                          "sha256": pin["sha256"]})
    # The generated registry cannot be an input to its own regeneration.
    # It remains snapshotted for consumer builds, but is excluded from this key.
    semantic_inputs = {key: value["sha256"] for key, value in recorded.items()
                       if key != DATA_PATH.as_posix()}
    identity_input = {"format": "MLF-PREPARED-LIBRARY-JOB-1", "source_hashes": semantic_inputs,
                      "roots": args.modules, "source_package": "main",
                      "mode": "NoImplicitPrelude" if args.no_prelude else "ImplicitPrelude",
                      "library_inventory": libraries,
                      "primitive_abi": source_description["primitive_abi"],
                      "frontend_semantics": source_description["frontend_semantics"]}
    # Snapshot storage paths are not source semantics and must not perturb keys.
    identity_input["library_inventory"] = [{key: value for key, value in row.items() if key != "buffer_path"}
                                            for row in libraries]
    identity = sha_bytes(json.dumps(identity_input, sort_keys=True, separators=(",", ":")).encode())
    generated = output / "generated" / "MLF" / "PreparedLibraryData.hs"
    generated.parent.mkdir(parents=True)
    artifacts = output / "artifacts"
    artifacts.mkdir()
    request = {"format": "MLF-PREPARED-LIBRARY-JOB-1", "input_identity": identity,
               "library_identity": "mlf:prepared-library:" + identity,
               "source_package": "main", "mode": identity_input["mode"],
               "roots": args.modules, "library_inventory": libraries,
               "output_directory": str(artifacts), "generated_source": str(generated),
               "primitive_abi": source_description["primitive_abi"],
               "frontend_semantics": source_description["frontend_semantics"]}
    dump(output / "request.json", request)
    dump(output / "identity-input.json", identity_input)
    dump(output / "source-pins.json", recorded)
    dump(output / "receipt.json", {"format": "MLF-PREPARED-LIBRARY-STAGING-1", "complete": True,
         "stage": "inputs-staged-only", "input_identity": identity, "source_pins": recorded,
         "generated_source": str(generated), "generator_executed": False,
         "production_source_changed": False, "native_qualification": False,
         "user_program_cache": False, "performance_assertions": False})
    print(output / "request.json")


if __name__ == "__main__":
    main()
