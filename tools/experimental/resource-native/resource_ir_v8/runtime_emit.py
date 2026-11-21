"""Opt-in fresh-raw Stage05 IR8 runtime source artifact, never execution.

All real ctx helpers remain unresolved until an independently reviewed runtime
exists. Neither this module nor its output activates a default execution path.
"""
from __future__ import annotations

from dataclasses import dataclass

from .packet import emit_packet
from .checker import check_resources
from .program_schema import parse
from .runtime_emit_budget import (Budget, LIMITS, RuntimeEmissionError, decode_fresh,
                                  encode, exact, fail, hash_text, same, text_equal)
from .runtime_emit_body import ABI_SHA256, derive_plan, render_sources

__all__ = ('RuntimeEmission', 'RuntimeEmissionError', 'emit_runtime', 'loads_runtime')
PACKET_SCHEMA_SHA256 = 'e4976fb839a8b738c0797100fe7b5d1fc948f2b995ab17f3c44cc8cc4fb94ba6'
CORE_SHA256 = '0c54e24fe48deda73547e0dd3a7e9eb285ba0b36d5d938ee8c35a312d509ee83'
_BINDING_NAMES = ('core', 'raw', 'declaration', 'resource', 'metadata')


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class RuntimeEmission:
    format: str
    canonical_ir_json: str
    packet_manifest_json: str
    metadata_json: str
    runtime_header: str
    runtime_source: str
    packet_header: str
    packet_source: str
    manifest_json: str
    manifest_sha256: str
    statistics: tuple

    def __repr__(self):
        return ('RuntimeEmission(emitted-uncompiled-runtime-source, '
                f'manifest_sha256={self.manifest_sha256!r})')


def _sha(text, b):
    if type(text) is not str or len(text) != 64:
        fail('BINDING', 'expected a lowercase SHA256 digest', schema=True)
    for char in text:
        b.work()
        if char not in '0123456789abcdef':
            fail('BINDING', 'expected a lowercase SHA256 digest', schema=True)


def _owned(packet, b):
    # Only called with this invocation's newly returned public PacketEmission.
    raw = decode_fresh(packet.canonical_ir_json, b)
    metadata = decode_fresh(packet.metadata_json, b)
    packet_manifest = decode_fresh(packet.manifest_json, b)
    if type(packet.bindings) is not tuple or len(packet.bindings) != 5:
        fail('BINDING', 'fresh packet bindings have wrong shape', schema=True)
    for digest in packet.bindings: _sha(digest, b)
    _sha(packet.manifest_sha256, b)
    text_equal(packet.format, 'resource-ir-v8-c-packet-source/1', b)
    text_equal(metadata['format'], 'resource-ir-v8-static-metadata/1', b)
    text_equal(metadata['core_sha256'], CORE_SHA256, b)
    b.creation(6)
    names = ('core_sha256', 'ir_sha256', 'declaration_sha256', 'resource_sha256')
    for index, name in enumerate(names):
        text_equal(b.get(metadata, name, 'BINDING'), packet.bindings[index], b)
    text_equal(hash_text(packet.canonical_ir_json, b)[0], packet.bindings[1], b)
    text_equal(hash_text(packet.metadata_json, b)[0], packet.bindings[4], b)
    text_equal(hash_text(packet.manifest_json, b)[0], packet.manifest_sha256, b)
    b.creation(5)
    same(metadata['native_status'], {'state': 'abi-unbound', 'typed_static_bytes': None,
         'graph_executed': False, 'source_admitted': False}, b)
    text_equal(packet_manifest['schema_sha256'], PACKET_SCHEMA_SHA256, b)
    text_equal(packet_manifest['format'], 'resource-ir-v8-c-packet-emission-manifest/1', b)
    exact(packet_manifest['bindings'], _BINDING_NAMES, b)
    for index, name in enumerate(_BINDING_NAMES):
        text_equal(b.get(packet_manifest['bindings'], name, 'BINDING'), packet.bindings[index], b)
    # Mandatory second public resource admission on owned canonical raw, never
    # on cached metadata, producer rows, hashes, or a previously checked object.
    resource = check_resources(raw)
    text_equal(resource.canonical_json, packet.canonical_ir_json, b)
    text_equal(resource.sha256, packet.bindings[1], b)
    text_equal(resource.declaration_sha256, packet.bindings[2], b)
    text_equal(resource.derived_sha256, packet.bindings[3], b)
    text_equal(hash_text(resource.derived_json, b)[0], packet.bindings[3], b)
    derived = decode_fresh(resource.derived_json, b)
    text_equal(derived['ir_sha256'], packet.bindings[1], b)
    text_equal(derived['declaration_sha256'], packet.bindings[2], b)
    b.creation(10)
    outputs = b.mapping()
    for name, text in (('packet_header', packet.packet_header), ('packet_source', packet.packet_source)):
        digest, size = hash_text(text, b, source=True)
        producer = b.get(packet_manifest['outputs'], name, 'BINDING')
        exact(producer, ('bytes', 'sha256'), b)
        same(producer['bytes'], size, b)
        text_equal(producer['sha256'], digest, b)
        b.scratch(2); b.put(outputs, name, b.row(bytes=size, sha256=digest))
    b.creation(5)
    return raw, metadata, derived, outputs


