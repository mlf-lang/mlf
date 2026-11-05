#!/usr/bin/env python3
"""Pinned private demand instrumentation of batching, not a timing benchmark.

Uses the established inline-traversals transport, controls, dependency closure,
and byte-comparison harness. Only diagnostic modules are compiled. This runner
requires the frozen baseline producer and baseline source; source pins are
recorded before compilation and rechecked after all output has been consumed.
"""
from pathlib import Path
import hashlib
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[3]
INLINE = ROOT / 'tools/performance/inline-traversals'
BASELINE = ROOT / '.mlf-build/batch-replacement-20261101/baseline-source'
PRODUCER = ROOT / '.mlf-build/batch-replacement-20261101/baseline-producer'
SCRATCH = ROOT / '.mlf-build/batch-replacement-20261101'
sys.path.insert(0, str(INLINE))
import instrument as I
_LEGACY_OPTIMIZE, _LEGACY_LLVM = I.optimize, I.llvm


def candidate(raw):
    I._mechanism_opt_source = I.sha(raw)
    # The pre-existing transform is source-pinned at invocation and independently
    # reversible. The runner additionally pins actual source before/after runs.
    pre = I.Patch(raw, I.sha(raw))
    pre.change('  optimizeOwnedWork expression =\n    do {\n      unique <- copy M.empty expression;',
               '  optimizeOwnedWork expression =\n    do {\n      unique <- copy (M.empty) expression;')
    pre.change('  optimizeOwned expression =\n    case runFresh (optimizeOwnedWork expression) (L.advanceIdentity 1 (maxIdentity expression)) of {\n      (,) normalized seed ->\n        case runFresh (copy M.empty normalized) 0 of {',
               '  optimizeOwned expression =\n    case runFresh (optimizeOwnedWork expression) (L.advanceIdentity 1 (maxIdentity expression)) of {\n      (,) normalized seed ->\n        case runFresh (copy (M.empty) normalized) 0 of {')
    prepared, preliminary = pre.finish()
    I.OPTIMIZE_SHA = I.sha(prepared)
    transformed, first = _LEGACY_OPTIMIZE(prepared)
    p = I.Patch(transformed, I.sha(transformed))
    p.change('copy (M.empty) expression', 'copyFrom "copy.owned_initial_uniqueness" M.empty expression')
    p.change('copy (M.empty) normalized', 'copyFrom "copy.owned_final_numbering" M.empty normalized')
    p.change('copied <- copy M.empty (useTerm value);', 'copied <- copyFrom "copy.batch_admitted" M.empty (useTerm value);')
    p.change('  negativeCalls tree =\n    case useChildren tree of {', '''  negativeCalls tree = C.tick "batch.negative.roots" 0 (negativeCallsAt 0 tree);
  negativeCallsAt :: Int -> UseTree -> Set XName;
  negativeCallsAt depth tree = C.tick "batch.negative.visits" depth (case useChildren tree of {''')
    def negative(block):
        block = block.replace('negativeCalls body', 'negativeCallsAt (depth + 1) body')
        block = block.replace('negativeCalls function', 'negativeCallsAt (depth + 1) function')
        block = block.replace('negativeCalls argument', 'negativeCallsAt (depth + 1) argument')
        block = block.replace('negativeCalls value', 'negativeCallsAt (depth + 1) value')
        block = block.replace('negativeCalls (L.snd entry)', 'negativeCallsAt (depth + 1) (L.snd entry)')
        block = block.replace('negativeCalls subject', 'negativeCallsAt (depth + 1) subject')
        old = '    };\n  -- The base skeleton'
        if block.count(old) != 1:
            raise ValueError('negativeCalls trailing anchor changed')
        return block.replace(old, '    });\n  -- The base skeleton')
    p.block('negativeCallsAt', 'pendingCounts', negative)
    p.change('  materializeBody replacements tree =\n    case useChildren tree of {', '''  materializeBody replacements tree = C.tick "batch.materialize.roots" 0 (materializeBodyAt 0 False replacements tree);
  materializeBodyAt :: Int -> Bool -> Map XName UseTree -> UseTree -> UseTree;
  materializeBodyAt depth fromReplacement replacements tree = C.tick "batch.materialize.visits" depth (C.tick (if fromReplacement then "batch.materialize.replacement_visits" else "batch.materialize.base_visits") depth (case useChildren tree of {''')
    def materialize(block):
        block = block.replace('materializeBody replacements ', 'materializeBodyAt (depth + 1) fromReplacement replacements ')
        block = block.replace('Just value -> materializeBodyAt (depth + 1) fromReplacement replacements value',
                              'Just value -> C.tick "batch.materialize.expanded_var" depth (materializeBodyAt (depth + 1) True replacements value)')
        if not block.endswith('    };\n'):
            raise ValueError('materializeBody trailing anchor changed')
        return block[:-7] + '    }));\n'
    p.block('materializeBodyAt', 'materializePending', materialize)
    p.change('if M.null replacements then body else materializeBody replacements body;',
             '''if M.null replacements
    then C.tick "batch.flush.empty" 0 body
    else C.tick "batch.flush.nonempty" 0
           (C.tick "batch.flush.env_size" (M.size replacements)
             (C.named "batch.flush.env_histogram" (Host.show (M.size replacements)) 0
               (materializeBody replacements body)));''')
    p.change('    then do {\n      copied <- copyFrom "copy.batch_admitted" M.empty (useTerm value);',
             '    then traceFresh "batch.admitted" 0 (do {\n      copied <- copyFrom "copy.batch_admitted" M.empty (useTerm value);')
    p.change('               (S.union compareName (S.delete compareName name calls) (negativeCalls replacement)))\n      }\n    }\n    else do {',
             '               (S.union compareName (S.delete compareName name calls) (negativeCalls replacement)))\n      }\n    })\n    else do {')
    def owned(block):
        block = block.replace('  passOwnedRaw expression = case expression of {',
                              '  passOwnedRaw expression = traceFresh "batch.owned.visits" 0 (case expression of {')
        if not block.endswith('  };\n'):
            raise ValueError('passOwnedRaw trailing anchor changed')
        return block[:-5] + '  });\n'
    p.block('passOwnedRaw', 'passOwned', owned)
    def pending(block):
        block = block.replace('  passPendingRaw expression = case expression of {',
                              '  passPendingRaw expression = traceFresh "batch.pending.visits" 0 (case expression of {')
        if not block.endswith('  };\n'):
            raise ValueError('passPendingRaw trailing anchor changed')
        return block[:-5] + '  });\n'
    p.block('passPendingRaw', 'passOwnedRaw', pending)
    result, second = p.finish()
    return result, {'preparation': preliminary, 'legacy_transform': first, 'batch_transform': second}


