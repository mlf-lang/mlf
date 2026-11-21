"""Pure authenticated UTF8 batching contract. Does not execute any workload.

Batch observations are NOT fresh-process equivalence. The integrator must run
forward and reverse interpreter batches, host batches, and the three ORIGINAL
fixture demand cases in separate fresh processes. Keep original native/host
controls unchanged. Physical execution receipts and logical projections differ.
"""
import hashlib
import re

FIXTURE_BLOB = 'dcef64296a26296b720d0ffa00016d808f7cee1e'
FIXTURE_PATH = 'tools/shared/fixtures/utf8-length/Length.hs'
BEGIN = 812340001
END = 812340002
LIMIT = (1 << 63) - 1
HEADER = b'  main = do {\n'
PARAMETERIZED = b'  runCase getArg = do {\n'
SUFFIX = b'  }\n}\n'
FORWARD = tuple(range(6)) + tuple(range(10, 29))
REVERSE = tuple(reversed(FORWARD))
SCOPE = ('Ordered batch observations, not original per-vector fresh-process '
         'isolation or a proof of cache/GC/state independence')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def authenticate(raw):
    require(type(raw) is bytes, 'fixture must be bytes')
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    require(actual == FIXTURE_BLOB, 'original fixture pin')
    require(raw.count(HEADER) == 1 and raw.endswith(SUFFIX), 'unique fixture boundary')
    return digest(raw)


def vectors():
    """Independent inventory, including original indices of skipped large counts."""
    unit = 'aα中😀\0'
    all_cases = [(('count', str(n)), unit*n) for n in (0,1,2,63,64,65,255,256,257,1024)]
    all_cases += [(('scalar', str(n)), chr(n)) for n in
                  (0,1,127,128,2047,2048,55295,57344,65535,65536,1114111)]
    all_cases += [(('slice','65',str(start),str(count)), (unit*65)[start:start+count])
                  for start,count in ((0,0),(0,5),(1,3),(3,7),(255,1),(256,3),(324,1),(325,0))]
    require(len(all_cases) == 29, 'original inventory')
    return {i: {'arguments': args, 'expected': (len(text.encode('utf-8')), len(text))}
            for i,(args,text) in enumerate(all_cases) if i in FORWARD}


def order_for(direction):
    require(direction in ('forward', 'reverse'), 'batch direction')
    return FORWARD if direction == 'forward' else REVERSE


def addition(direction):
    cases = vectors()
    lines = [';\n  main = do {\n']
    for position,index in enumerate(order_for(direction)):
        args = cases[index]['arguments']
        # All arguments are fixed ASCII words/decimal numbers, no escaping needed.
        for arg in args:
            require(re.fullmatch(r'[a-z]+|[0-9]+', arg) is not None, 'argument literal')
        getter = 'panic "UTF8 batch getArg out of range"'
        for n,arg in reversed(list(enumerate(args))):
            getter = 'if eqInt index %d then ioReturn "%s" else (%s)' % (n,arg,getter)
        lines += ['    printInt %d; printInt %d;\n' % (BEGIN,index),
                  '    runCase (\\index -> %s);\n' % getter,
                  '    printInt %d%s\n' % (END, ';' if position+1 < len(FORWARD) else '')]
    lines.append('  }\n')
    return ''.join(lines).encode('ascii')


def generate(original, direction):
    authenticate(original)
    # Retain the complete original body and emit; only parameterize one binder.
    base = original.replace(HEADER, PARAMETERIZED, 1)
    generated = base[:-2] + addition(direction) + b'}\n'
    require(restore(generated, direction) == original, 'inverse mismatch')
    return generated


def restore(generated, direction):
    require(type(generated) is bytes, 'generated fixture must be bytes')
    tail = addition(direction) + b'}\n'
    require(generated.endswith(tail) and generated.count(PARAMETERIZED) == 1,
            'unique generated boundary')
    base = generated[:-len(tail)] + b'}\n'
    original = base.replace(PARAMETERIZED, HEADER, 1)
    authenticate(original)
    return original


def canonical_number(raw):
    require(type(raw) is bytes and re.fullmatch(rb'0|[1-9][0-9]{0,18}', raw) is not None,
            'noncanonical numeric output')
    number = int(raw)
    require(number <= LIMIT, 'numeric overflow')
    return number


