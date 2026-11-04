"""End-to-end manifest discovery, diagnostics and worker-plan fixtures."""

import json
from pathlib import Path
import subprocess


def compare_managers(work, manager, reference=None):
    work.mkdir()

    def write(name, deps, modules):
        root = work / name
        root.mkdir(exist_ok=True)
        for mod, imports in modules.items():
            (root / (mod + ".emlf")).write_text(
                "module "
                + mod
                + " where\n"
                + "".join("import " + imp + "\n" for imp in imports)
                + "value"
                + mod
                + " = 1\n"
            )
        data = {
            "format": 1,
            "name": name,
            "version": "1.0.0",
            "dependencies": {k: {"path": "../" + k} for k in deps},
            "library": {"modules": {k: k + ".emlf" for k in modules}},
        }
        (root / "mlf-package.json").write_text(json.dumps(data))

    def plan(binary):
        run = subprocess.run(
            [binary, "--manifest", work / "root/mlf-package.json", "--offline", "plan"],
            capture_output=True,
            timeout=60,
        )
        return (run.returncode, run.stdout, run.stderr)

    def check(message=None):
        actual = plan(manager)
        if reference and actual != plan(reference):
            raise ValueError("before/after package plans or diagnostics differ: " + repr(actual))
        code, out, err = actual
        if message:
            if code == 0 or message.encode() not in err:
                raise ValueError((code, out, err))
        else:
            if code != 0:
                raise ValueError(err)
            return json.loads(out)

    write("leaf", [], {"Leaf": []})
    write("left", ["leaf"], {"LeftArm": ["Leaf", "Leaf"]})
    write("right", ["leaf"], {"RightArm": ["Leaf"]})
    write("root", ["right", "left"], {"A": ["B", "RightArm"], "B": ["A", "LeftArm"]})
    good = check()
    rows = {row["crate"]: row["dependencies"] for row in good["crates"]}
    if rows != {
        "leaf/1.0.0/library": [],
        "left/1.0.0/library": ["leaf/1.0.0/library"],
        "right/1.0.0/library": ["leaf/1.0.0/library"],
        "root/1.0.0/library": ["left/1.0.0/library", "right/1.0.0/library"],
    }:
        raise ValueError("unexpected crate DAG: " + repr(rows))
    write("root", ["right", "left"], {"A": ["Leaf"]})
    check("root:A: import Leaf is not declared in this package or a direct dependency")
    write("root", ["right", "left"], {"Leaf": []})
    check("module is provided by multiple packages")
    write("root", ["left"], {"A": []})
    write("leaf", ["root"], {"Leaf": []})
    check("dependency cycle:")
