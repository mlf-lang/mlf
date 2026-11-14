"""Current schema8 Session boundary; the original C4 byte gate is untouched.

This gate requires exact same-format audit bytes, not schema7-to-8 migration.
"""
from pathlib import Path
import os
import re

import open_file_comparison as Comparison

HERE = Path(__file__).resolve().parent
SUFFIXES = ('.mlfci', '.mlfco')
FROZEN_INPUTS = {
    'run_controls.py': 'cf7b83d81db2a591fac5bb042b4e12e0effbab6239ecb8ef9a1f8741ffd6bb20',
    'controls/FileControls.hs': '86fb166dabbff970025e5201a58905b220e73aa5f8e4d709be277a32256b755a',
    'fixtures/file-cases.json': 'b7878c17609b3c7bf59e4b9a8942b0df61ea2d691edab7de97b102fabe1a94f8',
}


def raw_files(prefix):
    return {suffix: Path(str(prefix) + suffix).read_bytes() for suffix in SUFFIXES}


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def same_group_ownership(crate, expected, actual):
    """Compare full ordered memberships while validating each format's owner."""
    if len(expected) != len(actual):
        return False
    seen = set()
    for closed, opened in zip(expected, actual):
        members = closed['members']
        if not members or members != opened['members'] or len(set(members)) != len(members):
            return False
        encoded = lambda value: ''.join(str(ord(char)) + '_' for char in value)
        legacy = 'Query_' + encoded(crate) + 'z_' + encoded(members[0])
        owner = pack(['MLF-OPEN-GROUP-1', crate, pack(sorted(members))])
        if closed['id'] != legacy or opened['id'] != owner or owner in seen:
            return False
        seen.add(owner)
    return True


def unpack(source):
    result = []
    while source:
        colon = source.find(':')
        if colon < 1 or not source[:colon].isdigit():
            raise ValueError('malformed retained crate spec')
        count = int(source[:colon])
        start = colon + 1
        if len(source) - start < count:
            raise ValueError('truncated retained crate spec')
        result.append(source[start:start + count])
        source = source[start + count:]
    return result


def verify_producer_objects(H, producer, auth):
    actual = {str(Path(path).relative_to(producer)): digest
              for path, digest in H.file_pins(producer / 'objects').items()}
    H.require(actual == auth['object_inputs'],
              'complete retained producer object inventory matches its receipt')
    return actual