def parse(raw, direction):
    """Return verified real result byte ranges; never synthesize result output."""
    require(type(raw) is bytes and len(raw) <= 32768, 'bounded raw output')
    lines = raw.splitlines(keepends=True)
    require(len(lines) == 25*5 and all(line.endswith(b'\n') for line in lines),
            'truncated or extra batch output')
    cases = vectors()
    rows = []
    offset = 0
    for position,index in enumerate(order_for(direction)):
        chunk = lines[position*5:position*5+5]
        numbers = tuple(canonical_number(line[:-1]) for line in chunk)
        require(numbers[0] == BEGIN and numbers[4] == END, 'batch marker')
        require(numbers[1] == index, 'batch index/order/duplicate')
        require(numbers[2:4] == cases[index]['expected'], 'vector result differs')
        start = offset + len(chunk[0]) + len(chunk[1])
        end = start + len(chunk[2]) + len(chunk[3])
        result = raw[start:end]
        rows.append(dict(index=index, arguments=list(cases[index]['arguments']),
                         start=start, end=end, actual_ascii=result.decode('ascii'),
                         actual_sha256=digest(result)))
        offset += sum(map(len, chunk))
    require(offset == len(raw), 'unconsumed output')
    return rows


def physical_record(command_id, lane, direction, argv, stdout, stderr, exit_code):
    """Called ONLY after a real process exits; execution/cleanup proof is external."""
    require(type(command_id) is str and command_id, 'physical command id')
    require(lane in ('host', 'interpreter'), 'physical lane')
    require(type(argv) is list and argv and all(type(a) is str for a in argv), 'physical argv')
    require(type(exit_code) is int and exit_code == 0 and stderr == b'', 'batch execution failed')
    rows = parse(stdout, direction)
    return dict(id=command_id, lane=lane, direction=direction, argv=argv,
                exit_code=exit_code, stdout_sha256=digest(stdout), stdout_bytes=len(stdout),
                stderr_sha256=digest(stderr), vectors=rows, scope=SCOPE)


def project(record, stdout, index, original_argv, original_expected):
    """Projection of actual bytes, not a fake subprocess.CompletedProcess."""
    require(record['stdout_sha256'] == digest(stdout), 'physical capture changed')
    rows = parse(stdout, record['direction'])
    require(rows == record['vectors'], 'physical inventory changed')
    require(type(index) is int and index in FORWARD, 'logical index')
    require(type(original_argv) is list and len(original_argv) >= 2, 'original argv')
    row = next(row for row in rows if row['index'] == index)
    args = row['arguments']
    require(original_argv[-len(args):] == args, 'original vector arguments changed')
    actual = stdout[row['start']:row['end']]
    require(type(original_expected) is bytes and actual == original_expected,
            'original expected differs from actual projection')
    return dict(physical_command_id=record['id'], index=index, original_argv=original_argv,
                start=row['start'], end=row['end'], actual_ascii=actual.decode('ascii'),
                actual_sha256=digest(actual), physical_stdout_sha256=digest(stdout),
                fresh_process=False, kind='verified-batch-projection')


