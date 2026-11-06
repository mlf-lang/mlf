#!/usr/bin/env python3
"""Prepare/build a host-only demand-boundary overlay from an immutable producer.

The timing wrappers evaluate only Either WHNF where the existing monadic bind
already demands it. Inner AST/type thunks remain lazy: work is charged to the
phase that actually forces it, not the phase that constructs a thunk. Nested
timings are inclusive, so phase durations must not simply be summed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner

PROFILE = '''module Bootstrap.PreparedProfile (phase, phaseValue, phaseIO, report) where
import Prelude
import qualified Bootstrap.Types as T
import Control.Exception (evaluate)
import Data.IORef (IORef, newIORef, atomicModifyIORef', readIORef)
import qualified Data.Map.Strict as M
import GHC.Clock (getMonotonicTimeNSec)
import System.CPUTime (getCPUTime)
import System.IO (hPutStrLn, stderr)
import System.IO.Unsafe (unsafePerformIO)

{-# NOINLINE phase #-}
phase :: String -> T.Either a b -> T.Either a b
phase = phaseValue

{-# NOINLINE phaseValue #-}
phaseValue :: String -> a -> a
phaseValue label value = unsafePerformIO (phaseIO label (evaluate value))

{-# NOINLINE metrics #-}
metrics :: IORef (M.Map String (Integer, Integer, Integer))
metrics = unsafePerformIO (newIORef M.empty)

phaseIO :: String -> IO a -> IO a
phaseIO label action = do
  beforeCPU <- getCPUTime
  beforeWall <- getMonotonicTimeNSec
  result <- action
  afterWall <- getMonotonicTimeNSec
  afterCPU <- getCPUTime
  atomicModifyIORef' metrics (\\table ->
    let add (a,b,c) (x,y,z) = (a+x,b+y,c+z)
        updated = M.insertWith add label (afterCPU-beforeCPU, toInteger (afterWall-beforeWall), 1) table
    in (updated, ()))
  pure result

report :: IO ()
report = do
  table <- readIORef metrics
  mapM_ (\\(label,(cpu,wall,count)) -> hPutStrLn stderr
    ("PROFILE\\t" ++ label ++ "\\t" ++ show (fromIntegral cpu / 1.0e12 :: Double) ++
     "\\t" ++ show (fromIntegral wall / 1.0e9 :: Double) ++ "\\t" ++ show count)) (M.toList table)
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(source, old, new, count=1):
    if source.count(old) != count:
        raise RuntimeError('instrumentation source shape changed: ' + old)
    return source.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'build'])
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--deep', action='store_true')
    parser.add_argument('--solver', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    receipt_path = out / 'receipt.json'
    if args.operation == 'prepare':
        producer_path = args.producer.resolve(strict=True)
        producer = json.loads(producer_path.read_text())
        if not producer.get('complete') or not producer.get('immutable_inputs_verified_after'):
            raise RuntimeError('complete immutable producer required')
        for path, expected in producer['compiled_snapshot_pins'].items():
            if sha(path) != expected:
                raise RuntimeError('producer snapshot changed: ' + path)
        tools = {path: expected for path, expected in producer['source_pins'].items()
                 if not Path(path).is_relative_to(ROOT)}
        for path, expected in tools.items():
            if sha(path) != expected:
                raise RuntimeError('producer tool changed: ' + path)
        raw = producer['generated_raw_ast']
        if sha(raw['path']) != raw['sha256']:
            raise RuntimeError('producer generated raw data changed')
        original = producer_path.parent
        out.mkdir(parents=True, exist_ok=False)
        shutil.copytree(original / 'source', out / 'source')
        shutil.copytree(original / 'generated', out / 'generated')
        for path, expected in producer['compiled_snapshot_pins'].items():
            copied = Path(str(path).replace(str(original), str(out), 1))
            if sha(copied) != expected:
                raise RuntimeError('snapshot copy changed: ' + str(copied))
        if sha(out / 'generated/Bootstrap/PreparedBuiltinData.hs') != raw['sha256']:
            raise RuntimeError('generated raw data changed during copy')
        solver_overlay = None
        if args.solver:
            solver = args.solver.resolve(strict=True)
            solver_overlay = {'path': str(solver), 'sha256': sha(solver)}
            solver_target = out / 'source/libraries/mlf-inference/Bootstrap/Graph/Solver.hs'
            solver_target.write_bytes(solver.read_bytes())
            if sha(solver_target) != solver_overlay['sha256']:
                raise RuntimeError('solver changed while snapshotting')
        (out / 'objects').mkdir()
        here = out / 'source/tools/experimental/prepared-prelude/source'
        target = here / 'Bootstrap/PreparedPreludeWholeRoot.hs'
        source = target.read_text()
        source = replace(source, '  import MLF.Primitive;', '  import MLF.Primitive;\n  import qualified Bootstrap.PreparedProfile as Profile;')
        source = replace(source, '    Artifact.validateInterface iface;',
            '    Profile.phase "restore-interface" (Artifact.validateInterface iface);')
        source = replace(source, '    Artifact.validateDependencies byName iface;',
            '    Profile.phase "restore-dependencies" (Artifact.validateDependencies byName iface);')
        source = replace(source, '    Artifact.validateExportBoundary byName iface;',
            '    Profile.phase "restore-exports" (Artifact.validateExportBoundary byName iface);')
        source = replace(source, '    Artifact.validateLayouts ((:) iface []);',
            '    Profile.phase "restore-layouts" (Artifact.validateLayouts ((:) iface []));')
        source = replace(source,
            '    linked <- Artifact.linkCrate byName layouts (Artifact.FragmentState 0 M.empty [] [] S.empty) object;',
            '    linked <- Profile.phase "restore-link" (Artifact.linkCrate byName layouts (Artifact.FragmentState 0 M.empty [] [] S.empty) object);')
        source = replace(source, '    contracts <- sourceContracts iface sourceValues;',
            '    contracts <- Profile.phase "restore-contracts" (sourceContracts iface sourceValues);')
        source = replace(source, '  sourcePhase phase root result =',
            '  timedSourcePhase label phase root result = Profile.phase label (sourcePhase phase root result);\n  sourcePhase phase root result =')
        source = replace(source,
            '      root <- Core.atPhase ModuleResolution (Standalone.rewriteRootWithNames mode names env program);',
            '      root <- Profile.phase "rewrite-root" (Core.atPhase ModuleResolution (Standalone.rewriteRootWithNames mode names env program));')
        for binding, label in [('ownData', 'canonical-data'), ('ownClasses', 'canonical-classes'),
                               ('fullLowered' if 'fullLowered <-' in source else 'lowered', 'class-lowering')]:
            source = replace(source, binding + ' <- sourcePhase Inference root',
                             binding + ' <- timedSourcePhase "' + label + '" Inference root')
        if 'compiled <- if direct then' in source:
            direct_finish = '''        compiled <- if direct then mapEither ImportedRoot (finishImported root selectedSignatures lowered)
          else mapEither (\\value -> SyntheticRoot value (Imported.referenceCounts selectedSignatures (fst lowered)))
            (finishRoot root lowered);'''
            source = replace(source, direct_finish,
                direct_finish.replace('compiled <- ', 'compiled <- Profile.phase "finish-root" (', 1)[:-1] + ');')
        else:
            source = replace(source, '        compiled <- finishRoot root lowered;',
                '        compiled <- Profile.phase "finish-root" (finishRoot root lowered);')
        if ('Parameters.remove selectedSignatures' in source or
                '(if direct then Imported.remove else Parameters.remove)' in source):
            source = replace(source,
                '        selected <- Core.atPhase Verification\n          (if demand then Parameters.select signatures fullLowered else Right ((,) fullLowered signatures));',
                '        selected <- Profile.phase "import-selection" (Core.atPhase Verification\n          (if demand then Parameters.select signatures fullLowered else Right ((,) fullLowered signatures)));')
            removal = 'Parameters.remove selectedSignatures'
        else:
            removal = 'Separate.removeEntryParameters signatures'
        if '(if direct then Imported.remove else Parameters.remove)' in source:
            source = replace(source,
                '''        actualRoot <- Core.atPhase Verification
          ((if direct then Imported.remove else Parameters.remove) selectedSignatures (Artifact.fragmentBindings linked) fresh);''',
                '''        actualRoot <- Profile.phase "remove-parameters" (Core.atPhase Verification
          ((if direct then Imported.remove else Parameters.remove) selectedSignatures (Artifact.fragmentBindings linked) fresh));''')
        else:
            source = replace(source,
                '        actualRoot <- Core.atPhase Verification (' + removal + ' (Artifact.fragmentBindings linked) fresh);',
                '        actualRoot <- Profile.phase "remove-parameters" (Core.atPhase Verification (' + removal + ' (Artifact.fragmentBindings linked) fresh));')
        source = replace(source,
            '        declarations <- Core.atPhase Verification\n          (foldEither Separate.mergeDeclaration rootData (Artifact.fragmentData linked));',
            '        declarations <- Profile.phase "merge-layouts" (Core.atPhase Verification\n          (foldEither Separate.mergeDeclaration rootData (Artifact.fragmentData linked)));')
        source = replace(source,
            '        grafted <- Core.atPhase Verification\n          (foldEither (\\rootBody declarationSpine -> Separate.graft declarationSpine rootBody)\n            actualRoot (Artifact.fragmentBodies linked));',
            '        grafted <- Profile.phase "graft" (Core.atPhase Verification\n          (foldEither (\\rootBody declarationSpine -> Separate.graft declarationSpine rootBody)\n            actualRoot (Artifact.fragmentBodies linked)));')
        source = replace(source, '        checked <- Core.atPhase Verification (Checked.check (XWithData declarations grafted));',
            '        checked <- Profile.phase "final-check" (Core.atPhase Verification (Checked.check (XWithData declarations grafted)));')
        target.write_text(source)
        (here / 'Bootstrap/PreparedProfile.hs').write_text(PROFILE)
        target = here / 'Harness.hs'
        source = target.read_text()
        source = replace(source, 'import Prelude hiding (Either(..), Maybe(..))',
                         'import Prelude hiding (Either(..), Maybe(..))\nimport qualified Bootstrap.PreparedProfile as Profile')
        source = replace(source, 'main = do', 'main = do { Profile.phaseIO "total" runMain; Profile.report }\nrunMain = do')
        source = replace(source, 'context <- require prepared', 'context <- Profile.phaseIO "restore-context" (require prepared)', 2)
        source = replace(source,
            'source <- require (Parser.parseModule (P.textFromChars path) (P.textFromChars bytes))',
            'source <- Profile.phaseIO "parse-source" (require (Parser.parseModule (P.textFromChars path) (P.textFromChars bytes)))')
        source = replace(source, 'result <- compileRequire outcome',
            'result <- Profile.phaseIO "whole-root" (compileRequire outcome)')
        output_count = 4 if '"--direct-emit-llvm-gc" ->' in source else 3 if '"--full-emit-llvm-gc" ->' in source else 2
        source = replace(source,
            'require (LLVM.emitCheckedChunks False checked) >>= mapM_ (putStr . P.textToChars)',
            'Profile.phaseIO "llvm-and-output" (require (LLVM.emitCheckedChunks False checked) >>= mapM_ (putStr . P.textToChars))', output_count)
        target.write_text(source)
        if args.deep:
            def add_import(path):
                contents = path.read_text()
                return replace(contents, '  import MLF.Primitive;',
                    '  import MLF.Primitive;\n  import qualified Bootstrap.PreparedProfile as Profile;')

            def wrap_function(contents, name, arguments, label):
                definition = '  ' + name + ' ' + arguments + ' ='
                return replace(contents, definition, definition + '\n    Profile.phase "' + label + '" (' +
                    name + 'Profile ' + arguments + ');\n  ' + name + 'Profile ' + arguments + ' =')

            target = out / 'source/libraries/mlf-inference/Bootstrap/CompilerCore.hs'
            source = add_import(target)
            source = replace(source, 'constraints <- atPhase Inference (C.generateProgram program);',
                'constraints <- Profile.phase "core-generate" (atPhase Inference (C.generateProgram program));')
            source = replace(source, 'solved <- atPhase Inference (C.solvePrepared constraints);',
                'solved <- Profile.phase "core-solve" (atPhase Inference (C.solvePrepared constraints));')
            source = replace(source, 'evidence <- atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints));',
                'evidence <- Profile.phase "core-evidence" (atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints)));')
            source = replace(source, '            atPhase Elaboration\n              (E.elaboratePreparedIn types solved evidence (C.skeleton constraints));',
                '            Profile.phase "core-elaborate" (atPhase Elaboration\n              (E.elaboratePreparedIn types solved evidence (C.skeleton constraints)));')
            source = replace(source, 'checked <- atPhase Verification (Checked.check term);',
                'checked <- Profile.phase "core-check" (atPhase Verification (Checked.check term));')
            source = replace(source, 'L.not (T.alphaEq ty expected)',
                'L.not (Profile.phaseValue "core-type-equality" (T.alphaEq ty expected))')
            source = replace(source, '(X.equalErased (X.erase term)\n                       (C.eraseSourceWith evidence (C.skeleton constraints)))',
                '(Profile.phaseValue "core-erasure-equality" (X.equalErased (X.erase term)\n                       (C.eraseSourceWith evidence (C.skeleton constraints))))')
            target.write_text(source)
            target = here / 'Bootstrap/PreparedImportedCore.hs'
            if target.is_file():
                source = add_import(target)
                for old, new in [
                    ('generated <- Core.atPhase Inference (generate signatures program);',
                     'generated <- Profile.phase "direct-generate" (Core.atPhase Inference (generate signatures program));'),
                    ('solved <- Core.atPhase Inference (C.solvePrepared constraints);',
                     'solved <- Profile.phase "direct-solve" (Core.atPhase Inference (C.solvePrepared constraints));'),
                    ('evidence <- Core.atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints));',
                     'evidence <- Profile.phase "direct-evidence" (Core.atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints)));'),
                    ('body <- Core.atPhase Elaboration (E.elaboratePreparedIn types solved evidence (C.skeleton constraints));',
                     'body <- Profile.phase "direct-elaborate" (Core.atPhase Elaboration (E.elaboratePreparedIn types solved evidence (C.skeleton constraints)));'),
                    ('checked <- Core.atPhase Verification (Checked.check term);',
                     'checked <- Profile.phase "direct-check" (Core.atPhase Verification (Checked.check term));'),
                    ('ensure (T.alphaEq (Checked.typeOf checked) expected)',
                     'ensure (Profile.phaseValue "direct-type-equality" (T.alphaEq (Checked.typeOf checked) expected))'),
                    ('ensure (X.equalErased (X.erase term) erased)',
                     'ensure (Profile.phaseValue "direct-erasure-equality" (X.equalErased (X.erase term) erased))'),
                    ('      parameters <- Core.atPhase Verification (traverseEither',
                     '      parameters <- Profile.phase "direct-contracts" (Core.atPhase Verification (traverseEither'),
                    ('        }) imports);', '        }) imports));'),
                ]:
                    source = replace(source, old, new)
                target.write_text(source)
            target = out / 'source/libraries/mlf-inference/Bootstrap/Constraint.hs'
            source = add_import(target)
            source = replace(source, '  runGenerate (Generate f) state = f state;', '''  runGenerate (Generate f) state = f state;
  profileGenerate label action = Generate (\\state -> Profile.phase label (runGenerate action state));
  profileImportStub core = case core of {
    CChecked _ (SApp (SPrimitive PPanic) (SStringLit message)) -> eqString message "unlinked module parameter";
    _ -> False
  };''')
            source = replace(source, '          datatypes <- D.validateDeclarations declarations;',
                '          datatypes <- Profile.phase "generate-datatypes" (D.validateDeclarations declarations);')
            source = replace(source, '          lowered <- Surface.lowerExpression expression;',
                '          lowered <- Profile.phase "generate-surface" (Surface.lowerExpression expression);')
            source = replace(source, '          validateAnnotations datatypes lowered;',
                '          Profile.phase "generate-annotations" (validateAnnotations datatypes lowered);')
            source = replace(source, '            runGenerate (build datatypes M.empty Nothing M.empty (desugar lowered))\n              (Generation G.emptyGraph [] []);',
                '            Profile.phase "generate-build" (runGenerate (build datatypes M.empty Nothing M.empty (desugar lowered))\n              (Generation G.emptyGraph [] []));')
            source = replace(source, '  build datatypes typeScope parent env core =', '''  build datatypes typeScope parent env core =
    profileGenerate (if profileImportStub core then "build-import-stub" else "build-other-node")
      (buildProfile datatypes typeScope parent env core);
  buildProfile datatypes typeScope parent env core =''')
            source = replace(source, '  declareRecursive datatypes gen definition =', '''  declareRecursive datatypes gen definition =
    profileGenerate (case definition of { (,,) _ _ core -> if profileImportStub core then "declare-import-stub" else "declare-own-signature" })
      (declareRecursiveProfile datatypes gen definition);
  declareRecursiveProfile datatypes gen definition =''')
            source = replace(source, '      prepared <- Solver.prepare (initialGraph constraints);',
                '      prepared <- Profile.phase "solve-prepare" (Solver.prepare (initialGraph constraints));')
            source = replace(source, '      initial <- Solver.solverUnify (equalities constraints) prepared;',
                '      initial <- Profile.phase "solve-equalities" (Solver.solverUnify (equalities constraints) prepared);')
            source = replace(source, '      solved <- evaluateSteps initial (solveSteps constraints);',
                '      solved <- Profile.phase "solve-steps" (evaluateSteps initial (solveSteps constraints));')
            source = replace(source, '      Solver.finishNormalized solved',
                '      Profile.phase "solve-finish" (Solver.finishNormalized solved)')
            target.write_text(source)
            for filename, functions in [
                ('Graph.hs', [('validateGraph', 'graph', 'graph-validate'), ('kindsAt', 'graph starts', 'graph-kinds'),
                              ('unify', 'equations before', 'graph-unify'), ('rebind', 'old skeleton', 'graph-rebind')]),
                ('Graph/Solver.hs', [('prepare', 'input', 'solver-prepare'), ('finish', 'solver', 'solver-finish'),
                    ('unifyDistinct', 'equations solver', 'solver-project-unify'),
                    ('expanded', 'source target solver', 'solver-expand'),
                    ('instantiateClosed', 'source target solver', 'solver-instantiate-closed')])]:
                target = out / ('source/libraries/mlf-inference/Bootstrap/' + filename)
                source = add_import(target)
                for name, arguments, label in functions:
                    source = wrap_function(source, name, arguments, label)
                if filename == 'Graph/Solver.hs':
                    for name, arguments, label in [
                        ('validFreshFragment', 'root parent fresh next', 'solver-fresh-fragment'),
                        ('expansionBottomGraft', 'first target root frontier solver', 'solver-graft-attempt'),
                        ('congruentExpansionGraft', 'first originalTarget root frontier solver', 'solver-congruent-graft'),
                    ]:
                        definition = '  ' + name + ' ' + arguments + ' ='
                        if definition in source:
                            source = replace(source, definition, definition +
                                '\n    Profile.phaseValue "' + label + '" (' + name + 'Profile ' + arguments +
                                ');\n  ' + name + 'Profile ' + arguments + ' =')
                target.write_text(source)
            target = out / 'source/libraries/mlf-crates/Bootstrap/CrateArtifact.hs'
            source = add_import(target)
            source = replace(source, '      checked <- Separate.objectChecked fragment;',
                '      checked <- Profile.phase "fragment-independent-check" (Separate.objectChecked fragment);')
            source = replace(source, 'Right (Separate.freshCheckedObject serial checked)',
                'Right (Profile.phaseValue "fragment-fresh-whnf" (Separate.freshCheckedObject serial checked))')
            checksum = '''            ensure
              (eqString
                 (Separate.fingerprintAfter
                    (contextState allowedLayouts (Separate.objectContext fragment))
                    (Pretty.prettyTerm (Separate.objectBody fragment)))
                 (Separate.unitObjectFingerprint recorded))
              "inference fragment checksum mismatch"'''
            source = replace(source, checksum, '            Profile.phase "fragment-checksum" (\n' + checksum + ')')
            source = replace(source, '                  D.validateDeclarations ds;',
                '                  Profile.phase "fragment-datatype-check" (D.validateDeclarations ds);')
            source = replace(source, '                  own <- checkedBindings;',
                '                  own <- Profile.phase "fragment-binding-inventory" checkedBindings;')
            schemes = '''                  ensure (sameSchemes actual (Separate.unitBindings recorded))
                    "crate fragment binding scheme mismatch"'''
            source = replace(source, schemes, '                  Profile.phase "fragment-scheme-match" (\n' + schemes + ')')
            target.write_text(source)
        commands = []
        for row in producer['commands']:
            if row['label'] in ['host', 'supervisor', 'build-prototype']:
                commands.append({'label': row['label'],
                    'argv': [arg.replace(str(original), str(out)) for arg in row['argv']]})
        inputs = {str(path): sha(path) for folder in ['source', 'generated'] for path in (out / folder).rglob('*') if path.is_file()}
        receipt = {'complete': False, 'prepared': True, 'scope': 'host-only Either-WHNF demand profiling overlay',
                   'producer': str(producer_path), 'producer_sha256': sha(producer_path),
                   'deep_core_graph_profile': args.deep, 'solver_overlay': solver_overlay,
                   'phase_times_inclusive': True, 'inner_thunks_not_forced_by_timer': True,
                   'commands': commands, 'inputs': inputs,
                   'controller_inputs': {**tools, **{str(path): sha(path) for path in
                        [Path(__file__).resolve(), Path(sys.executable).resolve(), ROOT / 'tools/shared/test_direct.py']}}}
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        print(receipt_path)
        return
    receipt = json.loads(receipt_path.read_text())
    try:
        for path, expected in {**receipt['inputs'], **receipt['controller_inputs']}.items():
            if sha(path) != expected:
                raise RuntimeError('profile input changed before build: ' + path)
        for row in receipt['commands']:
            with (out / (row['label'] + '.stdout')).open('wb') as stdout, (out / (row['label'] + '.stderr')).open('wb') as stderr:
                process = subprocess.Popen(row['argv'], cwd=out / 'source',
                    env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'},
                    stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    process.communicate(timeout=600)
                except BaseException:
                    _, _, receipt['cleanup'] = CommandRunner.stop_group(process)
                    raise
                row['exit'] = process.returncode
                if process.returncode:
                    raise RuntimeError('profile build failed: ' + row['label'])
        receipt.update(complete=True, executable=str(out / 'prepared-emlf'), executable_sha256=sha(out / 'prepared-emlf'))
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in {**receipt['inputs'], **receipt['controller_inputs']}.items() if sha(path) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        if changed:
            raise RuntimeError('profile inputs changed')
    print(receipt['executable'])


if __name__ == '__main__':
    main()
