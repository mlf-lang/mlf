"""Bounded, host-only IR8 static metadata closure.

Only raw plain JSON enters check_metadata/loads_metadata. The fresh resource
checker is mandatory on every call; no checked object or producer table can
waive it. A MetadataClosure is not an execution or source-admission capability.
"""
from __future__ import annotations

from dataclasses import dataclass

from .checker import check_resources as _check_resources
from .program_schema import parse as _parse
from .metadata_budget import (MetadataError, Budget as _Budget, fail as _fail,
                              canonical_encode as _encode, census_records as _census,
                              decode_fresh as _decode_fresh)
from .metadata_types import build_types as _build_types, verify_types as _verify_types
from .metadata_representations import build_representations as _build_representations
from .metadata_edges import build_edges as _build_edges, GUARDS as _GUARDS

__all__ = ('MetadataClosure', 'MetadataError', 'check_metadata', 'loads_metadata')
CORE_SHA256 = '0c54e24fe48deda73547e0dd3a7e9eb285ba0b36d5d938ee8c35a312d509ee83'
FORMAT = 'resource-ir-v8-static-metadata/1'
NATIVE_TABLES = ('types', 'callable_contracts', 'schemes', 'environments', 'codes',
    'code_executions', 'shapes', 'shape_typing', 'representations', 'nominal_fields',
    'families', 'type_resolutions', 'representation_resolutions', 'sites',
    'site_executions', 'slots', 'accesses', 'introductions', 'uses', 'transports')
ELEMENT_KINDS = ('meta.Type', 'meta.CallableContract', 'meta.Scheme', 'meta.Env',
    'meta.CodeTyping', 'meta.CodeExecution', 'meta.ShapeBinding', 'meta.ShapeTyping',
    'meta.Representation', 'meta.NominalField', 'meta.FamilyTyping', 'meta.TypeResolution',
    'meta.RepresentationResolution', 'meta.Site', 'meta.SiteExecution', 'meta.Slot',
    'meta.Access', 'meta.Intro', 'meta.Use', 'meta.Transport')
COUNT_KEYS = NATIVE_TABLES + ('boundaries', 'coverage', 'storage_entries', 'storage_objects',
                             'access_transport_resolution_rows', 'metadata_records')
TOP_KEYS = ('format', 'core_sha256', 'ir_sha256', 'declaration_sha256', 'resource_sha256',
    'type_remap', 'environment_remap', 'types', 'callable_contracts', 'schemes', 'environments',
    'codes', 'code_executions', 'shapes', 'shape_typing', 'representations', 'nominal_fields',
    'families', 'type_resolutions', 'representation_resolutions', 'sites', 'site_executions',
    'slots', 'accesses', 'introductions', 'uses', 'transports', 'boundaries', 'coverage',
    'storage_inventory', 'counts', 'native_status')
PENDING_GATES = ('native-ABI-and-sizeof', 'emitter-storage-correspondence',
    'dynamic-origin-representation-and-edges', 'model-native-and-lifecycle',
    'source-proof-and-lowering', 'single-code-emission', 'GC-replacement', 'performance')
_REPORT_KEYED_SIZES = (26, 8, 7, 3, 4, 12)


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class MetadataClosure:
    canonical_json: str
    ir_sha256: str
    declaration_sha256: str
    resource_sha256: str
    metadata_json: str
    metadata_sha256: str
    counts: tuple
    _report: tuple

    def report(self):
        return self._report

    def __repr__(self):
        return ('MetadataClosure(checked-static-metadata-only, '
                f'ir_sha256={self.ir_sha256!r}, metadata_sha256={self.metadata_sha256!r})')


