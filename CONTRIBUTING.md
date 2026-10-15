# Contributing

Use issues for reproducible compiler or tooling defects and
[discussions](https://github.com/orgs/mlf-lang/discussions) for language design
and ecosystem questions. Include a small `.emlf` program, the command, expected
result, actual result, platform, and toolchain version.

Install a published native seed, Clang, GMP, pkg-config, and BDWGC. Follow
[the package manager guide](docs/package-manager.md) to build and test with MLF:

```sh
export MLF_COMPILER=/absolute/path/to/installed/bin/emlf
export MLF_PACKAGE_MANAGER=/absolute/path/to/installed/bin/mlfpkg
export MLF_GC_PREFIX="$(brew --prefix bdw-gc)"
./mlfpkg --locked build
./mlfpkg --timeout 21600 test
```

Use `./mlfpkg lock` after intentional manifest or source changes. Do not regenerate
independent test oracles from the compiler being tested. See
[test coverage](tests/README.md), [release instructions](docs/releases.md), and
[the changelog](CHANGELOG.md). Keep changes focused and explain the validation
performed in the pull request.
