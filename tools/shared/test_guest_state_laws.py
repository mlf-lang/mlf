#!/usr/bin/env python3
"""Run maintained Graph/Oracle laws through actual imports on authenticated O2 MLF.

Four sequential stages normally total about 90 seconds; the safety watchdog is
90 seconds PER STAGE, not a 90-second campaign claim. No compiler-within-compiler,
LLVM emission, copied state implementation, or full native/unit qualification.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from test_direct import authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import identity, select

WATCHDOG = ROOT/'tools/shared/resource_watchdog.py'
FLAGS = ('MLF_GRAPH_BUILD_NEGATIVE', 'MLF_ORACLE_TRAVERSAL_NEGATIVE')
CASES = (
    ('graph-build', 'GraphBuildLaws.emlf', FLAGS[0],
     ('libraries/mlf-foundation', 'libraries/mlf-language-core', 'libraries/mlf-inference', 'tests'),
     b'PASS graph build standard classes (14 checks)\n', b'FAIL graph build: pure/oracle\n'),
    ('oracle-traversal', 'OracleTraversalLaws.emlf', FLAGS[1],
     ('libraries/mlf-foundation', 'tests'),
     b'PASS oracle traversal (4 checks)\n', b'FAIL oracle traversal: fresh order/oracle\n'))
LIMITS = {'wall_seconds': 90, 'address_space_per_process': 3*1024**3,
          'process_tree_rss_bytes': 1536*1024**2, 'host_available_floor': 3*1024**3,
          'disk_free_floor': 3*1024**3, 'max_output_bytes': 100*1024**2}

def require(value, message):
    if not value:
        raise ValueError(message)

def verify_observation(resource, status, log, expected):
    require(set(LIMITS) <= set(resource.get('limits', {})) and resource['limits'] == LIMITS,
            'resource contract changed')
    require('reason' in resource and resource['reason'] is None, 'resource failure is not a law result')
    require(type(resource.get('exit_code')) is int and resource['exit_code'] == status,
            'unexpected child status')
    require(resource.get('complete') is (status == 0), 'inconsistent completion status')
    require(resource.get('elapsed_seconds', 91) < 90 and
            resource.get('peak_group_rss', LIMITS['process_tree_rss_bytes']+1) <= LIMITS['process_tree_rss_bytes'],
            'resource measurement exceeds bounds')
    samples = resource.get('samples', [])
    require(bool(samples), 'missing resource samples')
    for sample in samples:
        require(sample.get('host_available', 0) >= LIMITS['host_available_floor'] and
                sample.get('disk_free', 0) >= LIMITS['disk_free_floor'] and
                sample.get('group_rss', LIMITS['process_tree_rss_bytes']+1) <= LIMITS['process_tree_rss_bytes'] and
                sample.get('output_bytes', LIMITS['max_output_bytes']+1) <= LIMITS['max_output_bytes'],
                'resource sample exceeds bounds')
    require(log == expected, 'law output differs from exact oracle')
    if status == 1:
        require(b'PASS' not in log and log.startswith(b'FAIL '), 'invalid negative control output')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    labels = [label + suffix for label, *_ in CASES for suffix in ('-positive', '-negative')]
    selected = select('guest-state-laws/', labels)
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir = receipt.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'kind': 'actual-import-guest-state-laws', 'commands': [],
              'full_native_unit': False, 'native_or_llvm_output': False,
              'per_stage_limits': LIMITS}
    if selected:
        record.update(scope='focused', selected_ids=[identity('guest-state-laws/', selected)])
    else:
        record['expected_campaign_seconds_approximate'] = 90.5
    def save():
        temporary = output/'receipt.json.tmp'
        temporary.write_text(json.dumps(record, indent=2)+'\n')
        temporary.replace(output/'receipt.json')
    try:
        producer = authenticate_build(receipt, producer_dir/'bin')
        require(producer['optimization'] == '2', 'state-law gate requires authenticated O2 producer')
        compiler = producer_dir/'bin/emlf'
        record.update(producer_receipt_sha256=sha(receipt), compiler=producer['outputs']['emlf'])
        save()
        results = {}
        for label, fixture, flag, roots, positive, negative in CASES:
            for failure in [False, True]:
                stage = label + ('-negative' if failure else '-positive')
                if selected and stage != selected:
                    continue
                directory = output/stage
                directory.mkdir()
                command = [str(compiler)]
                for root in roots:
                    command.extend(['-i', str(ROOT/root)])
                command.extend(['--run', str(ROOT/'tools/shared/fixtures'/fixture)])
                flags = {name: '0' for name in FLAGS}
                flags[flag] = '1' if failure else '0'
                environment = dict(os.environ, **flags)
                row = {'label': stage, 'command': command, 'environment_overrides': flags,
                       'expected_exit': 1 if failure else 0, 'complete': False}
                record['commands'].append(row)
                save()
                supervised = [sys.executable, str(WATCHDOG), '--seconds', '90', '--address-space-mib', '3072',
                              '--rss-mib', '1536', '--disk-free-mib', '3072', '--max-output-mib', '100',
                              str(directory), 'nice', '-n', '19', 'ionice', '-c', '3', *command]
                result = subprocess.run(supervised, cwd=ROOT, env=environment, capture_output=True)
                (directory/'supervisor.stdout').write_bytes(result.stdout)
                (directory/'supervisor.stderr').write_bytes(result.stderr)
                resource_path = directory/'bounded-receipt.json'
                log_path = directory/'build.log'
                resource = json.loads(resource_path.read_text())
                expected_status = 1 if failure else 0
                verify_observation(resource, expected_status, log_path.read_bytes(), negative if failure else positive)
                require(result.returncode == expected_status, 'watchdog process status mismatch')
                results[str(resource_path)] = sha(resource_path)
                results[str(log_path)] = sha(log_path)
                row.update(complete=True, expected_negative_control=failure,
                           elapsed_seconds=resource['elapsed_seconds'],
                           resource_receipt_sha256=results[str(resource_path)], log_sha256=results[str(log_path)])
                save()
        require(all(sha(path) == expected for path, expected in results.items()), 'recorded result changed')
        record.update(complete=True, result_files=results,
                      observed_campaign_seconds=sum(row['elapsed_seconds'] for row in record['commands']))
        save()
        summary = {'complete': True, 'stages': len(record['commands']), 'full_native_unit': False}
        if selected:
            summary['selected_ids'] = record['selected_ids']
        else:
            summary.update(positive_law_checks=18, negative_controls=2)
        print(json.dumps(summary))
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error)
        save()
        raise

if __name__ == '__main__':
    main()
