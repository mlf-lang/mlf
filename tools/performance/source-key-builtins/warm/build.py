#!/usr/bin/env python3
"""Build one executable with plain, coarse (original boundaries), and detailed v7 drivers."""
import argparse
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
cli=argparse.ArgumentParser(description=__doc__)
cli.add_argument('output',type=Path)
cli.add_argument('--focus',action='store_true',help='additional Prelude and symbol table probes')
args=cli.parse_args()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = json.loads((ROOT/'shared-sources.json').read_text())
PATHS = {row['module']: ROOT/row['path'] for row in MANIFEST['modules']}

def one(s, old, new):
    if s.count(old) != 1:
        raise ValueError(f'expected one site, found {s.count(old)}: {old!r}')
    return s.replace(old,new)

def wrap(s, expression, label, kind='demand'):
    return one(s,expression,f'(Clock.{kind} "{label}" ({expression}))')

def definitions(s, kind, labels):
    for name, label in labels.items():
        match = re.findall(r'^  '+name+r'(?= ).*? =(?=\s)',s,re.M)
        if len(match)!=1:
            raise ValueError(f'ambiguous definition: {name} {match}')
        s=one(s,match[0],match[0]+' Clock.'+kind+' "'+label+'" HP.$')
    return s

def region(s, start, end, replacements):
    i=s.index(start); j=s.index(end,i+len(start))
    part=s[i:j]
    for old,new in replacements:
        part=one(part,old,new)
    return s[:i]+part+s[j:]

def query(s):
    s=definitions(s,'io',{'loadBinarySourceContext':'context.load'})
    s=definitions(s,'demand',{'sourceCacheParts':'key.project','restoreSourceCacheKey':'key.restore',
        'binaryQuery':'typed.envelope','decodeBinarySourceRecord':'raw.record','validateCached':'raw.validate'})
    s=one(s, 'contracts, scopes]) context)', 'contracts, scopes]) (Clock.demand "key.projectedContext" context))')
    s=wrap(s,'Separate.pack\n          [format, crateId, compilerHash, members, bindings, context, prepared, contracts, scopes]',
             'key.restoredText')
    s=region(s,'  decodeBinarySourceRecord key','  data BinaryQuery',[
        ('eqString saved key','Clock.demand "key.equal" (eqString saved key)'),
        ('eqString (encodeSourceDatatypes datatypes) context','Clock.demand "key.datatypes" (eqString (encodeSourceDatatypes datatypes) context)'),
        ('Storage.admit [Storage.AdmitTerm body]', 'Clock.demand "syntax.body" (Storage.admit [Storage.AdmitTerm body])'),
        ('eqString (Separate.fingerprint (Pretty.prettyTerm body))\n      (Separate.unitObjectFingerprint header)',
         'Clock.demand "checksum.body" (eqString (Separate.fingerprint (Pretty.prettyTerm body)) (Separate.unitObjectFingerprint header))'),
        ('Separate.fingerprint (Pretty.prettyTerm term)', 'Clock.demand "checksum.newUnit" (Separate.fingerprint (Pretty.prettyTerm term))')])
    s=region(s,'  validateCached expectedName','  decodeCached ::',[
        ('D.validateDeclarations datatypes','Clock.demand "datatype.validate" (D.validateDeclarations datatypes)'),
        ('Separate.collectBindings ds (XEnv M.empty (M.fromList X.compareName parameters))\n          implementation',
         'Clock.demand "xmlf.bindings" (Separate.collectBindings ds (XEnv M.empty (M.fromList X.compareName parameters)) implementation)'),
        ('Separate.fingerprint (Pretty.prettyTerm payload)','Clock.demand "checksum.returnedUnit" (Separate.fingerprint (Pretty.prettyTerm payload))')])
    s=region(s,'  loadBinarySourceContext cacheDir','  decodeBinarySourceRecord ::',[
        ('fileExists path','Clock.io "file.stat" (fileExists path)'),
        ('byteArrayDigest bytes','Clock.io "context.sha" (byteArrayDigest bytes)'),
        ('eqString (encodeSourceDatatypes datatypes) expectedContext','Clock.demand "key.datatypes" (eqString (encodeSourceDatatypes datatypes) expectedContext)'),
        ('eqString encoded expectedContext','Clock.demand "key.carrier" (eqString encoded expectedContext)')])
    s=region(s,'  readBinarySourceGraph previous','  readSourceCacheFileWithWindow ::',[
        ('validSourceContextDigest digest','Clock.demand "key.ref-format" (validSourceContextDigest digest)'),
        ('fst selected','Clock.demand "key.window" (fst selected)')])
    return s

