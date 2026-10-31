"""Pinned, reversible private instrumentation; never overwrite source modules."""
import hashlib
import re

OPTIMIZE_SHA = 'b1a1e81d21a81300e8df8be5c62d21c824496e77c8040e3ca5cc122c4334fee4'
LLVM_SHA = 'a8c0c5b03f85c25b35e64a6753a2df9572a76650a01d987e3cd98959c719cfe5'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Patch:
    def __init__(self, raw, expected):
        require(sha(raw) == expected, 'production source identity changed: review instrumentation')
        self.original = raw.decode()
        self.text = self.original
        self.edits = []

    def change(self, before, after, count=1):
        require(before != after and self.text.count(before) == count, (before, self.text.count(before), count))
        self.text = self.text.replace(before, after)
        self.edits.append({'before': before, 'after': after, 'count': count})

    def block(self, first, following, function):
        start = self.text.index('  ' + first + ' ::')
        end = self.text.index('  ' + following + ' ::', start)
        before = self.text[start:end]
        self.change(before, function(before))

    def finish(self):
        restored = self.text
        for edit in reversed(self.edits):
            require(restored.count(edit['after']) == edit['count'], 'ambiguous reverse transformation')
            restored = restored.replace(edit['after'], edit['before'])
        require(restored == self.original, 'private copy does not reverse exactly')
        return self.text.encode(), self.edits


