#!/usr/bin/env python3
"""Demand/order and allocation controls for conservative thunk lowering.

This gate executes fresh O0/O2 binaries against literal results. An optional
reference compiler must retain the eliminated allocation in the recursive-loop
control; it is not used as the value oracle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

from test_direct import CommandRunner, sha
from test_native_string_index import local_c_closure, require, resolve_tool

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    'scalar-loop': (
        'scan limit i state = if ltInt i limit then '
        'let next = addInt state 1 in if eqInt next 0 then 1 '
        'else scan limit (addInt i 1) (subInt next 1) else -1\n'
        'main = ioBind (getArg 0) (\\limit -> ioBind (getArg 1) (\\state -> '
        'printInt (scan (readInt limit) 0 (readInt state))))\n', [
            ('ordinary', ['1000', '3'], b'-1\n', b''),
            ('small-positive-boundary', ['20', '4611686018427387903'], b'-1\n', b''),
            ('large-positive', ['20', '18446744073709551616'], b'-1\n', b''),
            ('large-negative', ['20', '-18446744073709551616'], b'-1\n', b''),
            ('stop-branch', ['20', '-1'], b'1\n', b''),
            ('undemanded-state', ['0', 'not an integer'], b'-1\n', b''),
        ]),
    'unknown-arithmetic': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> '
        'printInt (choose (eqString flag "skip") (addInt (panic "late operand") 1)))\n', [
            ('unused-unknown', ['skip'], b'7\n', b''),
            ('demanded-unknown', ['take'], b'', b'Runtime: late operand\n'),
        ]),
    'conditional-loop': (
        'scan limit i state = if ltInt i limit then '
        'let next = addInt state 1 in if eqInt next 0 then 1 '
        'else scan limit (addInt i 1) (if eqInt next 0 then 0 else subInt next 1) else -1\n'
        'main = ioBind (getArg 0) (\\limit -> ioBind (getArg 1) (\\state -> '
        'printInt (scan (readInt limit) 0 (readInt state))))\n', [
            ('ready-conditional-loop', ['1000', '3'], b'-1\n', b''),
            ('unused-conditional-state', ['0', 'not an integer'], b'-1\n', b''),
        ]),
    'unknown-condition': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> '
        'printInt (choose (eqString flag "skip") (if panic "condition failure" then 8 else 9)))\n', [
            ('unused-unknown-condition', ['skip'], b'7\n', b''),
            ('demanded-unknown-condition', ['take'], b'', b'Runtime: condition failure\n'),
        ]),
    'conditional-panic': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\mode -> ioBind (getArg 1) (\\flag -> '
        'let condition = eqString flag "then" in seq condition '
        '(printInt (choose (eqString mode "skip") (if condition then panic "branch failure" else 8)))))\n', [
            ('unused-panic-branch', ['skip', 'then'], b'7\n', b''),
            ('demanded-panic-branch', ['take', 'then'], b'', b'Runtime: branch failure\n'),
            ('untaken-panic-branch', ['take', 'else'], b'8\n', b''),
        ]),
    'conditional-division': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\mode -> ioBind (getArg 1) (\\flag -> '
        'let condition = eqString flag "then" in seq condition '
        '(printInt (choose (eqString mode "skip") (if condition then quotInt 5 0 else 8)))))\n', [
            ('unused-division-branch', ['skip', 'then'], b'7\n', b''),
            ('demanded-division-branch', ['take', 'then'], b'', b'Runtime: integer division by zero\n'),
            ('untaken-division-branch', ['take', 'else'], b'8\n', b''),
        ]),
    'conditional-index': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\mode -> ioBind (getArg 1) (\\flag -> '
        'let condition = eqString flag "then" in seq condition '
        '(printInt (choose (eqString mode "skip") (if condition then stringCodeAt "abc" (-1) else 8)))))\n', [
            ('unused-index-branch', ['skip', 'then'], b'7\n', b''),
            ('demanded-index-branch', ['take', 'then'], b'', b'Runtime: string index out of bounds\n'),
            ('untaken-index-branch', ['take', 'else'], b'8\n', b''),
        ]),
    'conditional-dominance': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> '
        'let condition = eqString flag "skip" in let value = panic "conditional sibling" in '
        'seq (if condition then 0 else value) '
        '(printInt (choose true (if condition then addInt value 1 else 8))))\n', [
            ('conditional-sibling-not-a-fact', ['skip'], b'7\n', b''),
            ('conditional-taken-force', ['take'], b'', b'Runtime: conditional sibling\n'),
        ]),
    'excluded-multiplication': (
        'scan limit i state = if ltInt i limit then '
        'let next = addInt state 1 in if eqInt next 0 then 1 '
        'else scan limit (addInt i 1) (mulInt next next) else -1\n'
        'main = ioBind (getArg 0) (\\limit -> ioBind (getArg 1) (\\state -> '
        'printInt (scan (readInt limit) 0 (readInt state))))\n', [
            ('demanded-products', ['6', '3'], b'-1\n', b''),
            # The first iteration forces next, but the base case does not need
            # its square. The shape assertion below proves it remains lazy;
            # this bound is a completion guard, not a timing qualification.
            ('unused-large-product', ['1', '9' * 8192], b'-1\n', b''),
        ]),
    'branch-dominance': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> let value = panic "branch operand" in '
        'seq (if eqString flag "take" then value else 0) '
        '(printInt (choose true (addInt value 1))))\n', [
            ('sibling-force-not-a-fact', ['skip'], b'7\n', b''),
            ('taken-force', ['take'], b'', b'Runtime: branch operand\n'),
        ]),
    'excluded-partial': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> '
        'printInt (choose (eqString flag "skip") (quotInt 5 0)))\n', [
            ('unused-division', ['skip'], b'7\n', b''),
            ('demanded-division', ['take'], b'', b'Runtime: integer division by zero\n'),
        ]),
    'excluded-index': (
        'choose flag value = if flag then 7 else value\n'
        'main = ioBind (getArg 0) (\\flag -> ioBind (getArg 1) (\\text -> '
        'ioBind (printInt (stringLength text)) (\\ignored -> '
        'printInt (choose (eqString flag "skip") (stringCodeAt text (-1))))))\n', [
            ('unused-ready-index', ['skip', 'abc'], b'3\n7\n', b''),
            ('demanded-ready-index', ['take', 'abc'], b'3\n', b'Runtime: string index out of bounds\n'),
        ]),
    'error-order': (
        'first a b = seq a (seq b 0)\n'
        'main = ioBind (putStrLn "before") (\\ignored -> '
        'printInt (first (panic "first failure") (addInt (panic "second failure") 1)))\n', [
            ('original-error-order', [], b'before\n', b'Runtime: first failure\n'),
        ]),
    'seq-demand': (
        'reverse first second = seq second (seq first 0)\n'
        'capture value = let inner argument = seq argument (seq value 0) '
        'in inner (panic "argument first")\n'
        'division value = seq (quotInt 5 0) value\n'
        'index value = seq (stringCodeAt "abc" (-1)) value\n'
        'panicFirst value = seq (panic "explicit first") value\n'
        'letFirst = let value = panic "later" in seq (quotInt 5 0) value\n'
        'success first second = seq second (seq first (addInt first second))\n'
        'rest value = seq 0 value\n'
        'run mode = if eqString mode "reverse" then reverse (panic "later") (panic "second first") '
        'else if eqString mode "capture" then capture (panic "later") '
        'else if eqString mode "division" then division (panic "later") '
        'else if eqString mode "index" then index (panic "later") '
        'else if eqString mode "panic" then panicFirst (panic "later") '
        'else if eqString mode "let" then letFirst '
        'else if eqString mode "success" then success 3 5 else rest (panic "rest required")\n'
        'main = ioBind (getArg 0) (\\mode -> '
        'ioBind (putStrLn "before") (\\ignored -> printInt (run mode)))\n', [
            ('seq-reversed-formals', ['reverse'], b'before\n', b'Runtime: second first\n'),
            ('seq-capture-after-argument', ['capture'], b'before\n', b'Runtime: argument first\n'),
            ('seq-internal-division-first', ['division'], b'before\n', b'Runtime: integer division by zero\n'),
            ('seq-internal-index-first', ['index'], b'before\n', b'Runtime: string index out of bounds\n'),
            ('seq-internal-panic-first', ['panic'], b'before\n', b'Runtime: explicit first\n'),
            ('seq-let-after-first', ['let'], b'before\n', b'Runtime: integer division by zero\n'),
            ('seq-both-successful', ['success'], b'before\n8\n', b''),
            ('seq-rest-still-demanded', ['rest'], b'before\n', b'Runtime: rest required\n'),
        ]),
    'first-demand': (
        'reverse first second = addInt second first\n'
        'capture value = let inner argument = subInt argument value '
        'in inner (panic "argument first")\n'
        'division first later = addInt (quotInt first 0) later\n'
        'index text later = addInt (stringCodeAt text (-1)) later\n'
        'appendJoined pieces suffix = concatString (concatStringList pieces) suffix\n'
        'aliasJoined pieces suffix = let joined = concatStringList pieces in '
        'let right = suffix in concatString joined right\n'
        'letOrder first later = let right = later in addInt (quotInt first 0) right\n'
        'ifOrder later condition = if condition then later else later\n'
        'ifInternal later = if eqInt (quotInt 5 0) 0 then later else later\n'
        'caseOrder later subject = case subject of { [] -> later; (:) first rest -> later }\n'
        'caseInternal later = case panic "case first" of { [] -> later; (:) first rest -> later }\n'
        'unknown function later = addInt (function 0) later\n'
        'closedScalar value = addInt (addInt 2 3) value\n'
        'sequence first second third = seq third (seq first (seq second 0))\n'
        'captureMix mode capturedFirst capturedSecond = '
        'let inner first second third = seq third '
        '(addInt second (addInt capturedSecond (addInt first capturedFirst))) in '
        'inner (if eqString mode "value" then 3 else panic "formal later") '
        '(if eqString mode "formal" then panic "formal before captures" else 1) 0\n'
        'run mode = if eqString mode "reverse" then reverse (panic "later") (panic "second first") '
        'else if eqString mode "capture" then capture (panic "later") '
        'else if eqString mode "division" then division 5 (panic "later") '
        'else if eqString mode "index" then index "abc" (panic "later") '
        'else if eqString mode "join-head" then stringLength (appendJoined [panic "head first"] (panic "suffix later")) '
        'else if eqString mode "join-tail" then stringLength (appendJoined ((:) "a" (panic "tail first")) (panic "suffix later")) '
        'else if eqString mode "join-alias" then stringLength (aliasJoined [panic "alias head first"] (panic "suffix later")) '
        'else if eqString mode "let" then letOrder 5 (panic "later") '
        'else if eqString mode "if" then ifOrder (panic "later") (panic "condition first") '
        'else if eqString mode "if-internal" then ifInternal (panic "later") '
        'else if eqString mode "case" then caseOrder (panic "later") (panic "subject first") '
        'else if eqString mode "case-internal" then caseInternal (panic "later") '
        'else if eqString mode "unknown" then unknown (\\value -> panic "call first") (panic "later") '
        'else if eqString mode "seq-three" then sequence (panic "first later") (panic "second later") (panic "third first") '
        'else if eqString mode "mixed-formal" then captureMix "formal" (panic "capture first later") (panic "capture second") '
        'else if eqString mode "mixed-capture" then captureMix "capture" (panic "capture first later") (panic "capture second") '
        'else if eqString mode "mixed-value" then captureMix "value" 4 2 '
        'else closedScalar 2\n'
        'main = ioBind (getArg 0) (\\mode -> '
        'ioBind (putStrLn "before") (\\ignored -> printInt (run mode)))\n', [
            ('first-reversed-formals', ['reverse'], b'before\n', b'Runtime: second first\n'),
            ('first-capture-after-argument', ['capture'], b'before\n', b'Runtime: argument first\n'),
            ('first-nested-division', ['division'], b'before\n', b'Runtime: integer division by zero\n'),
            ('first-nested-index', ['index'], b'before\n', b'Runtime: string index out of bounds\n'),
            ('first-deep-join-head', ['join-head'], b'before\n', b'Runtime: head first\n'),
            ('first-deep-join-tail', ['join-tail'], b'before\n', b'Runtime: tail first\n'),
            ('first-deep-join-alias', ['join-alias'], b'before\n', b'Runtime: alias head first\n'),
            ('first-let-order', ['let'], b'before\n', b'Runtime: integer division by zero\n'),
            ('first-if-formal-order', ['if'], b'before\n', b'Runtime: condition first\n'),
            ('first-if-internal-error', ['if-internal'], b'before\n', b'Runtime: integer division by zero\n'),
            ('first-case-formal-order', ['case'], b'before\n', b'Runtime: subject first\n'),
            ('first-case-internal-error', ['case-internal'], b'before\n', b'Runtime: case first\n'),
            ('first-unknown-call', ['unknown'], b'before\n', b'Runtime: call first\n'),
            ('ordered-seq-three-formals', ['seq-three'], b'before\n', b'Runtime: third first\n'),
            ('ordered-formal-before-captures', ['mixed-formal'], b'before\n', b'Runtime: formal before captures\n'),
            ('ordered-capture-between-formals', ['mixed-capture'], b'before\n', b'Runtime: capture second\n'),
            ('ordered-mixed-success', ['mixed-value'], b'before\n10\n', b''),
            ('first-closed-total-expression', ['value'], b'before\n7\n', b''),
        ]),
    'lazy-accumulator': (
        'counter limit i total = if eqInt i limit then total '
        'else counter limit (addInt i 1) (addInt total 1)\n'
        'main = ioBind (getArg 0) (\\limit -> printInt (counter (readInt limit) 0 0))\n', [
            ('bounded-lazy-accumulator', ['1000'], b'1000\n', b''),
        ]),
    'seq-accumulator': (
        'counter limit i total = if eqInt i limit then total '
        'else let next = addInt total 1 in seq next (counter limit (addInt i 1) next)\n'
        'main = ioBind (getArg 0) (\\limit -> printInt (counter (readInt limit) 0 0))\n', [
            ('bounded-seq-accumulator', ['1000'], b'1000\n', b''),
        ]),
    'worker-prefix': ((ROOT / 'tools/shared/fixtures/native/WorkerPrefix.emlf').read_text(), [
        ('complete-callee-deep-head', ['join'], b'before\n', b'Runtime: head first\n'),
        ('complete-callee-partial-argument', ['division'], b'before\n', b'Runtime: integer division by zero\n'),
        ('complete-callee-ignored-argument', ['constant-panic'], b'before\n', b'Runtime: later required\n'),
        ('complete-callee-value', ['constant-value'], b'before\n7\n', b''),
        ('partial-application-unused-capture', ['partial-unused'], b'before\n', b'Runtime: suffix required\n'),
        ('partial-application-used-capture', ['partial-used'], b'before\n', b'Runtime: capture first\n'),
    ]),
    'known-let-loop': (
        'scan limit i state = if ltInt i limit then '
        'let cap = addInt state 1 in seq cap '
        '(let raw = mulInt (addInt i 1) 2 in '
        'let next = if ltInt cap raw then cap else raw in '
        'if eqInt next 0 then 1 else scan limit (addInt i 1) (subInt next 1)) else -1\n'
        'main = ioBind (getArg 0) (\\limit -> ioBind (getArg 1) (\\state -> '
        'printInt (scan (readInt limit) 0 (readInt state))))\n', [
            ('known-binding-next-demand', ['1000', '3'], b'-1\n', b''),
        ]),
    'forced-let-loop': (
        'scan label i state = if eqInt i 0 then 0 else '
        'let cap = addInt state 1 in seq (stringLength label) (seq cap '
        '(let raw = mulInt cap 2 in let next = addInt cap raw in '
        'seq next (scan label (subInt i 1) next)))\n'
        'main = ioBind (getArg 0) (\\label -> ioBind (getArg 1) (\\limit -> '
        'printInt (scan label (readInt limit) 3)))\n', [
            ('dominated-force-next-demand', ['abc', '20'], b'0\n', b''),
        ]),
    'known-let-barriers': (
        'partial first = seq first (let later = panic "later" in addInt (quotInt first 0) later)\n'
        'index text = seq text (let later = panic "later" in addInt (stringCodeAt text (-1)) later)\n'
        'conditional value = seq value (let later = panic "later" in if eqInt value 0 then later else 7)\n'
        'sibling flag = let first = panic "first" in '
        'seq (if eqString flag "take" then first else 0) '
        '(let later = panic "later" in addInt first later)\n'
        'run mode = if eqString mode "partial" then partial 5 '
        'else if eqString mode "index" then index "abc" '
        'else if eqString mode "conditional-unused" then conditional 1 '
        'else if eqString mode "conditional-used" then conditional 0 else sibling mode\n'
        'main = ioBind (getArg 0) (\\mode -> '
        'ioBind (putStrLn "before") (\\ignored -> printInt (run mode)))\n', [
            ('known-first-partial-barrier', ['partial'], b'before\n', b'Runtime: integer division by zero\n'),
            ('known-first-index-barrier', ['index'], b'before\n', b'Runtime: string index out of bounds\n'),
            ('known-first-condition-unused', ['conditional-unused'], b'before\n7\n', b''),
            ('known-first-condition-used', ['conditional-used'], b'before\n', b'Runtime: later\n'),
            ('known-first-sibling-not-dominating', ['skip'], b'before\n', b'Runtime: first\n'),
            ('known-first-taken-sibling', ['take'], b'before\n', b'Runtime: first\n'),
        ]),
    'overflow-values': (
        'main = ioBind (getArg 0) (\\text -> let value = readInt text in '
        'seq value (ioBind (printInt (addInt value 1)) (\\ignored -> '
        'ioBind (printInt (subInt value 1)) (\\ignored2 -> printInt (mulInt value 3)))))\n', [
            ('positive-boundary', ['4611686018427387903'],
             b'4611686018427387904\n4611686018427387902\n13835058055282163709\n', b''),
            ('negative-boundary', ['-4611686018427387904'],
             b'-4611686018427387903\n-4611686018427387905\n-13835058055282163712\n', b''),
        ]),
}


def loop_allocations(llvm):
    workers = []
    for match in re.finditer(r'^define private ptr @(mlf\.worker\.\d+)\(([^\n]*)\)(?: noinline)? \{\n(.*?)^\}',
                             llvm, re.M | re.S):
        if match[2].count('ptr ') == 3 and '@' + match[1] + '(' in match[3]:
            workers.append((match[1], match[3]))
    require(len(workers) == 1, 'scalar-loop control did not emit exactly one recursive worker')
    name, body = workers[0]
    return {'worker': name, 'thunk_allocations': len(re.findall(r'call ptr @mlf\.(?:allocate\.thunk|thunk_new)\(', body))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--reference')
    parser.add_argument('--context-reference', help='compiler before context-aware let scheduling')
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--gc-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and not ROOT.is_relative_to(output), 'output cannot contain checkout')
    output.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'status': 'running', 'complete': False,
              'scope': 'ready-total-and-first-demand-native-controls', 'performance_assertions': False,
              'full_corpus_qualification': False, 'compiler_source_provenance_authenticated': False,
              'native_toolchain_closure_complete': False,
              'native_provenance_scope': 'selected compiler/Clang, source/header closure, static BDWGC and GMP pkg-config flags; system libraries are not fully pinned',
              'commands': [], 'inputs': {}, 'artifacts': {},
              'interpreted_cases': [], 'cases': []}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    save()
    try:
        compiler, clang, pkg = resolve_tool(args.compiler), resolve_tool(args.clang), resolve_tool('pkg-config')
        reference = resolve_tool(args.reference) if args.reference else None
        context_reference = resolve_tool(args.context_reference) if args.context_reference else None
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        sources = local_c_closure((ROOT / 'runtime/mlf_runtime.c').resolve())
        inputs = [compiler, clang, pkg, archive, *sources, *sorted((gc / 'include').rglob('*.h')),
                  Path(__file__).resolve(), ROOT / 'tools/shared/test_direct.py',
                  ROOT / 'tools/shared/test_native_string_index.py',
                  ROOT / 'tools/shared/fixtures/native/WorkerPrefix.emlf', Path(sys.executable).resolve()]
        if reference:
            inputs.append(reference)
        if context_reference:
            inputs.append(context_reference)
        record['inputs'] = {str(path): sha(path) for path in inputs}
        record['compiler_identity'] = runner.run('compiler-identity', [compiler, '--implementation-identity'], timeout=30).stdout.decode().strip()
        cflags = shlex.split(runner.run('gmp-cflags', [pkg, '--cflags', 'gmp'], timeout=30).stdout.decode())
        libraries = shlex.split(runner.run('gmp-libs', [pkg, '--libs', 'gmp'], timeout=30).stdout.decode())
        record['gmp_flags'] = {'cflags': cflags, 'libraries': libraries}
        source_dir = output / 'sources'
        source_dir.mkdir()
        for path in sources:
            target = source_dir / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            record['artifacts'][str(target)] = sha(target)
        programs = {}
        for label, (source, _) in FIXTURES.items():
            fixture = output / (label + '.emlf')
            fixture.write_text(source)
            record['artifacts'][str(fixture)] = sha(fixture)
            result = runner.run('emit-' + label, [compiler, '--no-prelude', '--emit-llvm-gc', fixture], timeout=180)
            llvm = output / (label + '.ll')
            llvm.write_bytes(result.stdout)
            record['artifacts'][str(llvm)] = sha(llvm)
            programs[label] = llvm
        shape = loop_allocations(programs['scalar-loop'].read_text())
        require(shape['thunk_allocations'] == 0, 'ready arithmetic still allocates a recursive thunk')
        record['candidate_shape'] = shape
        conditional_shape = loop_allocations(programs['conditional-loop'].read_text())
        require(conditional_shape['thunk_allocations'] == 0,
                'ready conditional still allocates a recursive thunk')
        record['conditional_shape'] = conditional_shape
        multiplication_shape = loop_allocations(programs['excluded-multiplication'].read_text())
        require(multiplication_shape['thunk_allocations'] > 0,
                'multiplication with ready operands lost its lazy suspension')
        record['excluded_multiplication_shape'] = multiplication_shape
        record['accumulator_shapes'] = {
            label: loop_allocations(programs[label].read_text())
            for label in ['lazy-accumulator', 'seq-accumulator']}
        require(record['accumulator_shapes']['seq-accumulator']['thunk_allocations'] == 0,
                'explicitly forced accumulator gained a recursive thunk')
        record['context_shapes'] = {
            label: loop_allocations(programs[label].read_text())
            for label in ['known-let-loop', 'forced-let-loop']}
        require(record['context_shapes']['known-let-loop']['thunk_allocations'] == 0,
                'known binding did not expose the next let demand')
        require(record['context_shapes']['forced-let-loop']['thunk_allocations'] == 1,
                'dominating force did not expose the next let demand')
        if context_reference:
            record['context_reference_shapes'] = {}
            for label in ['known-let-loop', 'forced-let-loop']:
                result = runner.run('context-reference-' + label,
                                    [context_reference, '--no-prelude', '--emit-llvm-gc', output / (label + '.emlf')], timeout=180)
                old_shape = loop_allocations(result.stdout.decode())
                record['context_reference_shapes'][label] = old_shape
                require(old_shape['thunk_allocations'] > record['context_shapes'][label]['thunk_allocations'],
                        'known-let context reference allocation control is vacuous: ' + label)
        if reference:
            result = runner.run('reference-scalar-loop', [reference, '--no-prelude', '--emit-llvm-gc', output / 'scalar-loop.emlf'], timeout=180)
            record['reference_shape'] = loop_allocations(result.stdout.decode())
            require(record['reference_shape']['thunk_allocations'] > 0, 'reference allocation control is vacuous')
            result = runner.run('reference-conditional-loop', [reference, '--no-prelude', '--emit-llvm-gc', output / 'conditional-loop.emlf'], timeout=180)
            record['reference_conditional_shape'] = loop_allocations(result.stdout.decode())
            require(record['reference_conditional_shape']['thunk_allocations'] > 0,
                    'reference conditional allocation control is vacuous')
            record['reference_accumulator_shapes'] = {}
            for label in ['lazy-accumulator', 'seq-accumulator']:
                result = runner.run('reference-' + label, [reference, '--no-prelude', '--emit-llvm-gc',
                                    output / (label + '.emlf')], timeout=180)
                record['reference_accumulator_shapes'][label] = loop_allocations(result.stdout.decode())
        for label, (_, cases) in FIXTURES.items():
            for name, arguments, expected, diagnostic in cases:
                result = runner.run('interpret-' + name, [compiler, '--no-prelude', '--run',
                                    output / (label + '.emlf'), '--', *arguments],
                                    expected=expected, status=1 if diagnostic else 0, timeout=180)
                require(result.stderr == diagnostic, 'interpreter diagnostic differs: ' + name)
                record['interpreted_cases'].append({'case': label + '/' + name, 'passed': True})
        for optimization in ['0', '2']:
            runtime = output / ('runtime-O' + optimization + '.o')
            runner.run('runtime-O' + optimization, [clang, '-O' + optimization, '-std=c11',
                       '-I' + str(gc / 'include'), *cflags, '-c', source_dir / 'runtime/mlf_runtime.c', '-o', runtime], timeout=120)
            record['artifacts'][str(runtime)] = sha(runtime)
            for label, (_, cases) in FIXTURES.items():
                binary = output / (label + '-O' + optimization)
                runner.run('link-' + label + '-O' + optimization, [clang, '-O' + optimization,
                           '-Wno-override-module', programs[label], runtime, archive, *libraries, '-lm', '-lpthread', '-ldl', '-o', binary], timeout=120)
                record['artifacts'][str(binary)] = sha(binary)
                for name, arguments, expected, diagnostic in cases:
                    result = runner.run('run-' + name + '-O' + optimization, [binary, *arguments],
                                        expected=expected, status=1 if diagnostic else 0, timeout=30)
                    require(result.stderr == diagnostic, 'diagnostic differs: ' + name)
                    record['cases'].append({'case': label + '/' + name + '/O' + optimization, 'passed': True})
        require(len(record['cases']) == 152 and len(record['interpreted_cases']) == 76,
                'execution case inventory differs')
        record.update(status='passed', complete=True)
    except BaseException as error:
        record.update(status='failed', complete=False, error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        for path, digest in {**record['inputs'], **record['artifacts']}.items():
            require(sha(path) == digest, 'input/artifact changed: ' + path)
        record['immutable_inputs_verified_after'] = True
        save()
    print(str(output / 'receipt.json') + ': passed (152 native controls, O0/O2)')


if __name__ == '__main__':
    main()