def verify_c_support(H, output, source, producer, auth, folder, inputs, record, save, limits):
    """Reproduce the two support objects; old receipts do not pin their bytes."""
    checks = record.setdefault('reproducible_c_support', {})
    key = str(producer)
    if key in checks:
        H.require(checks[key]['complete'] and checks[key]['source'] == str(source),
                  'same previously verified C-support producer/source')
        H.check_pins(checks[key]['pins'])
        return
    result = {'complete': False, 'source': str(source), 'pins': {}, 'objects': [],
              'scope': 'Reproducible C-object verification, not receipt-hash authentication.'}
    checks[key] = result
    save()
    support = folder / 'support-verification'
    support.mkdir()
    for name, relative in [('host', 'host/ghc/cbits/host.c'),
                           ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        original = producer / (name + '.o')
        expected = [auth['cc']['path'], '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                    '-c', str(source / relative), '-o', str(original)]
        commands = [row for row in auth['commands']
                    if Path(row['log']).name == 'c-' + name + '.log']
        H.require(len(commands) == 1 and commands[0]['exit_code'] == 0 and
                  commands[0]['cwd'] == str(source) and commands[0]['argv'] == expected,
                  'one exact successful authenticated C compilation')
        command = commands[0]
        H.require(H.sha(command['log']) == command['log_sha256'],
                  'original C compilation log unchanged')
        inputs[str(Path(command['log']))] = command['log_sha256']
        original = H.regular(original)
        old_bytes = original.read_bytes()
        rebuilt = support / (name + '.o')
        argv = list(expected)
        argv[-1] = str(rebuilt)
        H.require(argv[:-1] == command['argv'][:-1], 'only the C output operand changes')
        log = support / ('compile-' + name)
        try:
            H.Runner(output, limits).run(argv, source, log)
        finally:
            if (log / 'command.json').exists():
                result['objects'].append(H.load(log / 'command.json'))
                save()
        H.require(rebuilt.read_bytes() == old_bytes == original.read_bytes(),
                  'entire reproduced C object equals unchanged retained object')
        for path in [original, rebuilt]:
            digest = H.sha(path)
            inputs[str(path)] = digest
            result['pins'][str(path)] = digest
        save()
    result['complete'] = True
    save()


def verify_compiled_controls(H, so, se, folder):
    compiled = re.findall(
        r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),',
        (so + se).decode(), re.M)
    actual = [(name, str(Path(path.strip()).resolve())) for name, path in compiled]
    expected = {'FileControls': str((folder / 'FileControls.hs').resolve()),
                'Main': str((folder / 'Main.hs').resolve())}
    H.require(len(actual) == len(expected) and dict(actual) == expected,
              'exact FileControls/Main compilation origins only; no production recompilation')


def native_negative_controls(H, output, folder, viewer, source, closed_files, open_files,
                             run, record, save):
    results = []
    record['native_negative_controls'] = results
    cases = Comparison.make_native_negatives(closed_files, open_files)
    H.require([case['name'] for case in cases] ==
              ['receipt-sha-recomputed', 'used-inventory-sha-recomputed', 'old-object-checksum'],
              'all three native boundary controls')
    for case in cases:
        destination = folder / ('negative-' + case['name'])
        destination.mkdir()
        prefixes = {}
        for side, files in [('closed', case['closed_files']), ('open', case['open_files'])]:
            prefix = destination / side
            prefixes[side] = prefix
            H.require(set(files) == set(SUFFIXES), 'negative artifact pair')
            for suffix, raw in files.items():
                Path(str(prefix) + suffix).write_bytes(raw)
        views = destination / 'views'
        views.mkdir()
        row = {'name': case['name'], 'complete': False,
               'expected_helper_exit': case['expected_helper_exit'],
               'input_sha256': {side: {suffix: H.sha(str(prefix) + suffix)
                                      for suffix in SUFFIXES}
                                for side, prefix in prefixes.items()}}
        results.append(row)
        save()
        so, se = run(str(destination.relative_to(output)) + '/command',
                     [viewer, prefixes['closed'], prefixes['open'], views],
                     source, expected_exit=case['expected_helper_exit'])
        H.require(raw_files(prefixes['closed']) == case['closed_files'] and
                  raw_files(prefixes['open']) == case['open_files'],
                  'native negative inputs remained byte-for-byte unchanged')
        row.update(stdout=so.decode(), stderr=se.decode(),
                   outputs={p.name: H.sha(p) for p in sorted(views.iterdir()) if p.is_file()})
        save()
        if case['expected_helper_exit'] != 0:
            H.require(case['required_error_fragment'].encode() in se,
                      'native failure is the intended admission/audit rejection')
        else:
            match = re.fullmatch(rb'PASS C4 public views ([0-9]+) ([0-9]+)\n', so)
            H.require(match is not None and se == b'', 'used-inventory native audit completed')
            H.require(raw_files(views / 'audited-open') == open_files and
                      raw_files(views / 'audited-open') != case['open_files'],
                      'returned audited fragment reconstructs the exact original open bytes')
            dependencies = sorted(views.glob('dependency-*.mlfci'))
            H.require({p.name for p in dependencies} ==
                      {'dependency-' + str(i) + '.mlfci' for i in range(int(match[2]))},
                      'complete native negative dependency snapshots')
            try:
                Comparison.compare_open_file(
                    case['closed_files'], case['open_files'],
                    [p.read_bytes() for p in dependencies], raw_files(views / 'audited-open'),
                    (views / 'crate.xterm-v6.bin').read_bytes(),
                    (views / 'session.xterm-v6.bin').read_bytes(), entry_selection=True)
            except Comparison.ComparisonError as error:
                H.require('used-name inventory' in str(error),
                          'independent used-name rejection is the intended failure')
                row['comparison_rejection'] = str(error)
            else:
                H.require(False, 'corrupt used-name inventory escaped the complete comparator')
        row['complete'] = True
        save()
    H.require(len(results) == 3 and all(row['complete'] for row in results),
              'all native corrupted-artifact controls completed')


def build_views(H, output, source, producer, auth, inputs, limits, run):
    folder = output / 'session'
    objects = folder / 'objects'
    helper = HERE / 'C4ArtifactViews.hs'
    inputs[str(helper)] = H.sha(helper)
    immutable = {path: digest for path, digest in H.file_pins(objects).items()
                 if Path(path).name not in ('Main.o', 'Main.hi')}
    flags = []
    for token in auth['flags']:
        flags.append(str(objects) if token == str(producer / 'objects') else token)
        if token == '-i':
            flags.append('-i' + str(HERE))
    binary = folder / 'artifact-views'
    so, se = run('session/build-artifact-views',
                 [auth['ghc']['path'], '--make', '-j1', *flags, helper,
                  producer / 'host.o', producer / 'supervisor.o', '-o', binary],
                 source)
    compiled = re.findall(
        r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),',
        (so + se).decode(), re.M)
    H.require([(name, str(Path(path.strip()).resolve())) for name, path in compiled] ==
              [('Main', str(helper.resolve()))],
              'only the test helper compiled; no production recompilation')
    H.check_pins(immutable)
    inputs[str(binary)] = H.sha(binary)
    return binary, immutable