def _storage(plan, b):
    b.reserve(creation=32, work=1)
    members = b.listing()
    b.append(members, b.row(name='header', c_type='Rt8BindingHeader', count=1))
    b.creation(16)  # outer tuple and three three-member tuple rows
    for name, ctype, count in (('codes', 'Rt8Code', len(plan.code_mapping)),
        ('label_offsets', 'uint32_t', len(plan.label_rows)), ('label_bytes', 'unsigned char', b.label_utf8_bytes)):
        if count:
            b.scratch(3); b.append(members, b.row(name=name, c_type=ctype, count=count))
    packet = b.row(root_type='struct Ir8Packet_generated_v1', root_symbol='ir8_packet_generated_root', bytes=None, alignment=None)
    binding = b.row(root_type='struct Ir8Runtime_generated_v1', root_symbol='ir8_runtime_generated_root', bytes=None, alignment=None, members=members)
    return b.row(packet=packet, binding=binding, total_static_bytes=None,
        total_static_limit=LIMITS['typed_static_bytes'], measurement='sum-complete-aggregate-sizeof',
        wrapper_storage='by-value-nonowning-not-static')


def _manifest(packet, plan, outputs, storage, b):
    # Exact fixed argument records are reserved before constructing any kwargs.
    b.reserve(creation=80, work=1)
    bindings = b.mapping()
    for index, name in enumerate(_BINDING_NAMES): b.put(bindings, name, packet.bindings[index])
    b.put(bindings, 'packet_manifest', packet.manifest_sha256)
    limits = b.mapping()
    for key, value in LIMITS.items(): b.put(limits, key, value)
    b.put(limits, 'lower_public_calls', b.row(emit_packet=1, check_resources_extra=1))
    status = b.row(state='emitted-uncompiled-runtime-source', runtime_total_static_bytes=None,
                   callbacks_executed=False, dynamic_guards_executed=False, source_admitted=False)
    stats = b.row(phase='pre-manifest-serialization', creation_units=0, work_units=0,
                  source_utf8_bytes=0, label_utf8_bytes=0, label_count=0)
    result = b.row(format='resource-ir-v8-runtime-emission-manifest/1', abi_sha256=ABI_SHA256,
        packet_schema_sha256=PACKET_SCHEMA_SHA256, bindings=bindings, outputs=outputs,
        code_mapping=plan.code_mapping, entry_mapping=plan.entry_mapping,
        instruction_mapping=plan.instruction_mapping, introduction_mapping=plan.introductions,
        use_mapping=plan.uses, labels=plan.label_rows, frames=plan.frames,
        storage_plan=storage, limits=limits, statistics=stats, native_status=status)
    # All final retained objects are reserved BEFORE this named finite snapshot.
    b.reserve_result()
    stats['creation_units'], stats['work_units'] = b.creation_units, b.work_units
    stats['source_utf8_bytes'] = b.source_utf8_bytes
    stats['label_utf8_bytes'], stats['label_count'] = b.label_utf8_bytes, b.label_count
    return result


def _emit(packet, b):
    raw, metadata, derived, retained = _owned(packet, b)
    plan = derive_plan(raw, metadata, derived, b)
    storage = _storage(plan, b)
    # _owned charged the reused packet strings before new source construction.
    rendered = render_sources(plan, packet.bindings)
    b.scratch(2); b.put(retained, 'runtime_header', b.row(bytes=rendered[4], sha256=rendered[2]))
    b.scratch(2); b.put(retained, 'runtime_source', b.row(bytes=rendered[5], sha256=rendered[3]))
    manifest = _manifest(packet, plan, retained, storage, b)
    manifest_json, manifest_hash, _ = encode(manifest, b, 'manifest')
    statistics = b.finalize()
    return RuntimeEmission('resource-ir-v8-runtime-source/1', packet.canonical_ir_json,
        packet.manifest_json, packet.metadata_json, rendered[0], rendered[1],
        packet.packet_header, packet.packet_source, manifest_json, manifest_hash, statistics)


def emit_runtime(raw):
    b = Budget()
    return _emit(emit_packet(raw), b)


def loads_runtime(text):
    return emit_runtime(parse(text))
