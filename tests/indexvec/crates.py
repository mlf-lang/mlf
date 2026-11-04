"""Check the declaration identity boundary between separately compiled crates."""

import hashlib
import itertools
import json
import shutil


def frame(fields):
    return "".join(f"{len(field)}:{field}" for field in fields)


def check_crates(run, work, compiler, reference=None):
    work.mkdir()
    header = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n"
    lib = work / "ZLib.hs"
    lib.write_text(header + "module ZLib (value) where {\nimport MLF.Primitive;\nvalue :: Int;\nvalue = 41\n}\n")
    app = work / "Client.hs"
    app.write_text(header + "module Client where {\nimport MLF.Primitive;\nimport qualified ZLib as L;\nmain = putStrLn (showInt (addInt L.value 1))\n}\n")
    products, cases = {}, []

    def compile_unit(exe, name, source, identity, entry, dependencies):
        prefix = work / name
        cache = work / (name + "-cache")
        if cache.exists():
            shutil.rmtree(cache)
        spec = prefix.with_suffix(".spec")
        spec.write_text(frame(["MLF-CRATE-1", identity, entry, "false",
            frame([frame([source.stem, str(source)])]), frame(dependencies),
            str(cache), str(work / "builtin/unit")]))
        run([exe, "--compile-crate", spec, "-o", prefix])
        result = {ext: hashlib.sha256(prefix.with_suffix(ext).read_bytes()).hexdigest()
                  for ext in (".mlfci", ".mlfco", ".queries")}
        if products.setdefault(name, result) != result:
            raise AssertionError(f"{name} artifact changed with the producer/client combination")

    compilers = {"candidate": compiler}
    if reference is not None:
        compilers = {"previous": reference.resolve(strict=True), **compilers}
    for producer, client in itertools.product(compilers, repeat=2):
        compile_unit(compilers[producer], "library", lib, "lib", "", [])
        compile_unit(compilers[client], "client", app, "client", "Client", [str(work / "library.mlfci")])
        for reader in compilers.values():
            run([reader, "--run-crate", work / "client.mlfci"], expected=b"42\n")
        cases.append({"library": producer, "client": client, "readers": list(compilers), "stdout": "42"})
    (work / "checks.json").write_text(json.dumps({"products": products, "cases": cases}, indent=2) + "\n")
