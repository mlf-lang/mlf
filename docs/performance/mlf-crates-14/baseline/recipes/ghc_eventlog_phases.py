#!/usr/bin/env python3
"""Parse GHC's own eventlog records and timed-phase markers (no attachment).

Encoding source: bundled GHC 9.14.1 EventLogFormat.h, EventLogConstants.h,
and User's Guide eventlog-formats.rst.txt. Header sizes describe payloads,
integers are big endian, and event timestamps are nanoseconds.
Only the serial, properly nested USER_MSG (19) GHC:started:/GHC:finished:
stream is timed. USER_MARKER (58) duplicates are retained diagnostically only.
Textual -ddump-timings CPU measurements are not consumed or treated as wall.
"""
import argparse
import collections
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import io
import json
from pathlib import Path
import struct
import sys

W = Path(__file__).resolve().parents[1]
GHC = W.parent / 'pr25-latest-benchmark-work-20261026/toolchain/ghc-install'
INCLUDE = GHC / 'lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/rts-1.0.3/include/rts'
GUIDE = GHC / 'share/doc/ghc-9.14.1/html/users_guide/_sources/eventlog-formats.rst.txt'
TIMING_SOURCE = GHC / 'share/doc/ghc-9.14.1/html/libraries/ghc-9.14.1-da80/src/GHC.Utils.Error.html'
DOCS = [INCLUDE / 'EventLogFormat.h', INCLUDE / 'EventLogConstants.h', GUIDE, TIMING_SOURCE]
RTS_ENCODING_SOURCE = 'https://raw.githubusercontent.com/ghc/ghc/ghc-9.14.1-release/rts/eventlog/EventLog.c'
HEADER_BEGIN, HEADER_END = 0x68647262, 0x68647265
HET_BEGIN, HET_END = 0x68657462, 0x68657465
ET_BEGIN, ET_END = 0x65746200, 0x65746500
DATA_BEGIN, DATA_END = 0x64617462, 0xffff
BLOCK_MARKER, USER_MSG, USER_MARKER = 18, 19, 58


