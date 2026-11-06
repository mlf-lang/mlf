"""Exact source-identity admission; Oracle.hs owns independent semantics."""
import hashlib
from pathlib import Path

OWNER = 'host/ghc/MLF/Host/Base.hs'
OLD_SHA = 'b9663c40059791bfb99e9f302d4eab94452379653db3e951ee02c8ff45933de3'
NEW_SHA = 'eac4d08662fcadeb78678e3cb0fb4efdbdd9698e78baa0d39e79cea89b566d5e'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def restore_previous(raw):
    require(sha(raw) == NEW_SHA, 'exact reviewed small-Integer comparison source')
    extensions = b'ConstraintKinds, MagicHash #-}'
    imports = b'import GHC.Exts (isTrue#, (<#))\nimport GHC.Num.Integer (Integer(IS))\n'
    start = b"-- Keep the language's ordered demand, then expose the common small-Integer\n"
    end = b'{-# NOINLINE integerLtFallback #-}\n'
    require(raw.count(extensions) == raw.count(imports) == raw.count(start) == raw.count(end) == 1,
            'one exact comparison replacement and import extension')
    left = raw.index(start); right = raw.index(end, left) + len(end)
    previous = (raw[:left] + b'v_ltInt = strict2 (<)\n' + raw[right:])
    previous = previous.replace(extensions, b'ConstraintKinds #-}').replace(imports, b'')
    require(sha(previous) == OLD_SHA, 'complete unchanged pre-comparison host recovered')
    return previous


def historical(raw):
    return raw if sha(raw) == OLD_SHA else restore_previous(raw)


def candidate_dependencies(expected, source):
    require(expected[OWNER] == OLD_SHA, 'exact prior C4 host dependency')
    raw = (Path(source) / OWNER).read_bytes()
    historical(raw)
    return {**expected, OWNER: sha(raw)}