def run_session_files(H, output, record, inputs, binaries, producer, source,
                      auth, builtin, save, limits):
    """Reuse the complete, already passed ordinary gate's exact sources/oracles."""
    output = output.resolve()
    baseline = record['routes']['crate']['file_cases']
    fixture_path = HERE.parent / 'c4-local-transaction/fixtures/file-cases.json'
    for relative, digest in FROZEN_INPUTS.items():
        H.require(H.sha(HERE.parent / 'c4-local-transaction' / relative) == digest,
                  'unchanged frozen C4 source: ' + relative)
    authored = H.load(fixture_path)
    H.require(len(baseline) == authored['case_count'] == len(authored['cases']) == 9 and
              all(row['complete'] and row['actual_raw_artifact_bytes_equal']
                  for row in baseline), 'the original nine-case raw byte gate passed first')
    for name, digest in Comparison.ORACLE_PINS.items():
        path = Comparison.ORACLE_DIRECTORY / name
        H.require(H.sha(path) == digest, 'fixed independent oracle: ' + name)
        inputs[str(path)] = digest
    inputs[str(Comparison.DEPENDENCY_ORACLE_PATH)] = H.sha(Comparison.DEPENDENCY_ORACLE_PATH)
    for path in [Path(__file__), HERE / 'open_file_comparison.py',
                 HERE / 'frozen_file_oracles.py', fixture_path]:
        inputs[str(path)] = H.sha(path)
    rows = {'complete': False, 'scope': 'explicit closed/open boundary; complete content and '
            'linked structures; exact same-format fresh/fresh, warm and audited bytes',
            'file_cases': [], 'commands': []}
    record['routes']['session'] = rows
    rows['independent_dependency_schema_extension'] = {
        'source_sha256': Comparison.ORACLE_PINS['artifact_binary_typed.py'],
        'adapted_sha256': H.sha(Comparison.DEPENDENCY_ORACLE_PATH),
        'scope': 'only dependency-interface primitive declarations 132/133 with exact Prelude owner and names; unchanged 0..131 reader for own artifacts and linked terms',
        'exact_source_inverse_verified': True}
    save()

    def run(label, argv, cwd, expected_exit=0):
        log = output / label
        try:
            result = H.Runner(output, limits).run(argv, cwd, log, expected_exit=expected_exit)
        finally:
            if (log / 'command.json').exists():
                rows['commands'].append(H.load(log / 'command.json'))
                save()
        return (log / 'stdout').read_bytes(), (log / 'stderr').read_bytes()

    viewer, immutable = build_views(H, output, source, producer, auth,
                                    inputs, limits, run)
    comparison_root = output / 'compare-session'
    comparison_root.mkdir()
    for index, (case, original) in enumerate(zip(authored['cases'], baseline)):
        H.require(case['name'] == original['name'], 'original ordered case inventory')
        expected = original['outcomes'][0]
        H.require(expected['side'] == 'base', 'original reference outcome')
        original_folder = output / 'compare-crate/files' / case['name'] / 'base'
        closed_prefix = original_folder / 'unit'
        original_spec = original_folder / 'crate.spec'
        fields = unpack(original_spec.read_text())
        H.require(len(fields) == 8 and fields[0] == 'MLF-CRATE-1' and
                  fields[7] == str(builtin), 'unchanged original spec and builtin')
        source_pairs = [unpack(value) for value in unpack(fields[4])]
        H.require(all(len(pair) == 2 for pair in source_pairs), 'exact original source pairs')
        missing = [Path(path) for module, path in source_pairs
                   if module in case.get('missing_modules', [])]
        H.require(all(not os.path.lexists(path) for path in missing), 'original missing files absent')
        for suffix in SUFFIXES + ('.queries',):
            path = Path(str(closed_prefix) + suffix)
            if path.exists():
                inputs[str(path)] = H.sha(path)
        if case['expected_type'] != 'reject':
            H.require({suffix: H.sha(str(closed_prefix) + suffix) for suffix in SUFFIXES}
                      == expected['artifacts'], 'passed reference bytes still present')
        folder = comparison_root / case['name']
        folder.mkdir()
        row = {'name': case['name'], 'complete': False, 'outcomes': [],
               'baseline_prefix': str(closed_prefix)}
        rows['file_cases'].append(row)
        save()
        cold_files = None
        modes = ['cold'] if case['expected_type'] == 'reject' else ['cold', 'fresh-repeat', 'warm']
        for mode in modes:
            destination = folder / mode
            destination.mkdir()
            prefix = destination / 'unit'
            cache = folder / ('cold-cache' if mode == 'cold' else 'repeat-cache')
            if mode == 'warm':
                H.require(cache.is_dir(), 'warm reuses the actual second session cache')
            else:
                H.require(not os.path.lexists(cache), 'genuinely fresh session cache')
            actual_fields = list(fields)
            actual_fields[6] = str(cache)
            spec = destination / 'crate.spec'
            spec.write_text(pack(actual_fields))
            inputs[str(spec)] = H.sha(spec)
            H.require([value for i, value in enumerate(unpack(spec.read_text())) if i != 6] ==
                      [value for i, value in enumerate(fields) if i != 6],
                      'only query cache location changes from the original spec')
            so, se = run(str(destination.relative_to(output)) + '/command',
                         [binaries['session'], spec, prefix, case['expected_type']], destination)
            outcome = {'mode': mode, 'prefix': str(prefix), 'stdout': so.decode(),
                       'stderr': se.decode(), 'complete': False, 'artifacts': {}}
            row['outcomes'].append(outcome)
            for suffix in SUFFIXES:
                path = Path(str(prefix) + suffix)
                if path.exists():
                    outcome['artifacts'][suffix] = {'bytes': path.stat().st_size,
                                                    'sha256': H.sha(path)}
            save()  # Keep actual outputs even when the next assertion fails.
            H.require(so == expected['stdout'].encode() and se == b'',
                      'complete original diagnostics and handwritten status/type oracle')
            if case['expected_type'] == 'reject':
                H.require(all(not os.path.lexists(str(prefix) + suffix) for suffix in SUFFIXES),
                          'rejected case publishes no artifacts')
            else:
                report = H.load(str(prefix) + '.queries')
                outcome['query_report'] = report
                outcome['query_report_sha256'] = H.sha(str(prefix) + '.queries')
                save()
                groups = report['groups']
                inferred, reused = report['inferred_groups'], report['reused_groups']
                H.require(type(inferred) is int and type(reused) is int, 'integer query counts')
                if mode == 'warm':
                    H.require(inferred == 0 and reused > 0 and len(groups) == reused and
                              all(group['cached'] is True for group in groups),
                              'genuine complete warm reuse')
                else:
                    H.require(inferred > 0 and reused == 0 and len(groups) == inferred and
                              all(group['cached'] is False for group in groups),
                              'genuinely fresh inference')
                H.require(report['crate'] == fields[1] and
                          same_group_ownership(fields[1], expected['groups'], groups),
                          'complete ordered original inference groups and exact owner formats')
                actual = raw_files(prefix)
                if mode == 'cold':
                    cold_files = actual
                    cold_prefix = prefix
                    for suffix in SUFFIXES:
                        inputs[str(Path(str(prefix) + suffix))] = H.sha(str(prefix) + suffix)
                else:
                    H.require(actual == cold_files, 'complete same-format artifact bytes: ' + mode)
                    outcome['whole_artifact_bytes_equal'] = True
            outcome['complete'] = True
            save()
        if case['expected_type'] != 'reject':
            views = folder / 'views'
            views.mkdir()
            so, se = run(str(views.relative_to(output)) + '/command',
                         [viewer, closed_prefix, cold_prefix, views], source)
            row['public_view_stdout'] = so.decode()
            row['public_view_stderr'] = se.decode()
            row['view_files'] = {str(path.relative_to(views)): {'bytes': path.stat().st_size,
                                  'sha256': H.sha(path)}
                                 for path in sorted(views.iterdir()) if path.is_file()}
            save()
            match = re.fullmatch(rb'PASS C4 public views ([0-9]+) ([0-9]+)\n', so)
            H.require(match is not None and se == b'', 'complete actual public reader/link/audit')
            fragments, dependency_count = map(int, match.groups())
            dependency_paths = sorted(views.glob('dependency-*.mlfci'))
            H.require({path.name for path in dependency_paths} ==
                      {'dependency-' + str(i) + '.mlfci' for i in range(dependency_count)},
                      'exact complete dependency snapshots')
            audited = raw_files(views / 'audited-open')
            H.require(audited == cold_files, 'actual audit rebuild preserves all open bytes')
            row['comparison'] = Comparison.compare_open_file(
                raw_files(closed_prefix), cold_files,
                [path.read_bytes() for path in dependency_paths], audited,
                (views / 'crate.xterm-v6.bin').read_bytes(),
                (views / 'session.xterm-v6.bin').read_bytes(), entry_selection=True)
            H.require(row['comparison']['open_wire_schema'] == 8,
                      'current Session C4 writer emits schema8')
            H.require(row['comparison']['fragment_count'] == fragments,
                      'public and independent complete fragment inventory')
            row['cross_format_raw_bytes_equal'] = raw_files(closed_prefix) == cold_files
            row['same_format_fresh_fresh_and_warm_bytes_equal'] = True
            row['audited_open_complete_bytes_equal'] = True
            if index == 0:
                native_negative_controls(H, output, folder, viewer, source,
                                         raw_files(closed_prefix), cold_files, run, rows, save)
        H.require(all(not os.path.lexists(path) for path in missing),
                  'missing-source fixtures stayed absent after Session')
        H.check_pins(inputs)
        H.check_pins(immutable)
        row['complete'] = True
        save()
    H.require(len(rows['file_cases']) == 9 and all(row['complete'] for row in rows['file_cases']),
              'all nine retained session cases completed')
    rows['complete'] = True
    save()
