# Contributing

For routine cleanup, tool and test consolidation, or directory improvements,
follow the [daily housekeeping guide](docs/housekeeping.md).

Use issues for reproducible compiler or tooling defects and
[discussions](https://github.com/orgs/mlf-lang/discussions) for language design
and ecosystem questions. Include a small `.emlf` program, the command, expected
result, actual result, platform, and toolchain version.

## Developer commands

Run `python3 tools/dev.py --help` to see the build, test and benchmark entry
points. Paths in these commands are relative to the checkout root.

| Command | Work performed |
| --- | --- |
| `python3 tools/dev.py build` | Locked native package build using the selected stage-1 compiler and manager |
| `python3 tools/dev.py test` | Native package tests, with a six-hour timeout per build action |
| `python3 tools/dev.py test --target unit` | One native test target. Repeat `--target` to select more |
| `python3 tools/dev.py build-host` | Build the GHC-hosted compiler and fixed native standard library |
| `python3 tools/dev.py check-tools` | Developer command, paired benchmark, and worker cleanup tests |
| `python3 tools/dev.py bench shapes` | Prepare the GHC-hosted bootstrap compiler, then run the standard MLF/GHC compilation matrix |
| `python3 tools/dev.py bench apps --baseline PATH --output DIR` | Build the native application benchmark driver, then compare the candidate, baseline and C implementations |

For native build and test, install a published seed, Clang, GMP, pkg-config
and BDWGC. Follow the [package manager guide](docs/package-manager.md) to
build the stage-1 tools. Set `MLF_COMPILER` and `MLF_PACKAGE_MANAGER` to their
absolute paths, and `MLF_GC_PREFIX` if required for your installation.
The native launchers also work directly without Python.

On macOS and Linux, interrupting `check-tools` stops the active test script
and its workers. On Windows the developer commands share the console. Use
Ctrl+C to interrupt the checks there. Forcibly terminating just the Windows
launcher process can leave its active Python script running.

The [compiler-shape benchmark](tools/performance/compiler-shapes/README.md)
runs on macOS and Linux with GHC 9.14.1. Preview the matrix with
`python3 tools/dev.py bench shapes list`. A fresh default run writes
`.mlf-build/compiler-shapes/summary.md` and `summary.csv`. To reuse the fixed
dependencies and record another comparison:

```sh
python3 tools/dev.py bench shapes --workdir .mlf-build/shape-repeat \
  --setup .mlf-build/compiler-shapes/setup/setup.json --family wide_case --size 128
```

The [application benchmark](tools/bench/README.md) uses the native
`tools/bench` package, BDWGC, GMP and pinned PCRE2. Supply a separate baseline
compiler and a fresh output directory. The candidate defaults to
`.mlf-build/bin/emlf`. Use `bench apps --help` for candidate, Clang, workload
and correctness-only selection. Workflow orchestration stays outside timed
compilations and application runs.

## Skipping pull request CI

See [Skipping pull request CI](docs/ci.md#skipping-pull-request-ci) for the
`ci:skip` label and how to interpret the resulting **PR gate**.

## Where changes belong

- Put compiler and package-manager implementation in `libraries/mlf-*/`. The
  `bootstrap/` and `package/` directories contain executable entry points.
- Put compiler conformance cases and fixtures in [tests/](tests/README.md).
  The reusable assertion, case and runner APIs live in [testing/](testing/README.md).
- Put scalable compiler fixtures and their output oracles in
  [compiler-shapes](tools/performance/compiler-shapes/README.md). Application
  benchmark sources, inputs and pins live in [benchmarks/](benchmarks/README.md).
  The native application benchmark driver lives in [tools/bench/](tools/bench/README.md).
- Put GHC-hosted compiler construction and qualification in `tools/shared/`,
  release and packaging commands in `tools/release/`, and local results under
  the ignored `.mlf-build/` directory.

Use `./mlfpkg lock` after intentional manifest or source changes. Do not regenerate
independent test oracles from the compiler being tested. See
[test coverage](tests/README.md), [release instructions](docs/releases.md), and
[the changelog](CHANGELOG.md). Keep changes focused and explain the validation
performed in the pull request.
