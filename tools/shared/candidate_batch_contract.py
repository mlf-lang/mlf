"""Authenticated candidate-selection batch projections, not fresh-process equivalence."""
import ast
import hashlib

SCRIPT_BLOB = 'c2a16944fe4e19c1f8de0ac24ff06d95d94c031c'
CLASSES_BLOBS = (
    'bbcc794dc1ce447ccfc1450378e951df1b427819',
    'b4a2ce4772e168f2013a77d0113298103557d955',
    '9f3597afc8b5415339f05291b4ce6342ea057d21',
    '54dd1eedb8736aa9cea55d40c4de979e08e2df17',
    '3ff1b6a5668928661b112f6ab4225880f3408a1a',
    '6f1bc8e923c6333d20f38b421ae43672fa0721c3',
    'b7caa275f2b1b90718e5da59152c8ccf9b96d538',
    '629f0c52164ab2211c638e9499caf6ab7b30121e',
    '1eaafe6174076500ac97aa1d6b3dbf9ea68959ee',
    'bdbc1000fce1a8b1b388f953adc13d7c7d862655',
    'fa396c405908b897db00decda395c1d1fa660420',
    'f22cec64548c408602c85c8c81732fb57694927e',
    # Defining-module dictionary resolution (814571b2) kept the selector body byte-identical.
    '5f813fb61a3982644a528e7fb481210e6da56b95',
    # Cold frontend work keeps the authenticated selector fixture byte-identical.
    '7f3649c519a3426cb14c035921175f510bc749ca',
)
ORIGINAL_FIXTURE_SHA256 = '0d61d38552efcbfca9c8709257454233c3699775a106e368900da7dbe3f3fc66'
SOURCE_BASIS = '8d80e0fb1dbf4e6d40c53de35b727674b5c74817'
BEGIN, END = 812350001, 812350002
FORWARD = tuple(range(24))
REVERSE = tuple(reversed(FORWARD))
SCOPE = '24 logical projections; not 24 fresh interpreter processes or general state/GC equivalence'
ADAPTATIONS = (
 (b'  readIndices position count = if count == 0 then ioReturn [] else do {\n',
  b'  readIndices :: (Int -> IO String) -> Int -> Int -> IO ([] Int);\n  readIndices getArg position count = if count == 0 then ioReturn [] else do {\n'),
 (b'rest <- readIndices (position + 1) (count - 1);',
  b'rest <- readIndices getArg (position + 1) (count - 1);'),
 (b'    indices <- readIndices 4 (readInt count);',
  b'    indices <- readIndices getArg 4 (readInt count);'),
 (b'  main = do {\n',
  b'  runCase :: (Int -> IO String) -> IO ();\n  runCase getArg = do {\n'),
)

def require(ok, message):
    if not ok: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def blob(raw): return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def original_fixture(script, classes):
    """Parse literal syntax only; never execute an unauthenticated generator."""
    require(type(script)is bytes and blob(script)==SCRIPT_BLOB, 'frozen candidate script')
    require(type(classes)is bytes and blob(classes) in CLASSES_BLOBS, 'fixed Classes source')
    tree=ast.parse(script)
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and
           isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and
           n.func.value.id=='fixture' and n.func.attr=='write_text']
    require(len(calls)==1 and len(calls[0].args)==1 and not calls[0].keywords,'unique fixture writer')
    node=calls[0].args[0]
    require(isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add) and
            isinstance(node.left,ast.BinOp) and isinstance(node.left.op,ast.Add) and
            isinstance(node.left.right,ast.Name) and node.left.right.id=='body' and
            isinstance(node.left.left,ast.Constant) and type(node.left.left.value)is str and
            isinstance(node.right,ast.Constant) and type(node.right.value)is str,
            'literal prefix/body/suffix contract')
    text=classes.decode('utf-8')
    first,last='  selectCandidates ::','  methodBindings ::'
    require(text.count(first)==1 and text.count(last)==1,'unique selector body boundaries')
    begin,end=text.index(first),text.index(last)
    require(begin<end,'ordered selector body')
    body=text[begin:end]
    require(body.count('  selectCandidateOrdinals ordinal names indices supers =')==1,'selector body contract')
    fixture = (node.left.left.value+body+node.right.value).encode('utf-8')
    require(digest(fixture) == ORIGINAL_FIXTURE_SHA256, 'historical candidate fixture changed')
    return fixture