def storage(s):
    s=definitions(s,'io',{'readRaw':'file.read','decode':'wire.decode','encode':'wire.encode',
        'writeRaw':'file.write','writeAtomic':'file.encode-publish','writeRawAtomic':'file.publish-buffer'})
    s=definitions(s,'demand',{'checkUnit':'raw.checkUnit','validateUnitInterface':'interface.validate'})
    s=one(s,'readByteFileOrError path maxBytes','HostFile.measuredRead path maxBytes')
    s=one(s,'writeByteFileOrError path bytes','HostFile.measuredWrite path bytes')
    s=one(s,'  import MLF.Primitive;', '  import qualified WarmFile as HostFile;\n  import MLF.Primitive;')
    s=region(s,'  checkUnit object =','  -- V2-only',[
        ('admit [AdmitTerm term]', 'Clock.demand "syntax.unit" (admit [AdmitTerm term])'),
        ('eqString (Separate.fingerprint (Pretty.prettyTerm term))\n      (Separate.unitObjectFingerprint iface)',
         'Clock.demand "checksum.unit" (eqString (Separate.fingerprint (Pretty.prettyTerm term)) (Separate.unitObjectFingerprint iface))'),
        ('Checked.check term','Clock.demand "xmlf.term" (Checked.check term)')])
    s=region(s,'  validateUnitInterface iface =','  checkUnit ::',[
        ('D.validateDeclarations (Separate.unitData iface)','Clock.demand "datatype.validate" (D.validateDeclarations (Separate.unitData iface))')])
    return s

def bitstream(s):
    s=definitions(s,'io',{'decodeGraph':'wire.graph','checksum':'wire.crc'})
    for field,label in [('runSection bytes 80 symbolLength (getSymbols limits symbolCount)','wire.symbols'),
                        ('runSection bytes nodeOffset nodeLength (getNodes limits geometry symbols)','wire.nodes'),
                        ('runSection bytes rootOffset rootLength (getRoots limits nodes nodeWidth rootCount)','wire.roots')]:
        s=wrap(s,field,label,'io')
    return one(s,'                  canonicalGraph nodes nodeCount roots;',
               '                  Clock.demand "wire.canonical" (canonicalGraph nodes nodeCount roots);')

def source(s):
    s=definitions(s,'demand',{'finishGroup':'finish','validatePreparedRaw':'preparedRaw',
        'admitFinalSourceObject':'finish.admit','canonicalFinalSourceObject':'finish.canonical',
        'finishUnsignedRoot':'finish.unsigned','finalGroupObject':'final.objectWHNF','finalGroupContracts':'final.contractsWHNF'})
    s=region(s,'  admitFinalSourceObject object =','  -- Internal explicit source',[
        ('Wire.plan Wire.defaultLimits [Structure.toRawUnitObject object]','Clock.demand "finish.plan" (Wire.plan Wire.defaultLimits [Structure.toRawUnitObject object])'),
        ('Storage.admit [Storage.AdmitTerm term]','Clock.demand "syntax.unit" (Storage.admit [Storage.AdmitTerm term])'),
        ('eqString (Separate.fingerprint (Pretty.prettyTerm term))\n      (Separate.unitObjectFingerprint iface)',
         'Clock.demand "checksum.finish" (eqString (Separate.fingerprint (Pretty.prettyTerm term)) (Separate.unitObjectFingerprint iface))'),
        ('Wire.planGraph Wire.defaultLimits [Structure.toRawUnitObject admitted]','Clock.demand "finish.planGraph" (Wire.planGraph Wire.defaultLimits [Structure.toRawUnitObject admitted])'),
        ('finalSyntaxRun graph [FinalVisit termIdentity (FinalTerm term)] []\n      (FinalSyntaxState M.empty M.empty 0 0 0)',
         'Clock.demand "finish.normalize" (finalSyntaxRun graph [FinalVisit termIdentity (FinalTerm term)] [] (FinalSyntaxState M.empty M.empty 0 0 0))')])
    return s

