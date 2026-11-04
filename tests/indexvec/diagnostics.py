"""Compare public source diagnostics across declaration table layouts."""
import json
from pathlib import Path
import subprocess


def check_diagnostics(folder: Path, compiler: Path, reference: Path | None = None):
    folder.mkdir()
    (folder / "A.emlf").write_text("module A (value) where\nvalue = 41\n")
    (folder / "B.emlf").write_text("module B (value) where\nvalue = True\n")
    main = folder / "Test.emlf"
    mismatch = b'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n'
    cases = [
        ("ambiguous imports", "import A\nimport B\nmain = value\n",
         f"ModuleResolution: {main}: ambiguous name value: A.value, B.value\n".encode()),
        ("local shadow", "import qualified A as X\nmain = (\\value -> addInt (X.value) value) True\n", mismatch),
        ("generated dictionary", "class Tag a where { tag :: a -> Int }\n"
         "instance Tag Bool where { tag x = x }\nmain = tag True\n", mismatch),
        ("unresolved spelling", "import qualified A as X\nmain = X.missing\n",
         f"ModuleResolution: {main}: name is not in scope: X.missing\n".encode()),
        ("source location", "main = (1 + ) +\n", f"Parsing: {main}:2:13: unexpected ); expected False\n".encode()),
    ]
    results = {}
    for label, source, expected in cases:
        main.write_text("module Test where\n" + source)
        for exe in [compiler] if reference is None else [reference, compiler]:
            result = subprocess.run([exe, "--no-prelude", "--type", main], capture_output=True, timeout=360)
            if result.returncode != 1 or result.stdout or result.stderr != expected:
                raise ValueError(f"{exe}: {label}: {result.returncode}, {result.stdout!r}, {result.stderr!r}")
        results[label] = expected.decode().rstrip()
    (folder / "diagnostics.json").write_text(json.dumps(results, indent=2) + "\n")
