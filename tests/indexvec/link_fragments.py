"""A diamond of independently compiled crates, relinked with every source removed."""
import shutil
import sys
from pathlib import Path


def check_diamond(run, work, compiler):
    from crates import frame
    work.mkdir()
    header = ("-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, "
              "NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, "
              "FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n")
    modules = [
        ("Shared", [], "value = 20; neverSelected = 997261"),
        ("LeftSide", ["Shared"], "import qualified Shared as S; left = addInt S.value 1"),
        ("RightSide", ["Shared"], "import qualified Shared as S; right = addInt S.value 1"),
        ("Client", ["LeftSide", "RightSide"],
         "import LeftSide; import RightSide; main = putStrLn (showInt (addInt left right))")]
    for module, dependencies, body in modules:
        source = work / (module + ".hs")
        source.write_text(header + f"module {module} where {{ import MLF.Primitive; {body} }}\n")
        spec = source.with_suffix(".spec")
        spec.write_text(frame(["MLF-CRATE-1", module, "Client" if module == "Client" else "", "false",
            frame([frame([module, str(source)])]), frame([str(work / (d + ".mlfci")) for d in dependencies]),
            str(work / (module + "-cache")), str(work / "builtin/unit")]))
        run([compiler, "--compile-crate", spec, "-o", source.with_suffix("")])
        source.unlink()
        shutil.rmtree(work / (module + "-cache"))
    interface = work / "Client.mlfci"
    linked = run([compiler, "--link-crate", interface])
    assert b"997261" not in linked, "unreachable fragment was grafted into the executable"
    run([compiler, "--run-crate", interface], expected=b"42\n")
    # The diamond must use one producer for the common crate. Keep all object
    # hashes valid and relocate just one dependency edge to a second copy.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/shared"))
    from artifact_binary_reference import read_document, tree_document
    from artifact_binary_typed import list_values, n, s, text, value_node
    right = work / "RightSide.mlfci"
    saved = right.read_bytes()
    shared = work / "Shared.mlfci"
    copied = work / "Shared-second.mlfci"
    shutil.copyfile(shared, copied)
    shutil.copyfile(shared.with_suffix(".mlfco"), copied.with_suffix(".mlfco"))
    fields = list(value_node(read_document(saved, 3).values()[0], 242, 13))
    dependencies = []
    for entry in list_values(fields[1]):
        key, path, digest = value_node(entry, 3, 3)
        dependencies.append(n(3, key, s(str(copied)) if text(key) == "Shared" else path, digest))
    fields[1] = n(1, *dependencies)
    right.write_bytes(tree_document([n(242, *fields)], 3))
    run([compiler, "--link-crate", interface], failure=b"duplicate crate identity")
    right.write_bytes(saved)
    shared.rename(shared.with_suffix(".absent"))
    run([compiler, "--link-crate", interface], failure=b"does not exist")
    shared.with_suffix(".absent").rename(shared)
    source = work / "Shared.hs"
    source.write_text(header + "module Shared where { import MLF.Primitive; value = True; neverSelected = 997261 }\n")
    run([compiler, "--compile-crate", source.with_suffix(".spec"), "-o", source.with_suffix("")])
    run([compiler, "--link-crate", interface], failure=b"dependency")
