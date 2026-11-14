"""Small pure DATA MODEL, NOT a binary decoder, execution adapter or admission gate.
Synthetic tests demonstrate complete field comparisons and ordered-read behavior.
Actual MLFBIN decoding/provenance/ownership/runtime admission remains future work.
No filesystem, process, loader, compiler, guard, lock or repository-helper access.
"""
import hashlib

class ContractError(ValueError):pass

def need(ok,message):
 if not ok:raise ContractError(message)
def digest(raw):
 need(type(raw) is bytes,'raw bytes required');return hashlib.sha256(raw).hexdigest()
def exact_keys(v,keys):need(type(v) is dict and set(v)==set(keys),'exact object schema')
def hexadecimal(v):return type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v)

def freshness_model(query,crate):
 exact_keys(query,['format','crate','semantic_fingerprint','inferred_groups','reused_groups','groups'])
 need(type(query['format']) is int and query['format']==1 and query['crate']==crate,'format/crate')
 groups=query['groups'];need(type(groups) is list and groups,'nonempty actual groups')
 need(type(query['inferred_groups']) is int and query['inferred_groups']==len(groups),'fresh count equals full group list')
 need(type(query['reused_groups']) is int and query['reused_groups']==0,'integer zero reuse')
 need(type(query['semantic_fingerprint']) is str and query['semantic_fingerprint'],'crate fingerprint')
 ids=[]
 for g in groups:
  exact_keys(g,['id','members','cached','semantic_fingerprint','query_key'])
  need(type(g['id']) is str and g['id'],'group id');ids.append(g['id'])
  need(type(g['members']) is list and g['members'] and all(type(m) is str and m for m in g['members']),'ordered members')
  need(g['cached'] is False,'cached must be false')
  need(type(g['semantic_fingerprint']) is str and g['semantic_fingerprint'],'group fingerprint')
  need(hexadecimal(g['query_key']),'query key')
 need(len(ids)==len(set(ids)),'unique groups')


def validate_decoded_model(snapshot,actual_binary_bytes,expected_crate,expected_flavor):
 """An already decoded synthetic snapshot. Does NOT authenticate real wire bytes."""
 exact_keys(snapshot,['format','configuration','declarations','groups','evidence','types','rows','results','query','semantic_files'])
 need(snapshot['format']=='MLF-CRATE-QUERY-GRAPH-2','format')
 conf=snapshot['configuration'];need(type(conf) is list and len(conf)==5,'five config fields')
 need(conf==[expected_crate,digest(actual_binary_bytes),'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1',expected_flavor],'producer-specific full config')
 for name in ['declarations','groups','evidence','types']:need(type(snapshot[name]) is list,'complete table')
 rows=snapshot['rows'];need(type(rows) is list and rows,'complete rows')
 bykey={};locations=set()
 for row in rows:
  exact_keys(row,['key','digest','reads','payload'])
  key=row['key'];need(type(key) is str and key and key not in bykey,'unique row identity')
  need(hexadecimal(row['digest']),'row digest')
  need(type(row['reads']) is list and all(type(x) is str and x for x in row['reads']),'ordered reads list')
  # Repeated read occurrences are legal. Never convert this list to a set.
  need(row['payload'] is None or row['payload']==row['digest'],'location matches row digest')
  if row['payload'] is not None:locations.add(row['payload'])
  bykey[key]=row
 done=set();visiting=set()
 def visit(key):
  need(key in bykey,'missing read target');need(key not in visiting,'cycle')
  if key in done:return
  visiting.add(key)
  for dependency in bykey[key]['reads']:visit(dependency)
  visiting.remove(key);done.add(key)
 for key in bykey:visit(key)
 results=snapshot['results'];need(type(results) is dict and set(results)==locations,'full unique result location closure')
 for name,raw in results.items():need(hexadecimal(name) and digest(raw)==name,'result content address')
 freshness_model(snapshot['query'],expected_crate)
 need(type(snapshot['semantic_files']) is dict and snapshot['semantic_files'],'full semantic file map')
 need(all(type(k) is str and k and type(v) is bytes for k,v in snapshot['semantic_files'].items()),'raw semantic bytes')
 return True

def cross_producer_model(a,b,binary_a,binary_b,crate,flavor):
 """Explicit second-config-field comparison. Never strips/rewrites any object."""
 validate_decoded_model(a,binary_a,crate,flavor);validate_decoded_model(b,binary_b,crate,flavor)
 # Each compiler SHA must match its own binary, even if the two happen to equal.
 # All four other configuration fields are independently bound above and exact.
 for i in [0,2,3,4]:need(a['configuration'][i]==b['configuration'][i],'non-producer config field differs')
 for name in ['format','declarations','groups','evidence','types','rows','results','query','semantic_files']:
  need(a[name]==b[name],'full field/raw difference: '+name)
 return True

def same_binary_raw_model(oracle_files,current_files,oracle_binary_sha,current_binary_bytes):
 """Exact whole inventory+bytes; NO config/CRC/CURRENT/path exceptions here."""
 need(hexadecimal(oracle_binary_sha) and digest(current_binary_bytes)==oracle_binary_sha,'same binary binding')
 need(type(oracle_files) is dict and oracle_files and type(current_files) is dict,'raw inventory map')
 need(set(oracle_files)==set(current_files),'same full relative inventory')
 for k in oracle_files:need(type(oracle_files[k]) is bytes and type(current_files[k]) is bytes and oracle_files[k]==current_files[k],'exact raw file bytes')
 return True