def cases():
    # Independent literal-sized inventory of the original first twelve vectors.
    vectors=[(n,0,ids) for n in (0,1,2,7)
             for ids in ([],[-1,n],[0,0,1,n-1])]
    result={}
    for selector in ('named','ids'):
        for index,(n,period,ids) in enumerate(vectors):
            key=len(result)
            expected=(''.join('i:n%d;'%i for i in range(n) if i in set(ids))+
                      's:super;g:given;i:n0;i:n0;\n').encode('ascii')
            result[key]=dict(selector=selector,index=index,
                arguments=[selector,*map(str,[n,period,len(ids),*ids])],expected=expected)
    require(len(result)==24,'24 interpreter observations')
    return result

def order_for(direction):
    require(direction in ('forward','reverse'),'direction')
    return FORWARD if direction=='forward' else REVERSE

def addition(direction):
    entries=['(,) %d [%s]'%(i,', '.join('"%s"'%a for a in cases()[i]['arguments']))
             for i in order_for(direction)]
    return (''';
  batchArgument :: [] String -> Int -> IO String;
  batchArgument args index =
    if ltInt index 0 then panic "candidate batch getArg out of range"
    else case args of {
      [] -> panic "candidate batch getArg out of range";
      (:) value rest ->
        if eqInt index 0 then ioReturn value
        else batchArgument rest (subInt index 1)
    };
  batchLoop :: [] ((,) Int ([] String)) -> IO ();
  batchLoop entries = case entries of {
    [] -> ioReturn ();
    (:) ((,) index args) rest -> do {
      printInt %d; printInt index;
      runCase (batchArgument args);
      printInt %d;
      batchLoop rest
    }
  };
  batchCases :: [] ((,) Int ([] String));
  batchCases = [%s];
  main :: IO ();
  main = batchLoop batchCases
'''%(BEGIN,END,', '.join(entries))).encode('ascii')

def generate(original, direction, script, classes):
    require(original==original_fixture(script,classes),'full original generated fixture')
    require(original.endswith(b'  }\n}\n'),'exact fixture tail')
    base=original
    for old,new in ADAPTATIONS:
        require(base.count(old)==1 and new not in base,'unique reversible adaptation')
        base=base.replace(old,new,1)
    result=base[:-2]+addition(direction)+b'}\n'
    require(restore(result,direction,script,classes)==original,'full inverse')
    return result

def restore(generated, direction, script, classes):
    require(type(generated)is bytes,'generated bytes')
    tail=addition(direction)+b'}\n'
    require(generated.endswith(tail),'exact generated tail')
    result=generated[:-len(tail)]+b'}\n'
    for old,new in reversed(ADAPTATIONS):
        require(result.count(new)==1 and old not in result,'unique inverse adaptation')
        result=result.replace(new,old,1)
    require(result==original_fixture(script,classes),'complete original bytes restored')
    return result

def parse(raw,direction):
    require(type(raw)is bytes and len(raw)<=32768,'bounded actual bytes')
    lines=raw.splitlines(keepends=True)
    require(len(lines)==96,'24 complete framed observations')
    rows=[]; offset=0
    for position,index in enumerate(order_for(direction)):
        chunk=lines[position*4:position*4+4]
        expected=cases()[index]['expected']
        require(chunk==[('%d\n'%BEGIN).encode(),('%d\n'%index).encode(),
                        expected,('%d\n'%END).encode()],'exact marker/order/result bytes')
        start=offset+len(chunk[0])+len(chunk[1]);end=start+len(chunk[2])
        rows.append(dict(index=index,arguments=cases()[index]['arguments'],
            start=start,end=end,actual_ascii=raw[start:end].decode('ascii'),
            actual_sha256=digest(raw[start:end])))
        offset+=sum(map(len,chunk))
    require(offset==len(raw),'unconsumed bytes')
    return rows

