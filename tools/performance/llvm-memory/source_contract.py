from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
MANIFEST_SHA='3139c588c098659f16b17e88d20f584af54810c26ecda63aad7c042592feec29'
OLD_SHA='2fb2b89dde8e727ca56086a6a85167dded4ae9b993bf2cac48a33233e6a58d92'
NEW_SHA='50780c7183d62aa7568c0a799fdf5829b6ea60cbbc67cca7fd1a3f08bc4ba9c5'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def manifest():
 raw=(HERE/'host-delta.json').read_bytes();require(sha(raw)==MANIFEST_SHA,'fixed UTF8 host delta');d=json.loads(raw)
 require(d['old']==OLD_SHA and d['new']==NEW_SHA and d['path']=='host/ghc/MLF/Host/Base.hs' and d['parent_ref']=='9dfcd6625775819568eaaa5065f8dd1431df52f8','exact host owner transition');return d
def restore_before(raw):
 d=manifest();require(sha(raw)==NEW_SHA,'complete UTF8 host owner');result=raw
 for e in reversed(d['edits']):
  before,after=e['old'].encode(),e['new'].encode();require(result.count(after)==1,'one inverse region');result=result.replace(after,before)
 require(sha(result)==OLD_SHA,'exact prior full host owner');return result