def artifact(s):
    s=definitions(s,'io',{'writeObjectEither':'artifact.pair','writeObjectEitherV1':'artifact.v1',
        'envelopeEncode':'artifact.encode-envelope','readInterface':'input.interface','readObject':'input.object'})
    s=wrap(s,'envelopeAboveOldWork [Structure.toCrateObjectFields (binaryObjectFields object)]','artifact.choose-format')
    s=wrap(s,'Storage.writeAtomic 4 (prefix ++ ".mlfco")\n        [Structure.toCrateObjectFields (binaryObjectFields object)]', 'artifact.object-v1','io')
    s=wrap(s,'Storage.writeAtomic 3 (prefix ++ ".mlfci")\n          [Structure.toCrateInterfaceFields (binaryInterfaceFields (objectInterface object))]', 'artifact.interface','io')
    s=wrap(s,'Storage.writeAtomic 3 (prefix ++ ".mlfci")\n                [Structure.toCrateInterfaceFields (binaryInterfaceFields (objectInterface object))]', 'artifact.interface','io')
    s=wrap(s,'Storage.writeRawAtomic path bytes','artifact.object-v2-publish','io')
    return region(s,'  makeObjectWithPayload iface','  makeObject iface',[
        ('encodePooledPayload fragments','Clock.demand "assembly.pooledText" (encodePooledPayload fragments)'),
        ('Separate.fingerprint payload','Clock.demand "assembly.fingerprint" (Separate.fingerprint payload)')])

def session(s,coarse):
    if coarse:
        s=one(s,'  import MLF.Primitive;', '  import Probe;\n  import MLF.Primitive;')
    else:
        s=definitions(s,'io',{'compileParsedSourceGroups':'groups','compilePreparedWithEncoding':'prepared-crate'})
        s=wrap(s,'withPrelude spec sources interfaces','prelude','io')
        s=wrap(s,'loadSourcesInPackage (specIdentity spec) (specSources spec)','frontend.load','io')
        s=wrap(s,'prepareCrate updated loaded sources','frontend.prepare')
        s=wrap(s,'Source.prepareGroupOwned owned plan contracts names','group.prepare')
        s=wrap(s,'Artifact.writeObjectWithPayloadEither prefix object payload','final.write','io')
        s=wrap(s,'writeFile (prefix ++ ".queries")\n                        (Query.reportJSON (specIdentity spec)\n                           (Artifact.semanticFingerprint (Artifact.objectInterface object)) report)',
               'final.report','io')
        s=one(s,'Right ((,,) fragments report contracts) ->\n          ioReturn\n            (do {',
                'Right ((,,) fragments report contracts) ->\n          ioReturn\n            (Clock.demand "assembly" HP.$ do {')
        s=wrap(s,'fileDigest executable','compiler.sha','io')
        s=wrap(s,'fileExists destination','group.record-stat','io')
    s=one(s,'writeFile (cacheDir ++ "/query-key.new") key;', ('writeKey' if coarse else 'Clock.writeKey')+' (cacheDir ++ "/query-key.new") key;')
    s=one(s,'digest <- fileDigest (cacheDir ++ "/query-key.new");',
          'digest <- '+('hashKey (cacheDir ++ "/query-key.new")' if coarse else 'Clock.io "scratch.sha" (fileDigest (cacheDir ++ "/query-key.new"))')+';')
    s=one(s,'Query.readSourceCacheFileWithWindow readWindow cacheDir key name\n            bindings datatypes names destination',
          ('readRecord' if coarse else 'Clock.hit')+' (Query.readSourceCacheFileWithWindow readWindow cacheDir key name\n            bindings datatypes names destination)')
    if coarse:
        s=one(s,'ioReturn (case observed of','admit (ioReturn (case observed of')
        s=one(s,'})\n        } else ioReturn ((,) [] (Left "cache miss"));','}))\n        } else ioReturn ((,) [] (Left "cache miss"));')
    return s

