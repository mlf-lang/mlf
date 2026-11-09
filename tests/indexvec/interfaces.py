"""Compare resolved exports and checked ABI ownership through the file interface."""
import json
from pathlib import Path
import sys

from crates import frame


def check_interfaces(run, work, compiler, reference=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/shared"))
    from artifact_binary_reference import read_document
    from artifact_binary_typed import list_values, text, value_node
    work.mkdir()
    header = ("-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, "
              "RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, "
              "OverloadedStrings #-}\n")
    # A and B export an identical spelling. A alone owns hidden. The facade
    # exposes A.value without becoming a new producer of that definition.
    modules = [
        ("A", "(Tag(..), value)", "class Tag a where { tag :: a -> Int }; "
         "instance Tag Bool where { tag x = 40 }; hidden = tag True; value = hidden", []),
        ("B", "(value)", "value = 2", []),
        ("Facade", "(module A)", "import A; privateFacade = 9", ["A"]),
        ("App", "", "import qualified Facade as F; import qualified B; "
                    "main = printInt (addInt F.value B.value)", ["Facade", "B"])]
    for module, exports, source, deps in modules:
        path = work / (module + ".hs")
        path.write_text(header + f"module {module} {exports} where {{ import MLF.Primitive; {source} }}\n")
        path.with_suffix(".spec").write_text(frame([
            "MLF-CRATE-1", module + "-pkg", "App" if module == "App" else "", "false",
            frame([frame([module, str(path)])]), frame([str(work / (name + ".mlfci")) for name in deps]),
            str(work / (module + "-cache")), str(work / "builtin/unit")]))
    previous = {}
    for binary in ([reference] if reference else []) + [compiler]:
        tables = {}
        for module, _, _, _ in modules:
            run([binary, "--compile-crate", work / (module + ".spec"), "-o", work / module])
            data = (work / (module + ".mlfci")).read_bytes()
            if previous.setdefault(module, data) != data:
                raise AssertionError(f"{module}: public interface bytes changed")
            fields = value_node(read_document(data, 3).values()[0], 242, 13)
            bindings = [text(value_node(row, 2, 2)[0]) for row in list_values(fields[9])]
            protected = [text(value_node(row, 2, 2)[0]) for row in list_values(fields[12])]
            entry = text(fields[10])
            assert sorted(bindings) == sorted(protected)
            if module == "App":
                assert entry in bindings
            else:
                assert entry == ""
            exports = {}
            for row in list_values(fields[3]):
                name, entities = value_node(row, 2, 2)
                exports[text(name)] = [(text(owner), text(item))
                                       for owner, item, _ in (value_node(e, 189, 3) for e in list_values(entities))]
            tables[module] = (exports[module], set(bindings))
        assert set(tables['A'][0]) == {('A', 'Tag'), ('A', 'tag'), ('A', 'value')}
        assert tables['B'][0] == [('B', 'value')]
        assert any(name.startswith('instance_') for name in tables['A'][1])
        assert any(name.startswith('select_') for name in tables['A'][1])
        assert set(tables['Facade'][0]) == set(tables['A'][0])
        assert all(tables[a][1].isdisjoint(tables[b][1])
                   for i, (a, *_) in enumerate(modules) for b, *_ in modules[i+1:])
        run([binary, "--run-crate", work / "App.mlfci"], expected=b"42\n")
        app = work / "App.hs"
        saved = app.read_text()
        app.write_text(saved.replace("F.value", "F.hidden"))
        try:
            run([binary, "--compile-crate", work / "App.spec", "-o", work / "forbidden"], failure=b"F.hidden")
        finally:
            app.write_text(saved)
    (work / 'checks.json').write_text(json.dumps({m: sorted(names) for m, (_, names) in tables.items()}, indent=2) + '\n')