def _inventory(data, budget):
    """Enumerate every prospective storage object, without inventing sizeof."""
    budget.creation()
    rows = []

    def entry(kind, key, count, element):
        budget.work()
        if type(count) is not int or count < 0:
            _fail('metadata.storage_inventory', 'metadata-closure', 'STORAGE_INVENTORY', 'invalid prospective element count')
        budget.record_append(rows, kind=kind, key=key, count=count,
                             element_kind=element, emission_status='planned-unbound')

    for table, element in zip(NATIVE_TABLES, ELEMENT_KINDS):
        budget.work()
        entry('table', 'table/' + table, len(data[table]), element)
        entry('index', 'index/table/' + table, len(data[table]), 'meta.RegisteredRowRef')
    variants = captures = 0
    for family in data['families']:
        budget.work(); variants += len(family['variants'])
    for code in data['codes']:
        budget.work(); captures += len(code['captures'])
    budget.creation(1 + 2 * 6)  # descriptor-spec vector plus six fixed records
    descriptors = (('shapes', len(data['shapes']), 'physical.RtShape'),
        ('codes', len(data['codes']), 'physical.RtCode'),
        ('families', len(data['families']), 'physical.RtFamily'),
        ('variants', variants, 'physical.RtVariant'),
        ('nominal-fields', len(data['nominal_fields']), 'physical.RtField'),
        ('code-capture-fields', captures, 'physical.RtField'))
    for suffix, count, element in descriptors:
        entry('descriptor', 'descriptor/' + suffix, count, element)
        entry('index', 'index/descriptor/' + suffix, count, 'meta.RegisteredDescriptorRef')
    for env in data['environments']:
        entry('vector', 'vector/env/' + str(env['id']), len(env['arguments']), 'ref.Type')
    for code in data['codes']:
        entry('vector', 'vector/code-captures/' + str(code['id']), len(code['captures']), 'meta.CaptureTyping')
    for execution in data['code_executions']:
        entry('vector', 'vector/execution-captures/' + str(execution['id']), len(execution['captures']), 'meta.ResolvedCapture')
    for intro in data['introductions']:
        entry('vector', 'vector/intro-sites/' + str(intro['id']), len(intro['result_sites']), 'ref.Site')
    for use in data['uses']:
        entry('vector', 'vector/use-occurrences/' + str(use['id']), len(use['occurrences']), 'ref.PathString')
    for family in data['families']:
        fid = str(family['id'])
        entry('vector', 'vector/family-variants/' + fid, len(family['variants']), 'meta.VariantTyping')
        entry('vector', 'vector/family-variant-pointers/' + fid, len(family['variants']), 'physical.RtVariantRef')
        for variant in family['variants']:
            entry('vector', 'vector/variant-fields/' + fid + '/' + str(variant['index']), len(variant['fields']), 'ref.NominalField')
    for shape in data['shapes']:
        budget.work()
        if shape['kind'] == 'DATA':
            count = 0
            for field in data['nominal_fields']:
                budget.work()
                if field['shape'] == shape['id']:
                    count += 1
            entry('vector', 'vector/data-fields/' + str(shape['id']), count, 'ref.NominalField')
    budget.creation()
    strings = set()

    def string(value):
        budget.work(); budget.add(strings, value)

    def path(value):
        encoded, _, _ = _encode(value, budget)
        string(encoded)

    for scheme in data['schemes']:
        string(scheme['name'])
    for code in data['codes']:
        string(code['name']); path(code['body_path'])
        for capture in code['captures']:
            string(capture['name'])
    for use in data['uses']:
        string(use['name'])
        for occurrence in use['occurrences']:
            path(occurrence)
    for shape in data['shapes']:
        budget.work()
        if shape['source']['kind'] == 'legacy':
            string(shape['source']['reference'])
    for site in data['sites']:
        path(site['path'])
        if site['legacy_physical'] is not None:
            string(site['legacy_physical'])
    for ty in data['types']:
        budget.work()
        if ty['tag'] == 'closed':
            string(ty['atom'])
    for field in data['nominal_fields']:
        string(field['name'])
    for family in data['families']:
        string(family['name'])
        for variant in family['variants']:
            string(variant['name'])
    for intro in data['introductions']:
        path(intro['generalize_path']); path(intro['seal_path'])
    string_bytes = 0
    for value in budget.ordered(strings):
        string_bytes += 1  # exactly one NUL, including an empty legal string
        for char in value:
            budget.work()
            scalar = ord(char)
            string_bytes += 1 if scalar < 0x80 else 2 if scalar < 0x800 else 3 if scalar < 0x10000 else 4
    entry('string-pool', 'pool/strings', string_bytes, 'byte.UTF8')
    entry('header', 'header/program', 1, 'physical.RtProgram')
    entry('header', 'header/typed', 1, 'meta.TypedHeader')
    entry('header', 'header/bindings', 5, 'byte.Digest32')
    kinds = ('table', 'vector', 'descriptor', 'index', 'string-pool', 'header')
    rows = budget.ordered(rows, key=lambda item: (kinds.index(item['kind']), item['key']), key_units=3)
    budget.creation()
    final = []
    for index, row in enumerate(rows):
        budget.work()
        budget.record_append(final, id=index, **row)
    return final