def host_file():
    s=(ROOT/'host/ghc/MLF/Host/IO.hs').read_text()
    start=s.index('v_readByteFileOrError ::')
    end=s.index('foreign import ccall safe "mlf_ghc_byte_array_digest"',start)
    s=s[start:end].replace('v_readByteFileOrError','measuredRead').replace('v_writeByteFileOrError','measuredWrite')
    s=wrap(s,'c_readByteFile pathBytes (fromIntegral pathLength) bound out size','file.c-read','io')
    s=wrap(s,'c_writeByteFile pathBytes (fromIntegral pathLength) bytes (fromIntegral size)','file.c-write','io')
    (OUT/'WarmFile.hs').write_text('''module WarmFile (measuredRead, measuredWrite) where
import Prelude hiding (Int, String)
import qualified Prelude as P
import MLF.Host.Base
import MLF.Host.IO
import qualified Data.ByteString as B
import Control.Exception
import Foreign (alloca, free, nullPtr, peek)
import qualified WarmClock as Clock
''' +s)

changed={'Bitstream':bitstream,'ArtifactStorage':storage,'SourceInference':source,'CrateQuery':query,
    'CrateArtifact':artifact,'CrateSession':lambda s:session(s,False),
    'ArtifactStructure':lambda s:definitions(s,'demand',{'fromGraphDataContext':'typed.context',
              'fromGraphXTerm':'typed.body','fromGraphUnitInterface':'typed.header'}),
    'Crate':lambda s:definitions(s,'io',{'ensureBuiltin':'prelude.ensure'})}
if args.focus:
    import focus
    changed['CompilerCore']=lambda s:focus.compiler(s,wrap,definitions)
    changed['Bitstream']=lambda s:focus.symbol_reader(bitstream(s),one)
    changed['CrateArtifact']=lambda s:focus.artifact(artifact(s),one,region)
    changed['Crate']=lambda s:focus.crate(definitions(s,'io',{'ensureBuiltin':'prelude.ensure'}),wrap)
    # InferenceUnit also imports the CompilerCore type and feeds CrateSession.
    changed['InferenceUnit']=lambda s:s
owners={'Bootstrap.'+n for n in changed}
for name in sorted(owners):
    s=PATHS[name].read_text()
    s=changed[name.split('.')[-1]](s)
    s=one(s,'  import MLF.Primitive;', '  import qualified Prelude as HP;\n  import qualified WarmClock as Clock;\n  import MLF.Primitive;')
    def rename(match):
        prefix,mod=match.groups()
        return prefix+('Detail.' if mod in owners else '')+mod
    s=re.sub(r'^(module |\s*import (?:qualified )?)([A-Z][\w.]*)',rename,s,flags=re.M)
    target=OUT/'Detail'/(name.replace('.','/')+'.hs')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(s)
coarse=one(session(PATHS['Bootstrap.CrateSession'].read_text(),True),
           'module Bootstrap.CrateSession','module CoarseSession')
(OUT/'CoarseSession.hs').write_text(coarse)
host_file()
(OUT/'Main.hs').write_text('''module Main where
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Crate as C
import qualified Bootstrap.CrateSession as Plain
import qualified Detail.Bootstrap.CrateSession as Detail
import qualified CoarseSession as Coarse
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import qualified WarmClock as Clock
ok op = op >>= \\r -> case r of { T.Left err -> fail (B.unpack err); T.Right _ -> pure () }
main = runEntry $ do
  args <- getArgs
  case args of
    ["builtin", p] -> ok (C.ensureBuiltin (B.literal p))
    [mode,spec,p] -> let run f = f (B.literal spec) (B.literal p) in case mode of
      "P" -> ok (run Plain.compileSpecFile)
      "C" -> ok (run Coarse.compileSpecFile)
      "D" -> ok (Clock.io "session" (run Detail.compileSpecFile)) >> Clock.dump
      _ -> fail "unknown profile arm"
    _ -> fail "expected arm, spec, prefix"
''')
subprocess.run(['ghc','--make','-j3','-O2','-fpedantic-bottoms','-fno-state-hack','-package-env','-',
    '-i','-i'+str(OUT),'-i'+str(HERE),'-i'+str(HERE.parent),
    *['-i'+str(ROOT/r) for r in MANIFEST['source_roots']],'-outputdir',str(OUT/'obj'),'-optc-I'+str(ROOT/'runtime'),
    str(OUT/'Main.hs'),str(ROOT/'host/ghc/cbits/host.c'),str(ROOT/'runtime/mlf_process_supervisor.c'),
    '-o',str(OUT/'study')],check=True,cwd=OUT)