def physical_record(command_id,lane,direction,argv,stdout,stderr,exit_code):
    require(type(command_id)is str and bool(command_id),'physical identity')
    require(lane in ('host','interpreter'),'physical lane')
    require(type(argv)is list and bool(argv) and all(type(a)is str for a in argv),'physical argv')
    require(type(exit_code)is int and exit_code==0 and stderr==b'','physical success')
    return dict(id=command_id,lane=lane,direction=direction,argv=argv,
        exit_code=exit_code,stdout_sha256=digest(stdout),stdout_bytes=len(stdout),
        stderr_sha256=digest(stderr),vectors=parse(stdout,direction),scope=SCOPE)

def project(record,stdout,index,original_argv,original_expected):
    require(record['stdout_sha256']==digest(stdout),'capture identity')
    require(parse(stdout,record['direction'])==record['vectors'],'physical vectors changed')
    require(type(index)is int and index in FORWARD,'logical index')
    row=next(r for r in record['vectors'] if r['index']==index)
    args=cases()[index]['arguments']
    require(type(original_argv)is list and original_argv[-len(args):]==args,'exact logical arguments')
    actual=stdout[row['start']:row['end']]
    require(type(original_expected)is bytes and actual==original_expected,'frozen original expectation')
    return dict(physical_command_id=record['id'],index=index,original_argv=original_argv,
        start=row['start'],end=row['end'],actual_ascii=actual.decode('ascii'),
        actual_sha256=digest(actual),physical_stdout_sha256=digest(stdout),
        fresh_process=False,kind='verified-batch-projection')

def aggregate(physical,projections):
    require(len(physical)==4 and len({p['id'] for p in physical})==4,'four distinct physical batches')
    require({(p['lane'],p['direction']) for p in physical}==
        {(lane,d) for lane in ('host','interpreter') for d in ('forward','reverse')},'four lane/directions')
    require(len(projections)==96,'96 actual projections')
    by_id={p['id']:p for p in physical};seen=set()
    for p in physical:
        # Regenerate expected framing, never a physical execution record.
        expected=b''.join(('%d\n%d\n'%(BEGIN,i)).encode()+cases()[i]['expected']+
            ('%d\n'%END).encode() for i in order_for(p['direction']))
        require(type(p['exit_code'])is int and p['exit_code']==0 and
            p['stderr_sha256']==digest(b'') and p['stdout_sha256']==digest(expected) and
            type(p['stdout_bytes'])is int and p['stdout_bytes']==len(expected) and
            p['vectors']==parse(expected,p['direction']),'physical capture ledger')
    for row in projections:
        require(type(row['index'])is int and row['index'] in FORWARD,'projection index')
        key=(row['physical_command_id'],row['index'])
        require(key not in seen and key[0] in by_id,'duplicate/unknown projection')
        seen.add(key);p=by_id[key[0]];source=next(x for x in p['vectors'] if x['index']==key[1])
        require(type(row['start'])is int and type(row['end'])is int and
            row['kind']=='verified-batch-projection' and row['fresh_process'] is False and
            row['physical_stdout_sha256']==p['stdout_sha256'] and
            all(row[k]==source[k] for k in ('start','end','actual_ascii','actual_sha256')) and
            row['original_argv'][-len(source['arguments']):]==source['arguments'],
            'projection binding/offset/result')
    require(seen=={(p,i) for p in by_id for i in FORWARD},'exact projection coverage')
    return dict(batch_complete=True,physical_batch_count=4,logical_projection_count=96,
        original_interpreter_vectors=24,whole_candidate_complete=False,scope=SCOPE)
