"""Public non-executable IR8 host resource-checking API.

No run/generate/data adapter, runtime import, native eligibility or source claim.
Future consumers must recheck raw snapshots and establish all later gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .program_schema import ResourceError, DECLARATION_KEYS, snapshot, parse, preflight
from .declaration_adapter import check_type_ids
from .budgets import Budget, canonical_encode
from .body_checker import BodyChecker
from .provenance import FORMAT, COUNTS, RULES, PENDING_GATES


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ResourceCheck:
    canonical_json: str
    sha256: str
    declaration_sha256: str
    derived_json: str
    derived_sha256: str
    counts: tuple
    _report: tuple

    def report(self):
        return self._report

    def __repr__(self):
        return f'ResourceCheck(checked-resources-only, sha256={self.sha256!r})'


def _keyed(budget, entries):
    # One keyed-record row and one tuple member per (fixed-arity) key/value row.
    budget.charge(1 + 2 * len(entries))
    return tuple(entries)


def _final_report(budget, analysis, ir_hash, declaration_hash, derived_hash, counts):
    statuses = []
    for index, rule in enumerate(RULES):
        occurrences = 0
        for obligation in analysis.obligations:
            if rule in obligation['rules']:
                occurrences += 1
        classification = 'static' if index < 7 else 'runtime'
        status = 'not-present' if not occurrences else 'checked-symbolically' if index < 7 else 'pending-runtime'
        row = _keyed(budget, (('rule', rule), ('class', classification),
                              ('occurrences', occurrences), ('status', status)))
        budget.append(statuses, row)
    frozen_statuses = budget.tuple(statuses)
    # PENDING_GATES is a fixed immutable module constant, reused without copy.
    return _keyed(budget, (
        ('status', 'checked-resources-only'),
        ('scope', 'Host-only all-body type/resource analysis; no executable IR8 route.'),
        ('format', FORMAT), ('sha256', ir_hash), ('declaration_sha256', declaration_hash),
        ('derived_sha256', derived_hash), ('counts', counts), ('rule_status', frozen_statuses),
        ('pending_gates', PENDING_GATES)))


def check_resources(data):
    owned, canonical = snapshot(data)
    # This extraction belongs to the adopted declaration ingress, not analysis.
    six_maps = {key: owned[key] for key in DECLARATION_KEYS}
    declarations = check_type_ids(six_maps)
    budget = Budget()
    preflight(owned, budget)
    analysis = BodyChecker(owned, declarations, budget).check()
    ir_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    derived = analysis.final_data(ir_hash, declarations.sha256)
    derived_json, derived_hash = canonical_encode(derived)
    count_entries = []
    for key in COUNTS:
        budget.charge()  # keyed fixed-arity record
        budget.append(count_entries, (key, analysis.counts[key]))
    budget.charge()  # counts keyed-record header
    counts = budget.tuple(count_entries)
    report = _final_report(budget, analysis, ir_hash, declarations.sha256, derived_hash, counts)
    budget.charge()  # final immutable ResourceCheck row, after complete report
    return ResourceCheck(canonical, ir_hash, declarations.sha256, derived_json, derived_hash, counts, report)


def loads_resources(text):
    return check_resources(parse(text))
