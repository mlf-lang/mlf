"""Boundary attribution only. GHC laziness may force fragment work inside record."""
import hashlib,difflib
PATCHES={
'Bootstrap.QueryGraph':[
('newIntArray 6 0','newIntArray 7 0'),
('mapM (readIntArray counters) [0,1,2,3,4,5]','mapM (readIntArray counters) [0,1,2,3,4,5,6]'),
('["graph_ms","load_ms","infer_ms","finish_ms","output_ms","publish_ms"]','["graph_ms","load_ms","infer_ms","finish_ms","output_ms","publish_ms","raw_record_ms"]')],
'Bootstrap.CrateGraph':[
('                          recorded <- if hit then case previous of {','                          recordStarted <- G.clock statistics;\n                          recorded <- if hit then case previous of {'),
('                          G.elapsed statistics 2 inferStarted;','                          G.elapsed statistics 6 recordStarted;\n                          G.elapsed statistics 2 inferStarted;')]}
def instrument(src):
 out={}
 for module,replacements in PATCHES.items():
  p=src/(module.replace('.','/')+'.hs');before=p.read_text();after=before
  for old,new in replacements:
   if after.count(old)!=1:raise ValueError('instrumentation anchor count: '+module)
   after=after.replace(old,new)
  p.write_text(after)
  out[module]={'before_sha256':hashlib.sha256(before.encode()).hexdigest(),'after_sha256':hashlib.sha256(after.encode()).hexdigest(),'patch':''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=module,tofile=module+' instrumented'))}
 return out
