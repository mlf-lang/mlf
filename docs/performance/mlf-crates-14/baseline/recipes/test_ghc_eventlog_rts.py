#!/usr/bin/env python3
"""Bounded synthetic GC eventlog controls; no compiler invocation."""
import json
from pathlib import Path
import struct
import ghc_eventlog_rts as R

E = R.E
u16 = lambda x: struct.pack('>H', x)
u32 = lambda x: struct.pack('>I', x)
u64 = lambda x: struct.pack('>Q', x)


def fixture(records, capability=0, allocated_schema=12):
    header = u32(E.HEADER_BEGIN) + u32(E.HET_BEGIN)
    for tag, size in [(18, 14), (19, -1), (9, 0), (10, 0), (49, allocated_schema), (51, 12), (53, 58)]:
        header += (u32(E.ET_BEGIN) + u16(tag) + struct.pack('>h', size) +
                   u32(1) + b'x' + u32(0) + u32(E.ET_END))
    header += u32(E.HET_END) + u32(E.HEADER_END) + u32(E.DATA_BEGIN)
    body = b''
    for tag, timestamp, value in records:
        payload = u32(0) + u64(value) if tag in (49, 51) else b''
        body += u16(tag) + u64(timestamp) + payload
    first = u16(18) + u64(1) + u32(24 + len(body)) + u64(500) + u16(capability)
    last = u16(18) + u64(2) + u32(26) + u64(1000) + u16(65535)
    return header + first + body + last + u16(E.DATA_END)


valid = [(49, 10, 100), (9, 20, None), (10, 40, None), (51, 42, 50),
         (49, 50, 200), (9, 60, None), (10, 90, None), (51, 92, 25)]
_, events = R.extract(fixture(valid))
result = R.summarize(events, 100)
assert result['gc_interval_count'] == 2 and result['gc_elapsed_overlay_ns'] == 50
assert result['heap_observations'][0]['last_reported_bytes'] == 200  # Not sample sum 300.
assert result['heap_observations'][1]['last_reported_bytes'] == 25
assert result['heap_observations'][1]['max_reported_bytes'] == 50
checks = [{'case': 'matched-GC-cumulative-allocation-not-summed-and-live-can-decrease', 'passed': True}]
for name, data, wall in [
    ('no-RTS-observations', fixture([]), 100),
    ('unclosed-GC', fixture([(9, 20, None)]), 100),
    ('unmatched-GC-end', fixture([(10, 20, None)]), 100),
    ('duplicate-GC-start', fixture([(9, 20, None), (9, 30, None), (10, 40, None)]), 100),
    ('allocation-counter-decrease', fixture([(49, 10, 200)] + valid[1:4] + [(49, 50, 100)]), 100),
    ('unsupported-other-capability', fixture(valid, capability=1), 100),
    ('unsupported-payload-schema', fixture([], allocated_schema=8), 100),
    ('GC-exceeds-process-wall', fixture(valid), 40),
    ('truncated-final-sentinel', fixture(valid)[:-1], 100),
]:
    try:
        R.summarize(R.extract(data)[1], wall)
    except E.InvalidEventlog:
        checks.append({'case': name, 'passed': True})
    else:
        raise AssertionError('Invalid RTS fixture accepted: ' + name)
report = {'complete': True, 'controls': checks, 'recipe_sha256': E.sha(R.__file__),
          'test_sha256': E.sha(__file__), 'validating_parser_sha256': E.sha(E.__file__)}
out = Path(__file__).resolve().parents[1] / 'evidence/ghc-eventlog-rts-controls.json'
out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