def aggregate(physical_commands, logical_vectors, original_host_outputs):
    """Require both directions/lanes and 100 projections, plus real host baseline.

    Original 3 fresh interpreter demands and full host/native/runtime inventories
    are separate mandatory integration gates, not proved by this pure function.
    """
    require(len(physical_commands) == 4, 'four real batch commands required')
    require({(p['lane'],p['direction']) for p in physical_commands} ==
            {(lane,d) for lane in ('host','interpreter') for d in ('forward','reverse')},
            'physical lane/direction inventory')
    by_id = {p['id']:p for p in physical_commands}
    require(len(by_id) == 4, 'duplicate physical id')
    for p in physical_commands:
        require(type(p['exit_code']) is int and p['exit_code'] == 0 and
                p['stderr_sha256'] == digest(b''), 'physical execution status changed')
        require(tuple(r['index'] for r in p['vectors']) == order_for(p['direction']),
                'physical vector inventory changed')
        require(type(p['stdout_bytes']) is int and 0 < p['stdout_bytes'] <= 32768,
                'physical capture size')
        offset = 0
        for row in p['vectors']:
            index = row['index']
            require(type(index) is int and index in FORWARD, 'physical index type')
            expected = ('%d\n%d\n' % vectors()[index]['expected']).encode('ascii')
            prefix = ('%d\n%d\n' % (BEGIN,index)).encode('ascii')
            start = offset + len(prefix)
            end = start + len(expected)
            require(type(row['start']) is int and type(row['end']) is int and
                    row['start'] == start and row['end'] == end and
                    0 <= start < end <= p['stdout_bytes'], 'physical offset/range')
            require(row['actual_ascii'] == expected.decode('ascii') and
                    row['actual_sha256'] == digest(expected), 'physical independent expected/hash')
            offset = end + len(('%d\n' % END).encode('ascii'))
        require(offset == p['stdout_bytes'], 'physical exact capture size')
    require(set(original_host_outputs) == set(FORWARD), 'original host inventory')
    require(len(logical_vectors) == 100, 'logical coverage count')
    seen = set()
    for row in logical_vectors:
        require(type(row['index']) is int and type(row['start']) is int and
                type(row['end']) is int, 'logical integer types')
        key = (row['physical_command_id'],row['index'])
        require(key not in seen and key[0] in by_id and key[1] in FORWARD, 'logical duplicate/unknown')
        seen.add(key)
        p = by_id[key[0]]
        source = next(x for x in p['vectors'] if x['index'] == key[1])
        require(row['kind'] == 'verified-batch-projection' and row['fresh_process'] is False,
                'logical projection mislabeled as execution')
        args = vectors()[key[1]]['arguments']
        require(row['original_argv'][-len(args):] == list(args), 'logical original arguments changed')
        require(row['physical_stdout_sha256'] == p['stdout_sha256'] and
                all(row[k] == source[k] for k in ('start','end','actual_ascii','actual_sha256')),
                'projection evidence changed')
        require(row['actual_ascii'].encode('ascii') == original_host_outputs[key[1]],
                'original host/batch result differs')
    require(seen == {(p,i) for p in by_id for i in FORWARD}, 'logical coverage missing')
    return dict(batch_complete=True, physical_command_count=4, logical_projection_count=100,
                original_interpreter_vectors=25, scope=SCOPE,
                original_fresh_demand_gate_complete=False, whole_utf8_complete=False)

# Explicit successor to the retained expanded v1 generator. The v1 generator
# and all of its historical shape tests remain available, not silently rewritten.
LOOP_PARAMETERIZED = (b'  runCase :: (Int -> IO String) -> IO ();\n'
                      b'  runCase getArg = do {\n')

def loop_addition(direction):
    cases = vectors()
    entries = []
    for index in order_for(direction):
        args = cases[index]['arguments']
        for arg in args:
            require(re.fullmatch(r'[a-z]+|[0-9]+', arg) is not None, 'argument literal')
        entries.append('(,) %d [%s]' % (index, ', '.join('"%s"' % arg for arg in args)))
    template = ''';\n  batchArgument :: [] String -> Int -> IO String;
  batchArgument args index =
    if ltInt index 0 then panic "UTF8 batch getArg out of range"
    else case args of {
      [] -> panic "UTF8 batch getArg out of range";
      (:) value rest ->
        if eqInt index 0 then ioReturn value
        else batchArgument rest (subInt index 1)
    };
  batchLoop :: [] ((,) Int ([] String)) -> IO ();
  batchLoop entries = case entries of {
    [] -> ioReturn ();
    (:) ((,) index args) rest -> do {
      printInt %d;
      printInt index;
      runCase (batchArgument args);
      printInt %d;
      batchLoop rest
    }
  };
  batchCases :: [] ((,) Int ([] String));
  batchCases = [%s];
  main :: IO ();
  main = batchLoop batchCases
'''
    return (template % (BEGIN, END, ', '.join(entries))).encode('ascii')

def generate_loop(original, direction):
    authenticate(original)
    base = original.replace(HEADER, LOOP_PARAMETERIZED, 1)
    generated = base[:-2] + loop_addition(direction) + b'}\n'
    require(restore_loop(generated, direction) == original, 'loop inverse mismatch')
    return generated

def restore_loop(generated, direction):
    require(type(generated) is bytes, 'generated loop fixture must be bytes')
    tail = loop_addition(direction) + b'}\n'
    require(generated.endswith(tail) and generated.count(LOOP_PARAMETERIZED) == 1,
            'unique loop generated boundary')
    base = generated[:-len(tail)] + b'}\n'
    original = base.replace(LOOP_PARAMETERIZED, HEADER, 1)
    authenticate(original)
    return original
