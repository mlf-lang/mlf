#!/usr/bin/env python3
"""Tiny synthetic eventlog regression controls; never invokes a compiler."""
import io
import json
from pathlib import Path
import struct
import ghc_eventlog_phases as E

W = Path(__file__).resolve().parents[1]
u16 = lambda x: struct.pack('>H', x)
u32 = lambda x: struct.pack('>I', x)
u64 = lambda x: struct.pack('>Q', x)


def header():
    data = u32(E.HEADER_BEGIN) + u32(E.HET_BEGIN)
    for tag, size, name in [(18, 14, b'Block marker'), (19, -1, b'User message'),
                            (58, -1, b'User marker')]:
        data += (u32(E.ET_BEGIN) + u16(tag) + struct.pack('>h', size) +
                 u32(len(name)) + name + u32(0) + u32(E.ET_END))
    return data + u32(E.HET_END) + u32(E.HEADER_END) + u32(E.DATA_BEGIN)


def message(timestamp, text, tag=E.USER_MSG):
    payload = text.encode('utf-8')
    return u16(tag) + u64(timestamp) + u16(len(payload)) + payload


def fixture(messages, first_size_delta=0, final_size_delta=0):
    body = b''.join(message(*record) for record in messages)
    first = u16(E.BLOCK_MARKER) + u64(1) + u32(24 + len(body) + first_size_delta) + u64(500) + u16(0)
    # RTS endEventLogging adds the two-byte sentinel before closing this global block.
    last = u16(E.BLOCK_MARKER) + u64(2) + u32(26 + final_size_delta) + u64(1000) + u16(0xffff)
    return header() + first + body + last + u16(E.DATA_END)


valid = [(10, 'GHC:started: outer'), (20, 'GHC:started: inner'),
         (50, 'GHC:finished: inner'), (100, 'GHC:finished: outer'),
         (120, 'GHC:started: tail'), (150, 'GHC:finished: tail')]
checks = []
parsed = E.parse_stream(io.BytesIO(fixture(valid)))
result = E.reconstruct(parsed, 200)
assert result['phase_wall_coverage_ns'] == result['exact_exclusive_sum_ns'] == 120
assert result['process_residual_wall_ns'] == 80
assert result['unmarked_gaps_inside_phase_span_ns'] == 20
checks.append({'case': 'final-global-sentinel-included-and-nested-reconciliation', 'passed': True})
# Same labels are emitted first via traceMarkerIO, then via traceEventIO.
# Each underlying phase must occur once, and only USER_MSG timestamps count.
dual = [record for timestamp, label in valid
        for record in [(timestamp - 1, label, E.USER_MARKER), (timestamp, label, E.USER_MSG)]]
dual_result = E.reconstruct(E.parse_stream(io.BytesIO(fixture(dual))), 200)
assert dual_result['phase_count'] == 3
assert dual_result['marker_count'] == dual_result['diagnostic_marker_count'] == 6
assert dual_result['all_channel_marker_count'] == 12
assert dual_result['phase_wall_coverage_ns'] == result['phase_wall_coverage_ns']
assert dual_result['by_label'] == result['by_label']
checks.append({'case': 'dual-channels-no-doublecount-USER_MSG-timestamps-only', 'passed': True})
for name, data in [
    ('truncated-sentinel', fixture(valid)[:-1]),
    ('bad-nonfinal-block-length', fixture(valid, first_size_delta=2)),
    ('final-block-incorrectly-excludes-sentinel', fixture(valid, final_size_delta=-2)),
    ('final-block-other-overrun', fixture(valid, final_size_delta=1)),
    ('unclosed-phase', fixture(valid[:-1])),
    ('mismatched-finish', fixture([(10, 'GHC:started: a'), (20, 'GHC:finished: b')])),
    ('unmatched-finish', fixture([(10, 'GHC:finished: a')])),
    ('trailing-data', fixture(valid) + b'x'),
    ('no-phase-markers', fixture([])),
    ('marker-channel-only-is-not-authoritative', fixture([(t, s, E.USER_MARKER) for t, s in valid])),
    ('other-channel-does-not-repair-selected-channel', fixture(dual[:-1])),
]:
    try:
        E.reconstruct(E.parse_stream(io.BytesIO(data)))
    except E.InvalidEventlog:
        checks.append({'case': name, 'passed': True})
    else:
        raise AssertionError('Invalid eventlog accepted: ' + name)
try:
    E.reconstruct(parsed, 130)  # Coverage 120 fits; complete timestamp span 140 does not.
except E.InvalidEventlog:
    checks.append({'case': 'phase-span-exceeds-process-wall', 'passed': True})
else:
    raise AssertionError('Invalid supplied process duration accepted')

evidence = W / 'evidence'
evidence.mkdir(exist_ok=True)
(evidence / 'ghc-final-block-valid.eventlog').write_bytes(fixture(valid))
(evidence / 'ghc-final-block-invalid.eventlog').write_bytes(fixture(valid, final_size_delta=-2))
(evidence / 'ghc-dual-channel-valid.eventlog').write_bytes(fixture(dual))
report = {'complete': True, 'synthetic_controls': checks,
          'parser_sha256': E.sha(Path(E.__file__)), 'test_sha256': E.sha(__file__),
          'regression': {'actual_final_block_offset': 6681408,
                         'actual_final_block_declared_bytes': 468,
                         'actual_DATA_END_offset': 6681874,
                         'actual_file_bytes': 6681876,
                         'rule': '468 = 6681876 - 6681408, including the final two sentinel bytes.',
                         'source': E.RTS_ENCODING_SOURCE,
                         'functions': ['endEventLogging', 'closeBlockMarker', 'printAndClearEventBuf']},
          'actual_GHC_eventlog_evidence': str(evidence / 'ghc-eventlog-phase-wall.json')}
(evidence / 'ghc-eventlog-parser-controls.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