def _counts(data, budget):
    counts = budget.row()
    for name in NATIVE_TABLES + ('boundaries', 'coverage'):
        budget.work(); budget.put(counts, name, len(data[name]))
    budget.put(counts, 'storage_entries', len(data['storage_inventory']))
    objects = 0
    for row in data['storage_inventory']:
        budget.work(); objects += int(row['count'] > 0)
    budget.put(counts, 'storage_objects', objects)
    total = sum(len(data[name]) for name in ('type_resolutions', 'representation_resolutions', 'accesses', 'transports'))
    budget.work(4)
    budget.put(counts, 'access_transport_resolution_rows', total)
    budget.put(counts, 'metadata_records', 0)
    return counts


def _document(raw, derived, resource, types, budget):
    rep = _build_representations(raw, derived, types, budget)
    edges = _build_edges(rep)
    # Builders above are provisional, creation/work-bounded host structures.
    # Admit the root and each structurally completed subtree before attachment.
    # No attached subtree is structurally mutated afterward.
    budget.records()
    data = budget.row(format=FORMAT, core_sha256=CORE_SHA256,
        ir_sha256=resource.sha256, declaration_sha256=resource.declaration_sha256,
        resource_sha256=resource.derived_sha256)
    budget.creation()  # fixed three-bank iteration record
    for tables in (types.tables, rep.tables, edges.tables):
        for name, value in tables.items():
            budget.work(); budget.put(data, name, budget.retain_json(value))
    native = budget.row(state='abi-unbound', typed_static_bytes=None,
                        graph_executed=False, source_admitted=False)
    budget.put(data, 'native_status', budget.retain_json(native))
    budget.put(data, 'storage_inventory', budget.retain_json(_inventory(data, budget)))
    budget.put(data, 'counts', budget.retain_json(_counts(data, budget)))
    records = _census(data, budget)
    if not budget._verifying and records != budget.retained_records:
        _fail('metadata.records', 'metadata-closure', 'RECORD_CENSUS', 'retained output differs from independent object census')
    # The reviewed fixed scalar replacement changes no object occurrences.
    data['counts']['metadata_records'] = records
    return data


def _same(actual, expected, path, budget, layer, code):
    """Iterative exact JSON-tree equality: bool never aliases an integer ID.

    Table dictionaries are never used as authority. A new independent reference
    walk rechecks all fields, ordering, null domains, and complete row sets.
    """
    budget.creation()
    pending = []
    budget.creation()  # fixed pair record, separate from worklist membership
    budget.append(pending, (actual, expected))
    while pending:
        left, right = pending.pop()
        budget.work()
        if type(left) is not type(right):
            _fail(path, layer, code, 'derived table has a different plain JSON type')
        if type(right) is dict:
            if len(left) != len(right):
                _fail(path, layer, code, 'derived object keys differ')
            for key, value in right.items():
                budget.work()
                if type(key) is not str or key not in left:
                    _fail(path, layer, code, 'derived object key is absent')
                budget.creation()
                budget.append(pending, (left[key], value))
        elif type(right) is list:
            if len(left) != len(right):
                _fail(path, layer, code, 'complete derived row/member inventory differs')
            for index in range(len(right)):
                budget.work(); budget.creation()
                budget.append(pending, (left[index], right[index]))
        elif type(right) in (str, int, bool) or right is None:
            if left != right:
                _fail(path, layer, code, 'derived equation, order, or canonical field differs')
        else:
            _fail(path, 'metadata-schema', 'SCHEMA', 'non-JSON derived value')


