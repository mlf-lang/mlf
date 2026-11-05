"""One reversible, pinned prepared-public comparator adaptation; no source IO."""
import hashlib

FROZEN_SESSION_SHA256 = '718a05cacb3d52760058a1f57901e9fc37135b7098bd2bd9240428eded06c16f'
FROZEN_ORACLE_SHA256 = 'bf5000014cc1aa4d97a98ee1380a9307796182dc1cfd433522308521b1a1cd8c'
OLD_IMPORT = b'import SessionOracle\n'
NEW_IMPORT = OLD_IMPORT + b'import qualified CurrentC4TransactionOracle as C4\n'
OLD_CALL = b' checkOutcome(label++"/unchanged public route")True expected(C.solvePrepared input)\n'
NEW_CALL = b' C4.checkTransactionalOutcome(label++"/unchanged public route") expected(C.solvePrepared input)\n'
OLD_ORACLE_HEADER = b'module C4TransactionOracle where\n'
NEW_ORACLE_HEADER = b'module CurrentC4TransactionOracle where\n'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def restore_session(adapted):
    require(adapted.count(NEW_IMPORT) == 1 and adapted.count(NEW_CALL) == 1 and
            OLD_CALL not in adapted, 'exact single C4 import/call adaptation required')
    restored = adapted.replace(NEW_IMPORT, OLD_IMPORT).replace(NEW_CALL, OLD_CALL)
    require(digest(restored) == FROZEN_SESSION_SHA256,
            'session adaptation changed another byte of the frozen controls')
    return restored


def adapt_session(original):
    require(digest(original) == FROZEN_SESSION_SHA256, 'exact frozen SessionTests required')
    require(original.count(OLD_IMPORT) == 1 and original.count(OLD_CALL) == 1 and
            NEW_IMPORT not in original and NEW_CALL not in original,
            'unique original prepared-public comparison required')
    adapted = original.replace(OLD_IMPORT, NEW_IMPORT).replace(OLD_CALL, NEW_CALL)
    require(restore_session(adapted) == original, 'byte-exact session inverse required')
    return adapted


def verify_transaction_oracle(adapted):
    require(adapted.count(NEW_ORACLE_HEADER) == 1 and OLD_ORACLE_HEADER not in adapted,
            'one renamed transaction oracle module required')
    original = adapted.replace(NEW_ORACLE_HEADER, OLD_ORACLE_HEADER)
    require(digest(original) == FROZEN_ORACLE_SHA256,
            'complete independent C4 comparator differs beyond module rename')
    return original
