#!/usr/bin/env python3
"""Read existing single-capability GHC eventlog GC/heap observations; no compiler run."""
import argparse
import collections
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import ghc_eventlog_phases as E

SCHEMAS = {9: 0, 10: 0, 49: 12, 51: 12, 53: 58}
NAMES = {9: 'GC_START', 10: 'GC_END', 49: 'HEAP_ALLOCATED', 51: 'HEAP_LIVE', 53: 'GC_STATS_GHC'}


def extract(data):
    # Validate the entire immutable in-memory snapshot using the reviewed parser,
    # including blocks, event sizes, timestamps, final sentinel and trailing data.
    parsed = E.parse_stream(io.BytesIO(data))
    for tag, size in SCHEMAS.items():
        if tag in parsed['event_types']:
            E.require(parsed['event_types'][tag]['size'] == size,
                      'Unsupported RTS payload schema: ' + NAMES[tag])
    reader = E.Reader(io.BytesIO(data))
    reader.stream.seek(parsed['data_start_offset'])
    events, capability = [], None
    while True:
        offset = reader.tell()
        tag = reader.number('H')
        if tag == E.DATA_END:
            break
        timestamp = reader.number('Q')
        size = parsed['event_types'][tag]['size']
        payload = reader.take(reader.number('H') if size == -1 else size)
        if tag == E.BLOCK_MARKER:
            capability = struct.unpack('>IQH', payload[:14])[2]
            capability = None if capability == 65535 else capability
        elif tag in SCHEMAS:
            event = {'tag': tag, 'timestamp_ns': timestamp, 'offset': offset, 'capability': capability}
            if tag in (49, 51):
                event['capset'], event['bytes'] = struct.unpack('>IQ', payload)
            elif tag == 53:
                event['capset'], event['generation'] = struct.unpack('>IH', payload[:6])
            events.append(event)
    return parsed, sorted(events, key=lambda e: (e['timestamp_ns'], e['offset']))


def summarize(events, process_wall_ns=None):
    E.require(events, 'No selected RTS GC/heap events; observations unavailable')
    E.require({e['capability'] for e in events} == {0},
              'Only single capability 0 is supported; do not sum parallel GC elapsed intervals')
    starts, intervals, heaps = None, [], collections.defaultdict(list)
    generations = collections.Counter()
    for event in events:
        tag = event['tag']
        if tag == 9:
            E.require(starts is None, 'Nested or duplicate GC_START')
            starts = event
        elif tag == 10:
            E.require(starts is not None, 'Unmatched GC_END')
            E.require(event['timestamp_ns'] >= starts['timestamp_ns'], 'Negative GC duration')
            intervals.append({'start_ns': starts['timestamp_ns'], 'end_ns': event['timestamp_ns'],
                              'wall_ns': event['timestamp_ns'] - starts['timestamp_ns']})
            starts = None
        elif tag in (49, 51):
            heaps[(tag, event['capset'], event['capability'])].append(event)
        elif tag == 53:
            generations[event['generation']] += 1
    E.require(starts is None, 'Unclosed GC_START')
    E.require(intervals, 'No complete GC_START/GC_END intervals')
    total = sum(i['wall_ns'] for i in intervals)
    if process_wall_ns is not None:
        E.require(total <= process_wall_ns, 'GC intervals exceed process wall')
    heap_summary = []
    for (tag, capset, capability), samples in sorted(heaps.items()):
        if tag == 49:
            E.require(all(a['bytes'] <= b['bytes'] for a, b in zip(samples, samples[1:])),
                      'Cumulative HEAP_ALLOCATED decreased; restart/reset unsupported')
        heap_summary.append({'event': NAMES[tag], 'capset': capset, 'capability': capability,
                             'sample_count': len(samples),
                             'first_reported_bytes': samples[0]['bytes'],
                             'last_reported_bytes': samples[-1]['bytes'],
                             'max_reported_bytes': max(s['bytes'] for s in samples),
                             'first_report_timestamp_ns': samples[0]['timestamp_ns'],
                             'last_report_timestamp_ns': samples[-1]['timestamp_ns']})
    return {'format': 'ghc-eventlog-rts-observations-v1', 'complete': True,
            'capabilities': [0], 'event_counts': dict(collections.Counter(NAMES[e['tag']] for e in events)),
            'gc_interval_count': len(intervals), 'gc_elapsed_overlay_ns': total,
            'max_gc_interval_ns': max(i['wall_ns'] for i in intervals),
            'gc_interval_first_ns': intervals[0]['start_ns'], 'gc_interval_last_ns': intervals[-1]['end_ns'],
            'gc_stats_counts_by_generation': dict(sorted(generations.items())),
            'heap_observations': heap_summary,
            'limitations': [
                'GC elapsed is an orthogonal overlay already inside phase/process wall, never an additional stage to add.',
                'These are compiler-process RTS events, not assembler/subprocess GC or memory measurements.',
                'HEAP_ALLOCATED is per-capability cumulative allocation; observations are not summed across successive samples.',
                'Last reported cumulative allocation is the observed counter, not an asserted exact process-exit allocation total.',
                'HEAP_LIVE is reported after major GC; last/max reported live bytes are not continuous peak live memory, final retained heap or RSS.',
                'No GC CPU time, exact mutator time, or per-phase allocation is inferred from these event timestamps.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('eventlog', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = args.eventlog.read_bytes()
        parsed, events = extract(data)
        receipt = json.loads(args.receipt.read_text())
        E.require(receipt.get('complete') is True and receipt.get('exit_code') == 0, 'Incomplete benchmark receipt')
        wall_ns = int(Decimal(str(receipt['wall_seconds'])) * 1_000_000_000)
        result = summarize(events, wall_ns)
        result.update(source_eventlog=str(args.eventlog), eventlog_sha256=hashlib.sha256(data).hexdigest(),
                      process_wall_ns=wall_ns, process_receipt=str(args.receipt), process_receipt_sha256=E.sha(args.receipt),
                      recipe_sha256=E.sha(__file__), validating_parser_sha256=E.sha(E.__file__),
                      event_count=parsed['event_count'],
                      format_sources=[{'path': str(p), 'sha256': E.sha(p)}
                                      for p in E.DOCS[:3] + [E.INCLUDE / 'EventTypes.h']],
                      implementation_sources=[
                          {'url': 'https://github.com/ghc/ghc/blob/ghc-9.14.1-release/rts/sm/Storage.c',
                           'git_blob_sha': 'b4fb7a4fa50adebd74ac0add53364e92eb105c5a',
                           'function': 'calcTotalAllocated', 'lines': '1577-1594',
                           'meaning': 'Emits each capability total_allocated times sizeof(W_), cumulative since start.'},
                          {'url': 'https://github.com/ghc/ghc/blob/ghc-9.14.1-release/rts/Stats.c',
                           'git_blob_sha': 'e60c0f2ac38e4eb7e7f82da700cc88e47a0b5a61',
                           'function': 'stat_endGC', 'lines': '580-607',
                           'meaning': 'GC_END uses stats elapsed timestamp; HEAP_LIVE emitted for major GC only.'}])
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: result[k] for k in ['complete', 'gc_interval_count', 'gc_elapsed_overlay_ns',
                          'gc_stats_counts_by_generation', 'heap_observations']}, indent=2))
        return 0
    except (E.InvalidEventlog, OSError, ValueError, KeyError, struct.error) as error:
        print('RTS eventlog rejected: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