def _compare_document(candidate, expected, budget):
    budget.work(len(TOP_KEYS))
    if type(candidate) is not dict or len(candidate) != len(TOP_KEYS) or any(key not in candidate for key in TOP_KEYS):
        _fail('metadata', 'metadata-schema', 'SCHEMA', 'expected exact complete metadata document')
    for name in TOP_KEYS:
        if name in ('boundaries', 'coverage'):
            layer, code = 'metadata-closure', 'COVERAGE'
        elif name == 'storage_inventory':
            layer, code = 'metadata-closure', 'STORAGE_INVENTORY'
        elif name in ('type_remap', 'environment_remap', 'types', 'callable_contracts', 'schemes', 'environments', 'type_resolutions'):
            layer, code = 'metadata-type', 'TYPE_EQUATION'
        elif name in ('codes', 'code_executions', 'sites', 'site_executions', 'introductions', 'uses'):
            layer, code = 'metadata-origin', 'ORIGIN'
        elif name in ('shapes', 'shape_typing', 'representations', 'nominal_fields', 'families', 'representation_resolutions'):
            layer, code = 'metadata-representation', 'REPRESENTATION'
        else:
            layer, code = 'metadata-closure', 'TABLE_EQUATION'
        _same(candidate[name], expected[name], 'metadata.' + name, budget, layer, code)


def _fresh(data, budget):
    # This exact checker owns all lower-stage schema/resource errors. Do not wrap
    # or relabel them. Internally emitted JSON is still a NEW allocation when
    # decoded: the decoder precharges its complete containers/members first.
    resource = _check_resources(data)
    raw = _decode_fresh(resource.canonical_json, budget)
    derived = _decode_fresh(resource.derived_json, budget)
    types = _build_types(raw, derived, budget)
    budget.creation()  # fixed local adaptation result record
    return resource, raw, derived, types


def _verify_derived(raw, candidate):
    """Private mutation-test endpoint; no success object or producer admission.

    Always freshly resource-check raw. Reconstruct every required row exclusively
    from that fresh artifact; candidate rows influence none of the equations.
    This function returns None, never a MetadataClosure or execution authority.
    """
    budget = _Budget()
    resource, owned, derived, types = _fresh(raw, budget)
    _verify_types(owned, derived, types, budget)
    expected = _document(owned, derived, resource, types, budget)
    _compare_document(candidate, expected, budget)
    return None


