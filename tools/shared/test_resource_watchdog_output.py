"""Deterministic pure filesystem controls for the exact watchdog function.
No subprocess, compiler, resource guard bypass, or workload execution.
"""
import ast,errno,os,pathlib,stat,tempfile,types
P=pathlib.Path
source=P(__file__).with_name('resource_watchdog.py')
tree=ast.parse(source.read_text())
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='output_bytes')
def get(walk=os.walk):
 env={'Path':P,'stat':stat,'errno':errno,'os':types.SimpleNamespace(path=os.path,walk=walk)}
 exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),env)
 return env['output_bytes']
def rejects(f,kind):
 try:f()
 except kind:return
 raise AssertionError('expected '+kind.__name__)
def injected(error,after=None,names=()):
 def walk(root,**kw):
  yield str(root),list(names),[]
  if after:after()
  kw['onerror'](error)
 return get(walk)
def main():
 with tempfile.TemporaryDirectory() as t:
  root=P(t)/'watched';root.mkdir();(root/'a').write_bytes(b'abc')
  assert get()(root)==3
  child=root/'child'
  assert injected(FileNotFoundError(errno.ENOENT,'gone',str(child)),names=['child'])(root)==0
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(child)))(root),FileNotFoundError)
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(child/'nested')),names=['child'])(root),FileNotFoundError)
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(root)))(root),FileNotFoundError)
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(P(t)/'outside')))(root),FileNotFoundError)
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(root/'..'/'outside')))(root),FileNotFoundError)
  rejects(lambda:injected(FileNotFoundError(errno.EACCES,'wrong errno',str(child)),names=['child'])(root),FileNotFoundError)
  rejects(lambda:injected(PermissionError(errno.EACCES,'denied',str(child)),names=['child'])(root),PermissionError)
  rejects(lambda:injected(NotADirectoryError(errno.ENOTDIR,'not directory',str(child)),names=['child'])(root),NotADirectoryError)
  rejects(lambda:injected(OSError(errno.EIO,'io',str(child)),names=['child'])(root),OSError)
  rejects(lambda:injected(FileNotFoundError('no filename'))(root),FileNotFoundError)
  absent=P(t)/'absent';rejects(lambda:get()(absent),FileNotFoundError)
  regular=P(t)/'file';regular.write_bytes(b'x');rejects(lambda:get()(regular),NotADirectoryError)
  # Root vanishes after the opening stat: descendant error alone cannot hide it.
  lost=P(t)/'lost';lost.mkdir()
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(lost/'child')),lost.rmdir,names=['child'])(lost),FileNotFoundError)
  # Root becomes a regular file during traversal.
  changed=P(t)/'changed';changed.mkdir()
  def replace():changed.rmdir();changed.write_bytes(b'x')
  rejects(lambda:injected(FileNotFoundError(errno.ENOENT,'gone',str(changed/'child')),replace,names=['child'])(changed),NotADirectoryError)
  # Real os.walk race: rename after it yielded the root and snapshotted names.
  race=P(t)/'race';race.mkdir();work=race/'work';work.mkdir();(work/'data').write_bytes(b'payload')
  def rename_walk(path,**kw):
   iterator=os.walk(path,**kw)
   first=next(iterator);yield first
   work.rename(race/'published')
   yield from iterator
  assert get(rename_walk)(race)==0
  assert get()(race)==7  # next ordinary sample observes the published artifact
  # A disappeared sampled file remains tolerated as before.
  vanished=P(t)/'vanished';vanished.mkdir();f=vanished/'gone';f.write_bytes(b'x')
  def file_walk(path,**kw):
   f.unlink();yield str(path),[],['gone']
  assert get(file_walk)(vanished)==0
  (root/'symlink').symlink_to(race,target_is_directory=True)
  assert get()(root)==3  # unchanged followlinks=False; no external tree counted
 print('PASS 20 deterministic output traversal controls; no compiler execution')
if __name__=='__main__':main()