class InvalidEventlog(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidEventlog(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Reader:
    def __init__(self, stream):
        self.stream = stream

    def tell(self):
        return self.stream.tell()

    def take(self, n):
        require(0 <= n <= 16 * 1024 * 1024, 'Unreasonable record/header length')
        offset = self.tell()
        value = self.stream.read(n)
        require(len(value) == n, 'Truncated record at byte ' + str(offset))
        return value

    def number(self, code):
        return struct.unpack('>' + code, self.take(struct.calcsize('>' + code)))[0]

    def expect(self, value):
        offset = self.tell()
        require(self.number('I') == value, 'Incorrect format marker at byte ' + str(offset))


def parse_stream(stream):
    reader = Reader(stream)
    reader.expect(HEADER_BEGIN)
    reader.expect(HET_BEGIN)
    types = {}
    while True:
        marker = reader.number('I')
        if marker == HET_END:
            break
        require(marker == ET_BEGIN, 'Invalid event-type header marker')
        tag, size = reader.number('H'), reader.number('h')
        require(tag != DATA_END and tag not in types, 'Reserved/duplicate event type')
        require(size >= -1, 'Invalid negative fixed payload size')
        description = reader.take(reader.number('I')).decode('utf-8', errors='strict')
        reader.take(reader.number('I'))  # Future header extensions are explicitly skippable.
        reader.expect(ET_END)
        types[tag] = {'size': size, 'description': description}
    reader.expect(HEADER_END)
    reader.expect(DATA_BEGIN)
    data_start = reader.tell()
    require(USER_MSG in types and types[USER_MSG]['size'] == -1,
            'Missing or incompatible USER_MSG header')
    if BLOCK_MARKER in types:
        require(types[BLOCK_MARKER]['size'] >= 14, 'Invalid BLOCK_MARKER payload size')
    messages = []
    blocks = []
    current = None
    counts = collections.Counter()
    minimum, maximum = None, None
    records = 0

    def close_block(end_offset):
        if current is None:
            return
        span = end_offset - current['offset']
        # GHC 9.14.1 closeBlockMarker records the distance from marker start
        # through the buffer's current position, including the marker itself.
        require(span == current['declared_bytes'] and span >= current['marker_bytes'],
                'Invalid block length at byte ' + str(current['offset']))
        current['size_convention'] = 'includes-marker'
        current['physical_bytes'] = span
        blocks.append(current)

    while True:
        offset = reader.tell()
        tag = reader.number('H')
        if tag == DATA_END:
            # endEventLogging appends this two-byte tag to the global buffer
            # BEFORE printAndClearEventBuf closes the block. Thus the final
            # declared block size includes exactly these two sentinel bytes.
            require(current is not None and current['capability'] is None,
                    'GHC 9.14.1 end sentinel is not in the final global block')
            close_block(reader.tell())
            require(stream.read(1) == b'', 'Trailing bytes after EVENT_DATA_END')
            break
        require(tag in types, 'Event type absent from header at byte ' + str(offset))
        timestamp = reader.number('Q')
        size = types[tag]['size']
        payload = reader.take(reader.number('H') if size == -1 else size)
        records += 1
        counts[str(tag)] += 1
        minimum = timestamp if minimum is None else min(minimum, timestamp)
        maximum = timestamp if maximum is None else max(maximum, timestamp)
        if tag == BLOCK_MARKER:
            close_block(offset)
            block_size, end_time, capability = struct.unpack('>IQH', payload[:14])
            require(end_time >= timestamp, 'Block end precedes block start')
            current = {'offset': offset, 'marker_bytes': reader.tell() - offset,
                       'declared_bytes': block_size, 'start_ns': timestamp,
                       'end_ns': end_time, 'capability': None if capability == 0xffff else capability}
        else:
            if current is not None:
                require(current['start_ns'] <= timestamp <= current['end_ns'],
                        'Event timestamp outside its block at byte ' + str(offset))
            if tag in (USER_MSG, USER_MARKER):
                message = payload.decode('utf-8', errors='strict')
                if message.startswith(('GHC:started:', 'GHC:finished:')):
                    messages.append({'timestamp_ns': timestamp, 'offset': offset,
                                     'tag': tag, 'message': message,
                                     'capability': current['capability'] if current else None})
    require(records > 0, 'Empty event data')
    conventions = {block['size_convention'] for block in blocks}
    require(len(conventions) <= 1, 'Inconsistent block-size convention')
    return {'event_types': types, 'event_count': records, 'event_counts_by_tag': dict(counts),
            'event_timestamp_min_ns': minimum, 'event_timestamp_max_ns': maximum,
            'data_start_offset': data_start, 'block_count': len(blocks),
            'block_size_convention': next(iter(conventions)) if conventions else None,
            'messages': sorted(messages, key=lambda message: (message['timestamp_ns'], message['offset']))}


def reconstruct(parsed, process_wall_ns=None):
    # withTiming emits traceMarkerIO conditionally, then traceEventIO always.
    # Under -ddump-timings both channels contain the same phase labels; merging
    # them would cross-pair their identical labels and double the phase count.
    messages = [message for message in parsed['messages'] if message['tag'] == USER_MSG]
    diagnostics = [message for message in parsed['messages'] if message['tag'] == USER_MARKER]
    require(messages, 'No USER_MSG GHC timed-phase markers; eventlog does not establish phase wall')
    frames, intervals = [], []
    roots = []
    for index, message in enumerate(messages):
        if index:
            previous = messages[index - 1]
            require(not (message['timestamp_ns'] == previous['timestamp_ns'] and
                         message['capability'] != previous['capability']),
                    'Ambiguous simultaneous cross-capability phase-marker order')
        text = message['message']
        started = text.startswith('GHC:started:')
        prefix = 'GHC:started:' if started else 'GHC:finished:'
        label = text[len(prefix):].strip()
        require(bool(label), 'Empty timed-phase label')
        if started:
            phase = {'id': len(intervals), 'parent': frames[-1]['id'] if frames else None,
                     'label': label, 'start_ns': message['timestamp_ns'],
                     'start_offset': message['offset'], 'children': [],
                     'start_capability': message['capability']}
            if frames:
                frames[-1]['children'].append(phase['id'])
            else:
                roots.append(phase['id'])
            intervals.append(phase)
            frames.append(phase)
        else:
            require(bool(frames), 'Unmatched finish: ' + label)
            phase = frames.pop()
            require(phase['label'] == label, 'Non-nested/mismatched finish: ' + label +
                    '; expected ' + phase['label'])
            phase.update(end_ns=message['timestamp_ns'], end_offset=message['offset'],
                         end_capability=message['capability'])
            duration = phase['end_ns'] - phase['start_ns']
            children_wall = sum(intervals[child]['wall_ns'] for child in phase['children'])
            require(duration >= children_wall >= 0, 'Negative/overlapping child interval')
            phase.update(wall_ns=duration, exclusive_wall_ns=duration - children_wall)
    require(not frames, 'Unclosed timed phases: ' + ', '.join(phase['label'] for phase in frames))
    for a, b in zip(roots, roots[1:]):
        require(intervals[a]['end_ns'] <= intervals[b]['start_ns'], 'Overlapping top-level phases')
    coverage = sum(intervals[root]['wall_ns'] for root in roots)
    exclusive = sum(phase['exclusive_wall_ns'] for phase in intervals)
    require(coverage == exclusive, 'Exclusive phase reconciliation failure')
    first, last = intervals[roots[0]]['start_ns'], intervals[roots[-1]]['end_ns']
    by_label = collections.defaultdict(lambda: {'count': 0, 'exclusive_wall_ns': 0, 'inclusive_wall_ns': 0})
    for phase in intervals:
        entry = by_label[phase['label']]
        entry['count'] += 1
        entry['exclusive_wall_ns'] += phase['exclusive_wall_ns']
        entry['inclusive_wall_ns'] += phase['wall_ns']
    result = {key: value for key, value in parsed.items() if key not in ['messages', 'event_types']}
    result.update(format='ghc-eventlog-phase-wall-v2', complete=True,
                  selected_marker_tag=USER_MSG, selected_marker_channel='USER_MSG / traceEventIO',
                  diagnostic_marker_tag=USER_MARKER, diagnostic_marker_count=len(diagnostics),
                  all_channel_marker_count=len(parsed['messages']),
                  marker_count=len(messages), phase_count=len(intervals),
                  top_level_phase_count=len(roots), phase_timestamp_span_ns=last - first,
                  phase_wall_coverage_ns=coverage, exact_exclusive_sum_ns=exclusive,
                  unmarked_gaps_inside_phase_span_ns=last - first - coverage,
                  phase_capabilities=sorted({m['capability'] for m in messages if m['capability'] is not None}),
                  by_label=dict(sorted(by_label.items(), key=lambda pair: -pair[1]['exclusive_wall_ns'])),
                  intervals=intervals,
                  limitations=[
                      'Compiler-emitted marker elapsed intervals; textual GHC timings are CPU time and are not used.',
                      'Only USER_MSG (19) traceEventIO markers are paired; conditional duplicate USER_MARKER (58) records are diagnostic only.',
                      'Requires serial GHC timed phases; overlapping/non-nested markers are rejected, not assigned fake exclusive wall.',
                      'Exclusive values subtract direct child marker intervals; boundary/instrumentation work may remain in parents or residual.',
                      'Whole-process residual combines unmarked driver work, startup/shutdown and eventlog overhead; it is not an identified stage.',
                      'No GC/allocation attribution or ordinary-build overhead correction is inferred from these timestamps.'])
    if process_wall_ns is not None:
        require(process_wall_ns >= coverage, 'Marked phase coverage exceeds supplied process wall')
        require(process_wall_ns >= last - first, 'Phase timestamp span exceeds supplied process wall')
        result.update(process_wall_ns=process_wall_ns,
                      process_residual_wall_ns=process_wall_ns - coverage)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('eventlog', type=Path)
    parser.add_argument('--receipt', type=Path, help='Same-run benchmark receipt with wall_seconds')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--messages-output', type=Path, help='Only GHC phase messages, not environment/args')
    args = parser.parse_args()
    try:
        with args.eventlog.open('rb') as stream:
            parsed = parse_stream(stream)
        wall = None
        if args.receipt:
            receipt = json.loads(args.receipt.read_text())
            require(receipt.get('exit_code') == 0 and receipt.get('complete') is True,
                    'Supplied benchmark receipt is not a successful completed run')
            seconds = Decimal(str(receipt['wall_seconds']))
            require(seconds.is_finite() and seconds >= 0, 'Invalid process wall duration')
            wall = int((seconds * 1_000_000_000).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        result = reconstruct(parsed, wall)
        result.update(source_eventlog=str(args.eventlog), eventlog_sha256=sha(args.eventlog),
                      recipe_sha256=sha(__file__),
                      block_size_source={'url': RTS_ENCODING_SOURCE,
                          'functions': ['closeBlockMarker', 'endEventLogging', 'printAndClearEventBuf'],
                          'rule': 'Every block includes its marker; final global block also includes the two-byte EVENT_DATA_END.'},
                      marker_channel_source={'path': str(TIMING_SOURCE), 'sha256': sha(TIMING_SOURCE),
                          'function': 'withTiming / eventBegins / eventEnds',
                          'rule': 'Conditional traceMarkerIO precedes unconditional traceEventIO; select USER_MSG only, never merge channels.'},
                      format_sources=[{'path': str(path), 'sha256': sha(path)} for path in DOCS])
        if args.receipt:
            result.update(process_receipt=str(args.receipt), process_receipt_sha256=sha(args.receipt))
        if args.messages_output:
            args.messages_output.write_text(json.dumps(parsed['messages'], indent=2) + '\n')
        text = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.write_text(text)
        else:
            print(text, end='')
        return 0
    except (InvalidEventlog, UnicodeError, OSError, KeyError, ValueError, struct.error) as error:
        print('Eventlog rejected: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
