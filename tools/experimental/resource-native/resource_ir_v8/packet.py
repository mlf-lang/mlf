"""Opt-in fresh-raw IR8 packet source, never compiled/runtime admission.

No existing package export or default path imports this additive endpoint.
Each public call invokes the unchanged Stage03 checker anew, including all lower
resource checks. An old result, cached metadata or producer table is never input.
"""
from __future__ import annotations

from dataclasses import dataclass

from .metadata import check_metadata, loads_metadata
from .packet_budget import PacketError, Budget, decode_fresh, encode, fail, same
from .packet_emit import derive_specification, render_source, verify_lossless
from .packet_schema import TABLES, SCHEMA_SHA256, LIMITS

__all__ = ('PacketEmission','PacketError','emit_packet','loads_packet')


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class PacketEmission:
    format: str
    canonical_ir_json: str
    metadata_json: str
    bindings: tuple
    supplement_json: str
    supplement_sha256: str
    packet_header: str
    packet_source: str
    manifest_json: str
    manifest_sha256: str
    statistics: tuple

    def __repr__(self):
        return ('PacketEmission(emitted-uncompiled-packet-only, '
                f'metadata_sha256={self.bindings[4]!r}, manifest_sha256={self.manifest_sha256!r})')


def _owned(closure,budget):
    # This private helper is called only immediately after a fresh public checker.
    # Its caller never accepts a closure or metadata artifact from the user.
    raw=decode_fresh(closure.canonical_json,budget)
    metadata=decode_fresh(closure.metadata_json,budget)
    # Binding tuple (6), fixed comparison dictionary (5), return tuple (4).
    budget.reserve(creation=15,work=10)
    bindings=(metadata['core_sha256'],closure.ir_sha256,closure.declaration_sha256,
              closure.resource_sha256,closure.metadata_sha256)
    if (metadata['ir_sha256']!=bindings[1] or metadata['declaration_sha256']!=bindings[2]
            or metadata['resource_sha256']!=bindings[3]
            or metadata['native_status']!={'state':'abi-unbound','typed_static_bytes':None,
                                         'graph_executed':False,'source_admitted':False}):
        fail('packet.bindings','packet-mapping','EQUATION','fresh checker bindings/status differ')
    return raw,metadata,bindings


def _manifest(spec,metadata,bindings,supplement_hash,outputs,budget):
    b=budget
    b.reserve(creation=30,work=26)
    binding_names=('core','raw','declaration','resource','metadata')
    bound={name:bindings[index] for index,name in enumerate(binding_names)}
    counts={name:len(metadata[name]) for name,_,_ in TABLES}
    entries=b.listing()
    # Preserve Stage03 inventory ID order, not physical directory order.
    b.reserve(creation=1+len(spec['objects']),work=len(spec['objects']))
    source={obj['source_id']:obj for obj in spec['objects'] if obj['source_id'] is not None}
    for index in range(len(source)):
        b.reserve(creation=18,work=1)
        obj=source[index]
        b.append(entries,b.row(source_id=index,key=obj['key'],kind=obj['source_kind'],count=obj['count'],
            source_element_kind=obj['source_element_kind'],packet_element_type=obj['element'],
            directory_id=obj['directory_id'],mapping_class=obj['mapping_class']))
    member_count=0
    for obj in spec['objects']:
        b.work(); member_count+=int(obj['count']>0)
    b.reserve(creation=60,work=1)
    output_records=b.row(packet_header=b.row(bytes=outputs[4],sha256=outputs[2]),
                         packet_source=b.row(bytes=outputs[5],sha256=outputs[3]))
    sidecars=b.row(metadata_sha256=bindings[4],resource_sha256=bindings[3],supplement_sha256=supplement_hash)
    status=b.row(state='uncompiled-packet-only',packet_bytes=None,runtime_total_static_bytes=None,
                 graph_executed=False,source_admitted=False,runtime_guards_executed=False)
    return b.row(format='resource-ir-v8-c-packet-emission-manifest/1',schema_sha256=SCHEMA_SHA256,
        bindings=bound,supplement_sha256=supplement_hash,table_counts=counts,
        resolution_access_transport_rows=spec['resolution_access_transport_rows'],
        source_inventory_entries=entries,packet_directory_count=len(spec['objects']),
        packet_member_count=member_count,host_sidecars=sidecars,outputs=output_records,native_status=status)


def _emit_fresh(closure):
    b=Budget()
    raw,metadata,bindings=_owned(closure,b)
    spec=derive_specification(raw,metadata,bindings,b)
    verify_lossless(metadata,spec,b)
    supplement,supplement_hash,_=encode(spec['supplement'],b,'supplement',LIMITS['supplement_bytes'])
    outputs=render_source(spec,b)
    manifest=_manifest(spec,metadata,bindings,supplement_hash,outputs,b)
    manifest_json,manifest_hash,_=encode(manifest,b,'manifest',LIMITS['manifest_bytes'])
    statistics=b.finalize()
    return PacketEmission('resource-ir-v8-c-packet-source/1',closure.canonical_json,
        closure.metadata_json,bindings,supplement,supplement_hash,outputs[0],outputs[1],
        manifest_json,manifest_hash,statistics)


def emit_packet(raw):
    return _emit_fresh(check_metadata(raw))


def loads_packet(text):
    return _emit_fresh(loads_metadata(text))


def _fresh_specification(raw):
    """Private mutation-test snapshot, not an emission/admission result.

    Shape: exact format, bindings, supplement, objects, and R. Object rows are
    numeric native-field dictionaries (pool rows are byte integers). The fixed
    compiler-derived ProgramHeader/TypedHeader/directory rows are empty here;
    their exact counts and associations are retained and template-generated.
    """
    b=Budget()
    owned,metadata,bindings=_owned(check_metadata(raw),b)
    spec=derive_specification(owned,metadata,bindings,b)
    verify_lossless(metadata,spec,b)
    return spec


def _verify_packet(raw,candidate):
    """Fresh raw rechecking and type-exact mutation rejection; returns None."""
    b=Budget()
    owned,metadata,bindings=_owned(check_metadata(raw),b)
    expected=derive_specification(owned,metadata,bindings,b)
    verify_lossless(metadata,expected,b)
    same(candidate,expected,'packet.specification',b)
    return None
