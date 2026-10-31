"""Small offline verification suite; invoked only by the resource-bounded harness."""
import json
from pathlib import Path
import shutil
import struct
import importlib.util
import sys


def load_codec():
    # A direct file import also works under Python -I, without cwd/sys.path hooks.
    spec = importlib.util.spec_from_file_location("artifact_representation", Path(__file__).with_name("representation.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r = load_codec()


def fixture(label="original"):
    p = r.packed
    key = ["MLF-SOURCE-CRATE-QUERY-6", "crate", "compiler-identity",
           p([p(["member", "same-name", "signature", "double-bits:9223372036854775808"])]),
           p([p(["binding", "same-name", "forall α. α"])]),
           p([p(["data", "名😀", "layout-a"]), p(["data", "Other", "layout-b"])]),
           p(["prepared-source-group", label, "combining:e\u0301/NUL:\0"]),
           p([p(["source-contract", "same-name", "protected"])]), p([p(["scope", "evidence-role"])])]
    context = "data 名😀 = C;\n"
    meta = ["MLFI-4", "unit", p([p(["dependency", "fingerprint"])]), p(["owned"]), context,
            p(["instance"]), p([p(["same-name", "type"])]), "object-fingerprint"]
    obj = ["MLFO-1", "unit", "fingerprint", context + "raw-body " + label + " -0.0 NaN-payload"]
    return p(["MLF-QUERY-CACHE-1", p(key), p(meta), p(obj)]).encode()


def record(raw, root, name="fixture"):
    return dict(name=name, legacy_bytes=len(raw), legacy_sha256=r.sha(raw), root=root)


def independent_legacy_oracle(raw):
    """Second framing implementation: Unicode scalar cursor, no production parser reuse."""
    text = raw.decode("utf-8")
    result, cursor = [], 0
    while cursor < len(text):
        length = 0
        digits = 0
        while cursor < len(text) and "0" <= text[cursor] <= "9":
            length = length * 10 + ord(text[cursor]) - ord("0")
            digits += 1
            cursor += 1
        assert digits and text[cursor] == ":"
        cursor += 1
        assert cursor + length <= len(text)
        result.append(text[cursor:cursor + length])
        cursor += length
    assert cursor == len(text)
    return result


def run(directory):
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    passed = []

    def check(name, operation):
        operation()
        passed.append(name)

    def rejects(name, operation, message=None):
        try:
            operation()
        except (ValueError, UnicodeError, KeyError, FileNotFoundError) as error:
            if message is not None:
                assert message in str(error), (name, str(error))
            passed.append(name)
        else:
            raise AssertionError("unexpected acceptance: " + name)

    raw = fixture()
    builder = r.Builder()
    root = builder.query(raw)
    builder.write(directory / "valid", [record(raw, root)])
    reader = r.Reader(directory / "valid")
    check("UTF8-astral-combining-NUL-and-opaque-float-token-exact-roundtrip", lambda: equal(reader.decode(root), raw))
    check("independent-legacy-framing-oracle", lambda: equal(independent_legacy_oracle(reader.decode(root)), independent_legacy_oracle(raw)))
    check("full-reachable-accounting", lambda: equal(reader.accounting()["orphan_nodes"], 0))
    check("manifest-record-restores-with-original-byte-hash", lambda: equal(reader.restore("fixture"), raw))
    check("typed-domain-separates-raw-body-from-ordinary-text", lambda: different(r.content_id(r.RAW_BODY, b"same"), r.content_id(r.TEXT, b"same")))
    check("deterministic-query-root", lambda: equal(r.Builder().query(raw), root))
    outer = r.unpacked(raw.decode())
    original_key = r.unpacked(outer[1])
    # Every semantic source-v6 key field remains an input to identity.
    for index in range(1, 9):
        key = list(original_key)
        key[index] = r.packed([key[index], "changed"]) if index in (3, 4, 5, 7, 8) else key[index] + "changed"
        modified = list(outer)
        modified[1] = r.packed(key)
        changed = r.packed(modified).encode()
        changed_builder = r.Builder()
        changed_root = changed_builder.query(changed)
        check("key-field-%d-affects-root" % index, lambda v=changed_root: different(v, root))
    # Input order cannot renumber content identities or change the full bundle.
    other = fixture("other")
    forward, backward = r.Builder(), r.Builder()
    roots_f = [forward.query(x) for x in (raw, other)]
    roots_b = [backward.query(x) for x in (other, raw)]
    records = [record(raw, roots_f[0], "a"), record(other, roots_f[1], "b")]
    forward.write(directory / "forward", records)
    backward.write(directory / "backward", list(reversed(records)))
    check("stable-roots-under-input-reordering", lambda: equal(roots_f, list(reversed(roots_b))))
    for filename in ("objects.pack", "objects.index", "manifest.json"):
        check("deterministic-" + filename, lambda f=filename: equal((directory / "forward" / f).read_bytes(), (directory / "backward" / f).read_bytes()))
    old_nodes = set(builder.nodes)
    builder.query(other)
    check("unchanged-content-identities-survive-insertion", lambda: equal(old_nodes <= set(builder.nodes), True))
    check("same-header-context-shared-across-changed-body", lambda: equal(len(set(builder.role_refs["metadata/4"])), 1))
    check("changed-raw-body-never-aliases", lambda: equal(len(set(builder.role_refs["raw-body"])), 2))
    # Known rejection boundaries: unsupported versions never take a compact shortcut.
    bad = list(outer); bad[0] = "MLF-QUERY-CACHE-2"
    rejects("CACHE-2-rejected-not-reinterpreted", lambda: r.Builder().query(r.packed(bad).encode()))
    bad_key = list(original_key); bad_key[0] = "MLF-SOURCE-CRATE-QUERY-7"
    bad = list(outer); bad[1] = r.packed(bad_key)
    rejects("unknown-semantic-version", lambda: r.Builder().query(r.packed(bad).encode()))
    bad_obj = r.unpacked(outer[3]); bad_obj[3] = "wrong context"
    bad = list(outer); bad[3] = r.packed(bad_obj)
    rejects("unequal-header-body-context-fails-closed", lambda: r.Builder().query(r.packed(bad).encode()))
    rejects("invalid-UTF8", lambda: r.Builder().query(b"\xff"))
    rejects("truncated-legacy-field", lambda: r.unpacked("9:x"))
    rejects("noncanonical-length-explicitly-unsupported", lambda: r.unpacked("01:x"))
    rejects("non-ASCII-length-rejected", lambda: r.unpacked("١:x"))
    rejects("oversized-legacy-length", lambda: r.unpacked("999999999:x"))

    def corrupt(name, transform):
        target = directory / name
        fixture_bytes = sum(p.stat().st_size for p in (directory / "valid").iterdir())
        assert fixture_bytes <= 32768, "corruption copy exceeds reserved tiny fixture size"
        shutil.copytree(directory / "valid", target)
        transform(target)
        rejects(name, lambda: r.Reader(target))

    corrupt("pack-checksum-failure", lambda d: (d / "objects.pack").write_bytes((d / "objects.pack").read_bytes() + b"x"))
    corrupt("index-checksum-failure", lambda d: (d / "objects.index").write_bytes((d / "objects.index").read_bytes()[:-1]))

    def change_manifest(d, key, value):
        m = json.loads((d / "manifest.json").read_bytes()); m[key] = value
        (d / "manifest.json").write_bytes(r.canonical_json(m))

    corrupt("unknown-storage-version", lambda d: change_manifest(d, "format", "future"))
    corrupt("final-root-not-accepted-as-raw", lambda d: change_manifest(d, "semantic_scope", "final"))
    partial = directory / "partial-write"
    partial.mkdir()
    (partial / "objects.pack").write_bytes(b"unpublished")
    rejects("partial-write-without-published-manifest", lambda: r.Reader(partial))

    def bad_index(d, field, value):
        data = bytearray((d / "objects.index").read_bytes())
        entry = list(r.ENTRY.unpack_from(data, 12)); entry[field] = value
        data[12:12 + r.ENTRY.size] = r.ENTRY.pack(*entry)
        (d / "objects.index").write_bytes(data)
        change_manifest(d, "index_sha256", r.sha(data))

    corrupt("offset-gap-rejected-even-with-valid-index-digest", lambda d: bad_index(d, 1, 1))
    corrupt("oversized-decoded-field-rejected", lambda d: bad_index(d, 3, r.MAX_BYTES + 1))
    corrupt("unknown-node-kind-rejected", lambda d: bad_index(d, 5, 255))
    dangling = r.Builder()
    fake = "0" * 64
    dangling_root = dangling.frame([fake] * 4, "", "dangling-test", r.QUERY)
    dangling.write(directory / "dangling", [record(b"", dangling_root)])
    rejects("dangling-reference", lambda: r.Reader(directory / "dangling"))
    orphan = r.Builder(); orphan_root = orphan.query(raw); orphan.text("unreachable")
    orphan.write(directory / "orphan", [record(raw, orphan_root)])
    rejects("orphan-cannot-be-hidden-from-accounting", lambda: r.Reader(directory / "orphan").accounting())
    # Cycles cannot be authored by the normal content-addressed builder. Test the
    # walker guard directly with an adversarial in-memory node provider.
    cycle = object.__new__(r.Reader)
    cycle.entries = {fake: (0, 0, 0, 0, r.QUERY)}
    cycle.node = lambda key: (r.CONCAT, r.encode_refs([fake]), 0, 0)
    rejects("cycle-walker-unit-test", lambda: cycle.decode(fake), "cyclic")
    expansion = object.__new__(r.Reader)
    child = "1" * 64
    expansion.entries = {fake: (0, 0, 0, 0, r.QUERY), child: (0, 0, r.MAX_BYTES, r.MAX_BYTES, r.TEXT)}
    expansion.node = lambda key: (r.CONCAT, r.encode_refs([child, child]), 0, 0)
    rejects("declared-expansion-checked-before-child-allocation", lambda: expansion.decode(fake), "expansion")
    return dict(passed=len(passed), cases=passed,
                limitations=["Cycle and expansion guards use adversarial in-memory providers, not a forged SHA-256 fixed point.",
                             "No compiler semantic checker, production crash/concurrency/GC test, or raw-to-final conversion is run."])


def equal(a, b):
    assert a == b


def different(a, b):
    assert a != b


def run_cli_smoke(directory):
    """Sequential, bounded synthetic CLI controls. All outputs stay in directory."""
    import subprocess
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    first, second = fixture("first"), fixture("second")
    assert max(len(first), len(second)) < 32768
    one, two = directory / "one.mlfq", directory / "two.mlfq"
    one.write_bytes(first); two.write_bytes(second)
    cli = Path(__file__).with_name("cli.py")
    bundle = directory / "bundle"
    passed = []

    def command(arguments, success=True):
        result = subprocess.run([sys.executable, "-I", "-B", str(cli), *map(str, arguments)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
        assert len(result.stdout) + len(result.stderr) <= 65536
        assert (result.returncode == 0) == success, (arguments, result.returncode, result.stderr)
        return result

    result = command(["pack", "--output-dir", bundle, one, two])
    assert json.loads(result.stdout)["records_verified"] == 2
    passed.append("CLI-pack-postwrite-exact-roundtrip")
    result = command(["verify", bundle])
    assert json.loads(result.stdout)["records_verified"] == 2
    passed.append("CLI-verify-complete-bundle")
    result = command(["restore", bundle, "one.mlfq", "--stdout"])
    assert result.stdout == first
    passed.append("CLI-restore-exact-stdout")
    output = directory / "restored.mlfq"
    command(["restore", bundle, "one.mlfq", "--output-file", output])
    assert output.read_bytes() == first
    passed.append("CLI-restore-exact-file")
    command(["restore", bundle, "two.mlfq", "--output-file", output], success=False)
    assert output.read_bytes() == first
    passed.append("CLI-refuses-output-file-overwrite")
    before = {path.name: path.read_bytes() for path in bundle.iterdir()}
    command(["pack", "--output-dir", bundle, one], success=False)
    assert before == {path.name: path.read_bytes() for path in bundle.iterdir()}
    passed.append("CLI-refuses-bundle-overwrite")
    duplicate_dir = directory / "duplicate"
    duplicate_dir.mkdir(); duplicate = duplicate_dir / one.name; duplicate.write_bytes(second)
    rejected = directory / "duplicate-output"
    command(["pack", "--output-dir", rejected, one, duplicate], success=False)
    assert not rejected.exists()
    passed.append("CLI-refuses-duplicate-basenames-before-write")
    malformed = directory / "malformed.mlfq"; malformed.write_bytes(b"\xff")
    rejected = directory / "malformed-output"
    command(["pack", "--output-dir", rejected, malformed], success=False)
    assert not rejected.exists()
    passed.append("CLI-refuses-invalid-input-before-write")
    rejected = directory / "optimized-tests"
    result = subprocess.run([sys.executable, "-I", "-B", "-O", str(Path(__file__)), "--output-dir", str(rejected)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
    assert result.returncode != 0 and not rejected.exists()
    assert len(result.stdout) + len(result.stderr) <= 65536
    passed.append("test-entrypoint-refuses-disabled-assertions")
    return dict(passed=len(passed), cases=passed)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run offline codec and synthetic CLI controls in a new directory.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("tests require assertions; do not use Python -O")
    codec_result = run(args.output_dir)
    cli_result = run_cli_smoke(args.output_dir / "cli-smoke")
    print(json.dumps(dict(codec=codec_result, cli=cli_result), sort_keys=True))