def optimize(raw):
    p = Patch(raw, OPTIMIZE_SHA)
    p.change('module Bootstrap.LLVM.Optimize where {',
             '{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}\nmodule DiagnosticOptimize where {')
    p.change('  import MLF.Primitive;', '  import MLF.Primitive;\n  import qualified Counters as C;\n  import qualified Prelude as Host;')
    p.change('  -- Fresh copies preserve global binder identity uniqueness when rewriting.', '''  -- Counters execute when the original Fresh state transition is demanded.
  -- Counting the action constructor alone could share a partially applied action.
  traceFresh :: Host.String -> Int -> Fresh a -> Fresh a;
  traceFresh label depth action = Fresh (\\seed -> C.tick label depth (runFresh action seed));
  traceCopy :: Host.String -> Host.String -> Int -> Fresh a -> Fresh a;
  traceCopy origin event depth action = Fresh (\\seed -> C.named origin event depth (runFresh action seed));
  -- Fresh copies preserve global binder identity uniqueness when rewriting.''')

    def copy(block):
        # Keep the original public/private-call signature as a classified root.
        block = block.replace('  copy env expression =\n', '''  copy env expression = copyFrom "copy.other" env expression;
  copyFrom :: Host.String -> Map XName XErased -> XErased -> Fresh XErased;
  copyFrom origin env expression = traceCopy origin "roots" 0 (copyAt origin 0 env expression);
  copyAt :: Host.String -> Int -> Map XName XErased -> XErased -> Fresh XErased;
  copyAt origin depth env expression = traceCopy origin "visits" depth (
''', 1)
        block = block.replace('copy (M.insert', 'copyAt origin (depth + 1) (M.insert')
        block = block.replace('copy env ', 'copyAt origin (depth + 1) env ')
        # The root definition must not acquire recursive depth parameters.
        block = block.replace('  copyAt origin (depth + 1) env expression = copyFrom', '  copy env expression = copyFrom')
        block = block.replace('copy local b', 'copyAt origin (depth + 1) local b')
        block = block.replace('copyRecursive local', 'copyRecursiveAt origin (depth + 1) local')
        block = block.replace('copyAlternative env', 'copyAlternativeAt origin (depth + 1) env')
        block = block.replace('<- freshName;', '<- traceCopy origin "fresh_binder" depth freshName;')
        block = block.replace('\\ignored -> freshName', '\\ignored -> traceCopy origin "fresh_binder" depth freshName')
        # Wrap each existing outer constructor branch, never inspect the input twice.
        branches = [('XEVar n', 'variable_lookup'), ('XEAbs n b', 'rebuild_abs'),
                    ('XEApp f a', 'rebuild_app'), ('XELet n a b', 'rebuild_let'),
                    ('XELetRec ds b', 'rebuild_rec'), ('XECase a branches', 'rebuild_case')]
        for pattern, event in branches:
            anchor = '      ' + pattern + ' ->'
            require(block.count(anchor) == 1, 'required invariant: block.count(anchor) == 1')
            start = block.index(anchor) + len(anchor)
            next_branch = re.search(r'\n      (?:XE|_ ->)', block[start:])
            require(next_branch, 'required invariant: next_branch')
            end = start + next_branch.start()
            body = block[start:end]
            require(body.rstrip().endswith(';'), "required invariant: body.rstrip().endswith(';')")
            stripped = body.rstrip()[:-1]
            block = block[:start] + ' traceCopy origin "' + event + '" depth (' + stripped + ');' + block[end:]
        block = block.replace('      _ -> freshPure expression\n    };',
                              '      _ -> traceCopy origin "reuse_leaf" depth (freshPure expression)\n    });')
        require(block.endswith('    });\n'), "required invariant: block.endswith('    });\\n')")
        return block
    p.block('copy', 'copyRecursive', copy)

    def copy_helpers(block):
        block = block.replace('copyRecursive ::', 'copyRecursiveAt :: Host.String -> Int ->')
        block = block.replace('copyRecursive env', 'copyRecursiveAt origin depth env')
        block = block.replace('copyAlternative ::', 'copyAlternativeAt :: Host.String -> Int ->')
        block = block.replace('copyAlternative env', 'copyAlternativeAt origin depth env')
        block = block.replace('copy env value', 'copyAt origin depth env value')
        block = block.replace('copy (M.union', 'copyAt origin depth (M.union')
        block = block.replace('\\ignored -> freshName', '\\ignored -> traceCopy origin "fresh_pattern_binder" depth freshName')
        block = block.replace('freshPure (XErasedAlternative patternNext result)',
                              'traceCopy origin "rebuild_alternative" depth (freshPure (XErasedAlternative patternNext result))')
        return block
    p.block('copyRecursive', 'renameMaybe', copy_helpers)

    # Every ordinary external callsite has a named origin. Recursion only uses
    # copyAt; an unexpected future root is retained as copy.other and rejected
    # by the runner if actually executed.
    roots = [
        ('copy (M.singleton n (XEVar a)) b', 'identities_alias'),
        ('copy M.empty selected', 'projection'),
        ('copy M.empty value', 'substitute'),
        ('copy (M.singleton r (XEVar name)) (useTerm rhs)', 'recursive_rewrite'),
        ('copy M.empty rhs', 'higher_order_rhs'),
        ('copy M.empty callback', 'higher_order_callback'),
        ('copy M.empty expression', 'initial_uniqueness'),
        ('copy M.empty normalized', 'final_numbering'),
    ]
    for before, origin in roots:
        p.change(before, before.replace('copy ', 'copyFrom "copy.' + origin + '" ', 1))

    def substitute(block):
        block = block.replace('  substituteUsed name value tree =\n', '''  substituteUsed name value tree = traceFresh "substituteUsed.roots" 0 (substituteUsedAt 0 name value tree);
  substituteUsedAt :: Int -> XName -> XErased -> UseTree -> Fresh UseTree;
  substituteUsedAt depth name value tree = traceFresh "substituteUsed.visits" depth (
''')
        block = block.replace('then freshPure tree', 'then traceFresh "substituteUsed.pruned" depth (freshPure tree)', 1)
        block = block.replace('else case useTerm tree of {', 'else traceFresh "substituteUsed.positive" depth (case useTerm tree of {')
        block = block.replace('mapUseChildren (substituteUsed name value) tree',
                              'traceFresh "substituteUsed.rebuild_parent" depth (mapUseChildren (substituteUsedAt (depth + 1) name value) tree)')
        block = block.replace('         };', '         }));')
        return block
    p.block('substituteUsed', 'useApplications', substitute)

    def common(block):
        block = block.replace('  commonCalls target arity outer tree =\n', '''  commonCalls target arity outer tree = C.tick "commonCalls.roots" 0 (commonCallsAt 0 target arity outer tree);
  commonCallsAt :: Int -> XName -> Int -> Map XName Int -> UseTree -> CommonCalls;
  commonCallsAt depth target arity outer tree = C.tick "commonCalls.visits" depth (
''')
        block = block.replace('then NoCommonCalls', 'then C.tick "commonCalls.pruned" depth NoCommonCalls', 1)
        block = block.replace('else case useApplications [] tree of {',
                              'else C.tick "commonCalls.positive" depth (case useApplications [] tree of {')
        block = block.replace('commonChildCalls target arity outer tree', 'commonChildCallsAt depth target arity outer tree')
        block = block.replace('    };\n  commonChildCalls ::', '    }));\n  commonChildCallsAt :: Int ->')
        block = block.replace('let { collect = commonCalls target arity outer;',
                              'let { collect = commonCallsAt (depth + 1) target arity outer;')
        return block
    p.block('commonCalls', 'contractCommonCalls', common)

    # Add root/depth accounting to ordinary one-node traversals. Wrapping the
    # original expression body preserves branch selection and short circuiting.
    def simple(name, following, signature, arguments, recursive):
        def transform(block):
            definition = '  ' + name + ' ' + arguments + ' ='
            require(block.count(definition) == 1, 'required invariant: block.count(definition) == 1')
            prefix, body = block.split(definition, 1)
            trailing = re.search(r'\n  (?:--|data )', body)
            end = body.rindex(';', 0, trailing.start() if trailing else len(body))
            body, suffix = body[:end], body[end + 1:]
            for before, after in recursive:
                require(before in body, 'required invariant: before in body')
                body = body.replace(before, after)
            wrapped = ('traceFresh' if 'Fresh ' in signature else 'C.tick')
            return (prefix + definition + ' ' + wrapped + ' "' + name + '.roots" 0 (' + name + 'At 0 ' + arguments + ');\n' +
                    '  ' + name + 'At :: Int -> ' + signature + ';\n' +
                    '  ' + name + 'At depth ' + arguments + ' = ' + wrapped + ' "' + name + '.visits" depth (' + body + ');' + suffix)
        p.block(name, following, transform)
    simple('identities', 'fixedPoints', 'XErased -> Fresh XErased', 'expression',
           [('children identities expression', 'children (identitiesAt (depth + 1)) expression')])
    simple('indexUses', 'mapUseChildren', 'XErased -> UseTree', 'term',
           [('indexUses ', 'indexUsesAt (depth + 1) ')])
    simple('passUsed', 'passRaw', 'UseTree -> Fresh UseTree', 'tree',
           [('mapUseChildren passUsed tree', 'mapUseChildren (passUsedAt (depth + 1)) tree')])
    simple('passRaw', 'pass', 'XErased -> Fresh UseTree', 'expression',
           [('passRaw ', 'passRawAt (depth + 1) ')])
    simple('contractCommonCalls', 'specializeCommonParameters', 'XName -> UseTree -> Fresh UseTree', 'target tree',
           [('contractCommonCalls target', 'contractCommonCallsAt (depth + 1) target')])
    simple('useApplications', 'useMaybeLet', '[] UseTree -> UseTree -> (,) UseTree ([] UseTree)', 'arguments tree',
           [('useApplications ', 'useApplicationsAt (depth + 1) ')])
    simple('singleUseIOPath', 'singleUseBranchPath', 'XName -> Bool -> UseTree -> Bool', 'name insideIO tree',
           [('singleUseIOPath ', 'singleUseIOPathAt (depth + 1) ')])
    simple('singleUseBranchPath', 'sameCallNames', 'XName -> Bool -> UseTree -> Bool', 'name selected tree',
           [('singleUseBranchPath ', 'singleUseBranchPathAt (depth + 1) ')])
    return p.finish()


def llvm(raw):
    p = Patch(raw, LLVM_SHA)
    p.change('module Bootstrap.LLVM (', 'module DiagnosticLLVM (')
    p.change('import qualified Bootstrap.LLVM.Optimize as Optimize;',
             'import qualified DiagnosticOptimize as Optimize;')
    return p.finish()