def _report(data, resource, metadata_hash, size, budget):
    """One fixed, atomically precharged immutable report, never lazy lookup."""
    budget.creation()
    occurrences = []
    for guard in _GUARDS:
        count = 0
        for row in data['boundaries']:
            budget.work(1 + len(row['guards']))
            if guard in row['guards']:
                count += 1
        budget.append(occurrences, count)
    pool_bytes = None
    for row in data['storage_inventory']:
        budget.work()
        if row['key'] == 'pool/strings':
            pool_bytes = row['count']
    # A keyed tuple charges a record header, each fixed key/value tuple, and
    # every tuple membership: 1 + 4*n. The tuple of 27 guard records has its
    # own header and 27 members. counts is retained by the result and reused
    # by report, so no second counts record is allocated.
    keyed_sizes = _REPORT_KEYED_SIZES  # counts, row/native/boundary/stat/report
    creation = sum(1 + 4 * n for n in keyed_sizes) + 27 * (1 + 4 * 3) + 1 + 27 + 2
    # Reserve comparisons/reads for the fixed finalization graph, plus the
    # public result. No calls that charge work occur after this atomic freeze.
    work = sum(keyed_sizes) + 27 * 3 + len(COUNT_KEYS) + 27 + 7
    budget.finalize(creation=creation, work=work)
    counts = tuple((name, data['counts'][name]) for name in COUNT_KEYS)
    row_status = (('classification', 'planned-native-row-cardinality'),
        ('type_resolution', len(data['type_resolutions'])),
        ('representation_resolution', len(data['representation_resolutions'])),
        ('access', len(data['accesses'])), ('transport', len(data['transports'])),
        ('total', data['counts']['access_transport_resolution_rows']), ('limit', 65536), ('status', 'within-limit'))
    native_status = (('classification', 'abi-unbound'), ('limit_bytes', 4194304),
        ('measured_bytes', None), ('planned_storage_entries', data['counts']['storage_entries']),
        ('planned_nonempty_objects', data['counts']['storage_objects']),
        ('string_pool_bytes', pool_bytes), ('actual_emitted_rows_verified', False))
    guards = tuple((('guard', guard), ('occurrences', occurrences[index]),
                    ('status', 'not-present' if occurrences[index] == 0 else 'derived-pending-runtime'))
                   for index, guard in enumerate(_GUARDS))
    boundary_status = (('classification', 'derived-predicates-not-executed'),
                       ('rows', len(data['boundaries'])), ('guards', guards))
    statistics = (('metadata_records', data['counts']['metadata_records']),
                  ('creation_units', budget.creation_units), ('work_units', budget.work_units),
                  ('metadata_utf8_bytes', size))
    report = (('status', 'checked-static-metadata-only'),
        ('scope', 'Host-only bounded static metadata closure from freshly resource-checked IR8; no executable route.'),
        ('ir_sha256', resource.sha256), ('declaration_sha256', resource.declaration_sha256),
        ('resource_sha256', resource.derived_sha256), ('metadata_sha256', metadata_hash),
        ('counts', counts), ('table_row_status', row_status), ('native_static_status', native_status),
        ('boundary_status', boundary_status), ('host_statistics', statistics), ('pending_gates', PENDING_GATES))
    # Fixed checks are in the reserved finalization work; failures never return
    # a success object. No changing statistic is embedded in metadata_json.
    if (len(report) != 12 or len(counts) != len(COUNT_KEYS)
            or statistics[3][1] != size
            or data['counts']['metadata_records'] != budget.metadata_records
            or budget.metadata_records != budget.retained_records
            or pool_bytes is None or row_status[5][1] > 65536
            or row_status[5][1] != budget.row_units
            or budget.metadata_utf8_bytes != size):
        _fail('metadata.report', 'metadata-closure', 'REPORT', 'cached report finalization differs')
    for index, key in enumerate(COUNT_KEYS):
        if counts[index][0] != key or counts[index][1] != data['counts'][key]:
            _fail('metadata.report', 'metadata-closure', 'REPORT', 'cached count differs')
    return counts, report


def check_metadata(data):
    budget = _Budget()
    resource, owned, derived, types = _fresh(data, budget)
    _verify_types(owned, derived, types, budget)
    document = _document(owned, derived, resource, types, budget)
    # Independent equation replay reads fresh raw/lower-stage sources, not the
    # candidate tables. Only prospective semantic-row charges are suppressed;
    # every replay allocation, comparison, dependency, and copy still costs.
    with budget.verification():
        expected = _document(owned, derived, resource, types, budget)
        _compare_document(document, expected, budget)
    metadata_json, metadata_hash, size = _encode(document, budget)
    counts, report = _report(document, resource, metadata_hash, size, budget)
    return MetadataClosure(resource.canonical_json, resource.sha256, resource.declaration_sha256,
                           resource.derived_sha256, metadata_json, metadata_hash, counts, report)


def loads_metadata(text):
    return check_metadata(_parse(text))
