#!/usr/bin/env python3
"""Create reversible private progress owners for exact current-main f9bdb40.

Diagnostic only. Fixed labels update KindCounters, never inspect an AST. No
production source is changed. The combined F1 harness alone compiles/runs these
owners, with its Type counters, in one bounded diagnostic (not timing evidence).
"""
from pathlib import Path
import argparse, difflib, hashlib, json

OWNERS = {
    'CrateSession': 'a13c01632001643b683e54c10775eb9a262faf0d6766c52209a3ec0704fd9bdd',
    'CrateGraph': '52b0fcf312aec770515980f78d0ee44e1f29e248c496468536f44f20495880ee',
}

def sha(value):
    return hashlib.sha256(value).hexdigest()

def instrument(name, original):
    source = original.decode()
    changes = []
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError(f'{name}: expected exactly one anchor {old[:90]!r}, got {source.count(old)}')
        source = source.replace(old, new, 1)
        changes.append((old, new))
    def before(anchor, label, kind='event'):
        indent = anchor[:len(anchor)-len(anchor.lstrip())]
        replace(anchor, indent + 'Progress.' + kind + ' "' + label + '";\n' + anchor)
    def after(anchor, label, kind='event'):
        indent = anchor[:len(anchor)-len(anchor.lstrip())]
        replace(anchor, anchor + '\n' + indent + 'Progress.' + kind + ' "' + label + '";')
    replace('  import MLF.Primitive;', '  import MLF.Primitive;\n  import qualified KindCounters as Progress;')
    if name == 'CrateSession':
        before('      present <- fileExists file;', 'session.spec.enter', 'boundary')
        before('             text <- readFile file;', 'session.spec.read', 'boundary')
        after('             text <- readFile file;', 'session.spec.decode.await', 'boundary')
        before('                   sourceResult <- loadSourcesInPackage (specIdentity spec) (specSources spec);',
               'session.source-load.enter', 'boundary')
        after('                   sourceResult <- loadSourcesInPackage (specIdentity spec) (specSources spec);',
              'session.source-load.returned', 'boundary')
        before('                   dependencies <- Artifact.loadInterfaces paths;', 'session.dependencies.enter', 'boundary')
        after('                   dependencies <- Artifact.loadInterfaces paths;', 'session.dependencies.returned', 'boundary')
        before('      dependencies <- withPreludeUsing install spec sources interfaces;', 'session.prelude.enter', 'boundary')
        after('      dependencies <- withPreludeUsing install spec sources interfaces;', 'session.prepare-crate.await-whnf', 'boundary')
        before('            result <- compileGraphSources verifyAll updated loaded prepared (preparedSourcePlan prepared) prefix;',
               'session.prepare-crate.returned-whnf', 'boundary')
        before('      lock <- acquireFileLock (directory ++ "/.lock");', 'graph.lock.enter', 'boundary')
        after('      lock <- acquireFileLock (directory ++ "/.lock");', 'graph.lock.acquired', 'boundary')
        before('    compiler <- fileDigest executable;', 'graph.compiler-digest.enter', 'boundary')
        after('    compiler <- fileDigest executable;', 'graph.compile.enter', 'boundary')
        before('    case compiled of { Left e -> ioReturn (Left e); Right state -> case CrateGraph.checkedResult state of {',
               'graph.compile.returned', 'boundary')
        before('          made <- Artifact.makeOpenObject iface (map snd interfaces) (map (\\((,,) n f _) -> (,) n f) fragments);',
               'output.make-object.enter', 'boundary')
        before('            written <- Artifact.writeObjectEither prefix object;', 'output.write-object.enter', 'boundary')
        after('            written <- Artifact.writeObjectEither prefix object;', 'output.write-object.returned', 'boundary')
        before('              published <- QueryGraph.publish session;', 'query.publish.enter', 'boundary')
        after('              published <- QueryGraph.publish session;', 'query.publish.returned', 'boundary')
    else:
        before('        statistics <- G.profile;', 'graph.start', 'boundary')
        before('        started <- G.begin (cacheDir ++ "/query-graph-v2")', 'graph.begin.enter', 'boundary')
        # This label is reached only when begin returned Right; it does not force
        # any contract payload, merely precedes the existing initial recording.
        before('          initial <- case contracts of { Source.CheckedContracts scope indexed _ ->',
               'graph.initial-bindings.enter', 'boundary')
        before('            loaded <- recordDatatypes datatypes first;', 'graph.datatypes.enter', 'boundary')
        before('              G.elapsed statistics 0 graphStarted;', 'graph.initial-inputs.returned', 'boundary')
        old_prefix = '''  runGroups verify audit crateId inventory groups state = case groups of {
    [] -> ioReturn (Right state);
    (:) ((,) owners prepare) rest -> case state of {
'''
        new_prefix = '''  runGroups verify audit crateId inventory groups state = do {
    Progress.event "scc.next";
    case groups of {
      [] -> do { Progress.boundary "groups.complete"; ioReturn (Right state) };
      (:) ((,) owners prepare) rest -> do {
        Progress.event "scc.begin";
        runGroupStep verify audit crateId inventory owners prepare rest state
      }
    }
  };
  runGroupStep verify audit crateId inventory owners prepare rest state = case state of {
'''
        replace(old_prefix, new_prefix)
        replace('''        }
    }
  };
  -- One canonical content address''', '''        }
    };
  -- One canonical content address''')
        before('            graphStarted <- G.clock statistics;', 'scc.prepared')
        before('            source <- input (groupKey PreparedQuery slots) (preparedValue slots prepared) session;', 'scc.prepared-record.enter')
        before('              scopeInput <- input (groupKey ScopeInventoryQuery slots) (scopeInventory prepared) first;', 'scc.scope-inventory.enter')
        before('                    scoped <- G.record (groupKey ScopeQuery slots)', 'scc.scope-record.enter')
        before('                        loadStarted <- G.clock statistics;', 'scc.cache-load.enter')
        before('                        inferStarted <- G.clock statistics;', 'scc.raw-infer.await-whnf')
        before('                          recorded <- if hit then case previous of {', 'scc.raw-record.enter')
        before('                          finishStarted <- G.clock statistics;', 'scc.finish.enter')
        before('                                evidence <- resolveRequests env slots ((:) (G.edge scopeNode) (map G.edge dataNodes))', 'scc.finish-evidence.enter')
        before('                                content <- finishContentHash (verify || audit) group body final rawNode references finalRefs;', 'scc.finish-content.enter')
        before('                                supplied <- case content of { Left e -> ioReturn (Left e); Right hash ->', 'scc.finish-record.enter')
        anchor = '                                    G.elapsed statistics 3 finishStarted;'
        after(anchor, 'scc.finish-record.returned')
        replace('''                                    runGroups verify audit crateId inventory rest''', '''                                    Progress.event (if hit then "scc.finished.reused" else "scc.finished.fresh");
                                    runGroups verify audit crateId inventory rest''')
    restored = source
    for old, new in reversed(changes):
        if restored.count(new) != 1:
            raise ValueError(f'{name}: inverse anchor ambiguous')
        restored = restored.replace(new, old, 1)
    if restored.encode() != original:
        raise ValueError(f'{name}: inverse did not recover original bytes')
    return source.encode(), len(changes)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = args.source.resolve(strict=True)
    output = args.output.absolute()
    if output.exists():
        raise ValueError('fresh private output required')
    results = {}
    for name, expected in OWNERS.items():
        source = root / ('libraries/mlf-crates/Bootstrap/' + name + '.hs')
        old = source.read_bytes()
        if sha(old) != expected:
            raise ValueError('not the exact f9bdb40 owner: ' + name)
        new, changes = instrument(name, old)
        results[name] = (old, new, changes, source)
    (output / 'Bootstrap').mkdir(parents=True)
    receipt = {'format': 1, 'kind': 'private-diagnostic-not-producer', 'baseline_commit':
               'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1', 'transform_sha256': sha(Path(__file__).read_bytes()),
               'owners': {}, 'notes': [
               'Fixed labels do not inspect or retain ASTs.',
               'returned/WHNF labels are not claims of deep normal form.',
               'SCC completion means the original successful finish-record branch was reached.',
               'No query writer, checks, cache conditions or success/error decisions are removed.',
               'Source-load and prepare-crate windows are not separate parse/resolve/lower measurements.',
               'The combined F1 harness alone owns compilation and its single 120-second diagnostic.']}
    for name, (old,new,count,source) in results.items():
        target = output / 'Bootstrap' / (name + '.hs')
        target.write_bytes(new)
        patch = ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                           fromfile=str(source), tofile=str(target)))
        (output / (name + '.patch')).write_text(patch)
        receipt['owners'][name] = {'source': str(source), 'source_sha256': sha(old),
                                  'private_source': str(target), 'private_sha256': sha(new),
                                  'reversible_changes': count, 'inverse_matches_source': True}
    (output / 'progress-transform.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