def candidate_llvm(raw):
    I._mechanism_llvm_source = I.sha(raw)
    I.LLVM_SHA = I.sha(raw)
    return _LEGACY_LLVM(raw)


def main():
    # Reuse the audited transport with exact-string checked adaptations; no
    # changes to the committed original harness or its admission controls.
    original = (INLINE / 'run.py').read_text()
    source = original
    replacements = [
        ("DEFAULT_PRODUCER = ROOT / '.mlf-build/owned-reservation-20261101/producer'", 'DEFAULT_PRODUCER = Path(' + repr(str(PRODUCER)) + ')'),
        ("scratch = (ROOT / '.mlf-build/inline-traversals-20261101').resolve()", 'scratch = Path(' + repr(str(SCRATCH)) + ').resolve()'),
        ('H.authenticate(producer, ROOT)', 'H.authenticate(producer, Path(' + repr(str(BASELINE)) + '))'),
        ("    for family in ('commonCalls', 'substituteUsed', 'identities', 'indexUses', 'passRaw'):", "    require(all(event(rows, key) > 0 for key in ('batch.owned.visits', 'batch.pending.visits', 'batch.admitted', 'batch.negative.visits', 'batch.flush.nonempty', 'batch.materialize.visits')), 'owned batching pipeline was not demanded')\n    require(event(rows, 'batch.materialize.visits') == event(rows, 'batch.materialize.base_visits') + event(rows, 'batch.materialize.replacement_visits'), 'materialization visit partition')\n    for family in ('commonCalls', 'substituteUsed', 'identities', 'indexUses'):") ,
        ("    for origin in ('initial_uniqueness', 'final_numbering'):", "    for origin in ('owned_initial_uniqueness', 'owned_final_numbering'):"),
        ("            pins.update(closure_pins)", "            pins.update(closure_pins)\n            require(pins[str(original_optimize)] == instrument._mechanism_opt_source and pins[str(original_llvm)] == instrument._mechanism_llvm_source, 'source changed during transformation')"),
        ("            inputs = [helper, ROOT / 'tools/shared/test_direct.py', config_path,", "            inputs = [Path(" + repr(str(Path(__file__).resolve())) + "), Path(" + repr(str(BASELINE)) + ") / 'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs', Path(" + repr(str(BASELINE)) + ") / 'libraries/mlf-llvm/Bootstrap/LLVM.hs', ROOT / 'libraries/mlf-llvm/Bootstrap/LLVM/Library.hs', helper, ROOT / 'tools/shared/test_direct.py', config_path,"),
    ]
    for before, after in replacements:
        expected = 2 if before == 'H.authenticate(producer, ROOT)' else 1
        if source.count(before) != expected:
            raise ValueError(('transport anchor changed', before, source.count(before)))
        source = source.replace(before, after)
    # Compiled runner's __file__ must remain the original transport path, as its
    # HERE/ROOT and private Main.hs/Counters.hs paths are part of the protocol.
    I.optimize = candidate
    I.llvm = candidate_llvm
    ns = {'__name__': '__main__', '__file__': str(INLINE / 'run.py')}
    exec(compile(source, str(INLINE / 'run.py'), 'exec'), ns)


if __name__ == '__main__':
    main()
