/* Frozen Stage04 packet-only ABI. No runtime objects or callbacks. */
#ifndef IR8_PACKET_H
#define IR8_PACKET_H
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

#define IR8_PACKET_NULL UINT32_MAX
#define IR8_PACKET_MAX_BYTES UINT32_C(4194304)
#define IR8_PACKET_MAX_WORK UINT64_C(67108864)
#define IR8_PACKET_MAX_DIRECTORY UINT32_C(16384)
_Static_assert(CHAR_BIT == 8, "IR8 requires octets");
_Static_assert(sizeof(uint32_t) == 4 && UINT32_MAX == UINT32_C(4294967295), "IR8 requires exact uint32_t");

#define IR8_PACKET_ACCESS_MODE_MONO UINT32_C(1)
#define IR8_PACKET_ACCESS_MODE_SCHEME UINT32_C(2)
#define IR8_PACKET_BODY_BINDING_UNBOUND UINT32_C(1)
#define IR8_PACKET_CODE_KIND_FUNCTION UINT32_C(1)
#define IR8_PACKET_CODE_KIND_THUNK UINT32_C(2)
#define IR8_PACKET_ENV_MODE_CLOSED UINT32_C(3)
#define IR8_PACKET_ENV_MODE_CONCRETE UINT32_C(1)
#define IR8_PACKET_ENV_MODE_NEUTRAL UINT32_C(2)
#define IR8_PACKET_FIELD_OWNER_CODE UINT32_C(3)
#define IR8_PACKET_FIELD_OWNER_DATA UINT32_C(1)
#define IR8_PACKET_FIELD_OWNER_VARIANT UINT32_C(2)
#define IR8_PACKET_HEADER_SUBKIND_BINDINGS UINT32_C(3)
#define IR8_PACKET_HEADER_SUBKIND_PROGRAM UINT32_C(1)
#define IR8_PACKET_HEADER_SUBKIND_TYPED UINT32_C(2)
#define IR8_PACKET_INTRO_CONTAINER_CODE UINT32_C(2)
#define IR8_PACKET_INTRO_CONTAINER_ENTRY UINT32_C(1)
#define IR8_PACKET_NATIVE_DETAIL_ALIGNMENT UINT32_C(10)
#define IR8_PACKET_NATIVE_DETAIL_BINDING_MISMATCH UINT32_C(22)
#define IR8_PACKET_NATIVE_DETAIL_BODY_BINDING UINT32_C(26)
#define IR8_PACKET_NATIVE_DETAIL_COUNT UINT32_C(16)
#define IR8_PACKET_NATIVE_DETAIL_DUPLICATE UINT32_C(14)
#define IR8_PACKET_NATIVE_DETAIL_EQUATION UINT32_C(23)
#define IR8_PACKET_NATIVE_DETAIL_EXTRA UINT32_C(13)
#define IR8_PACKET_NATIVE_DETAIL_INTERNAL_INVARIANT UINT32_C(28)
#define IR8_PACKET_NATIVE_DETAIL_LENGTH UINT32_C(3)
#define IR8_PACKET_NATIVE_DETAIL_LIMIT UINT32_C(7)
#define IR8_PACKET_NATIVE_DETAIL_MAGIC UINT32_C(4)
#define IR8_PACKET_NATIVE_DETAIL_MISSING UINT32_C(12)
#define IR8_PACKET_NATIVE_DETAIL_NONE UINT32_C(0)
#define IR8_PACKET_NATIVE_DETAIL_NULL_ARGUMENT UINT32_C(2)
#define IR8_PACKET_NATIVE_DETAIL_NULL_DOMAIN UINT32_C(18)
#define IR8_PACKET_NATIVE_DETAIL_OFFSET UINT32_C(9)
#define IR8_PACKET_NATIVE_DETAIL_ORDER UINT32_C(15)
#define IR8_PACKET_NATIVE_DETAIL_OVERFLOW UINT32_C(8)
#define IR8_PACKET_NATIVE_DETAIL_OVERLAP UINT32_C(11)
#define IR8_PACKET_NATIVE_DETAIL_OWNER UINT32_C(25)
#define IR8_PACKET_NATIVE_DETAIL_PURPOSE UINT32_C(6)
#define IR8_PACKET_NATIVE_DETAIL_REFERENCE UINT32_C(19)
#define IR8_PACKET_NATIVE_DETAIL_REVISION UINT32_C(5)
#define IR8_PACKET_NATIVE_DETAIL_STRING_BOUNDARY UINT32_C(21)
#define IR8_PACKET_NATIVE_DETAIL_TAG UINT32_C(17)
#define IR8_PACKET_NATIVE_DETAIL_UTF8 UINT32_C(20)
#define IR8_PACKET_NATIVE_DETAIL_VECTOR_SHARING UINT32_C(24)
#define IR8_PACKET_NATIVE_DETAIL_WORK_EXHAUSTED UINT32_C(27)
#define IR8_PACKET_NATIVE_PHASE_ARGUMENTS UINT32_C(1)
#define IR8_PACKET_NATIVE_PHASE_DIRECTORY UINT32_C(3)
#define IR8_PACKET_NATIVE_PHASE_FINAL_CENSUS UINT32_C(9)
#define IR8_PACKET_NATIVE_PHASE_HEADER_AND_SIZE UINT32_C(2)
#define IR8_PACKET_NATIVE_PHASE_MEMBERSHIPS_AND_BINDINGS UINT32_C(4)
#define IR8_PACKET_NATIVE_PHASE_ORIGINS_AND_DESCRIPTORS UINT32_C(7)
#define IR8_PACKET_NATIVE_PHASE_ROW_DOMAINS UINT32_C(5)
#define IR8_PACKET_NATIVE_PHASE_SLOTS_ACCESS_TRANSPORTS UINT32_C(8)
#define IR8_PACKET_NATIVE_PHASE_TYPES_AND_RESOLUTIONS UINT32_C(6)
#define IR8_PACKET_NATIVE_STATUS_ARGUMENT UINT32_C(1)
#define IR8_PACKET_NATIVE_STATUS_BINDING UINT32_C(6)
#define IR8_PACKET_NATIVE_STATUS_COUNT_LIMIT UINT32_C(12)
#define IR8_PACKET_NATIVE_STATUS_DIRECTORY UINT32_C(4)
#define IR8_PACKET_NATIVE_STATUS_EDGE_EQUATION UINT32_C(11)
#define IR8_PACKET_NATIVE_STATUS_HEADER UINT32_C(2)
#define IR8_PACKET_NATIVE_STATUS_INTERNAL UINT32_C(14)
#define IR8_PACKET_NATIVE_STATUS_MEMBERSHIP UINT32_C(5)
#define IR8_PACKET_NATIVE_STATUS_OK UINT32_C(0)
#define IR8_PACKET_NATIVE_STATUS_ORIGIN_EQUATION UINT32_C(10)
#define IR8_PACKET_NATIVE_STATUS_REPRESENTATION_EQUATION UINT32_C(9)
#define IR8_PACKET_NATIVE_STATUS_SCHEMA UINT32_C(7)
#define IR8_PACKET_NATIVE_STATUS_SIZE_LIMIT UINT32_C(3)
#define IR8_PACKET_NATIVE_STATUS_TYPE_EQUATION UINT32_C(8)
#define IR8_PACKET_NATIVE_STATUS_WORK_LIMIT UINT32_C(13)
#define IR8_PACKET_OBJECT_KIND_DESCRIPTOR UINT32_C(3)
#define IR8_PACKET_OBJECT_KIND_DIRECTORY UINT32_C(8)
#define IR8_PACKET_OBJECT_KIND_HEADER UINT32_C(7)
#define IR8_PACKET_OBJECT_KIND_INDEX_DESCRIPTOR UINT32_C(4)
#define IR8_PACKET_OBJECT_KIND_INDEX_TABLE UINT32_C(2)
#define IR8_PACKET_OBJECT_KIND_STRING_POOL UINT32_C(6)
#define IR8_PACKET_OBJECT_KIND_TABLE UINT32_C(1)
#define IR8_PACKET_OBJECT_KIND_VECTOR UINT32_C(5)
#define IR8_PACKET_ORIGIN_KIND_CONCRETE UINT32_C(1)
#define IR8_PACKET_ORIGIN_KIND_GENERIC UINT32_C(2)
#define IR8_PACKET_ORIGIN_KIND_INSTANCE UINT32_C(3)
#define IR8_PACKET_PROTOCOL_REPEAT UINT32_C(1)
#define IR8_PACKET_READY_KIND_DATA UINT32_C(2)
#define IR8_PACKET_READY_KIND_FUNCTION UINT32_C(4)
#define IR8_PACKET_READY_KIND_NONE UINT32_C(5)
#define IR8_PACKET_READY_KIND_SCALAR UINT32_C(1)
#define IR8_PACKET_READY_KIND_SUM UINT32_C(3)
#define IR8_PACKET_RELATION_BELOW UINT32_C(3)
#define IR8_PACKET_RELATION_DOWN UINT32_C(2)
#define IR8_PACKET_RELATION_SAME UINT32_C(1)
#define IR8_PACKET_RESULT_IDENTITY_ARGUMENT UINT32_C(2)
#define IR8_PACKET_RESULT_IDENTITY_UNKNOWN UINT32_C(1)
#define IR8_PACKET_SHAPE_KIND_BOOL UINT32_C(2)
#define IR8_PACKET_SHAPE_KIND_DATA UINT32_C(3)
#define IR8_PACKET_SHAPE_KIND_I64 UINT32_C(1)
#define IR8_PACKET_SHAPE_KIND_OPEN UINT32_C(6)
#define IR8_PACKET_SHAPE_KIND_REPEAT UINT32_C(5)
#define IR8_PACKET_SHAPE_KIND_SUM UINT32_C(4)
#define IR8_PACKET_SHAPE_SOURCE_CANONICAL_ARROW UINT32_C(2)
#define IR8_PACKET_SHAPE_SOURCE_LEGACY UINT32_C(1)
#define IR8_PACKET_SHAPE_SOURCE_SCOPED_OPEN UINT32_C(3)
#define IR8_PACKET_SITE_CATEGORY_APPLICATION UINT32_C(5)
#define IR8_PACKET_SITE_CATEGORY_CLOSURE UINT32_C(2)
#define IR8_PACKET_SITE_CATEGORY_DATA UINT32_C(1)
#define IR8_PACKET_SITE_CATEGORY_HOLE UINT32_C(4)
#define IR8_PACKET_SITE_CATEGORY_SCALAR UINT32_C(6)
#define IR8_PACKET_SITE_CATEGORY_SUM UINT32_C(7)
#define IR8_PACKET_SITE_CATEGORY_THUNK UINT32_C(3)
#define IR8_PACKET_SITE_CONTEXT_CONCRETE UINT32_C(1)
#define IR8_PACKET_SITE_CONTEXT_EXECUTION UINT32_C(3)
#define IR8_PACKET_SITE_CONTEXT_INTRODUCTION UINT32_C(2)
#define IR8_PACKET_SLOT_ROLE_ARGUMENT UINT32_C(5)
#define IR8_PACKET_SLOT_ROLE_CAPTURE UINT32_C(1)
#define IR8_PACKET_SLOT_ROLE_FIELD UINT32_C(2)
#define IR8_PACKET_SLOT_ROLE_FUNCTION UINT32_C(4)
#define IR8_PACKET_SLOT_ROLE_MEMO UINT32_C(6)
#define IR8_PACKET_SLOT_ROLE_VARIANT_FIELD UINT32_C(3)
#define IR8_PACKET_TRANSPORT_KIND_IDENTITY UINT32_C(1)
#define IR8_PACKET_TRANSPORT_KIND_PROJECT UINT32_C(2)
#define IR8_PACKET_TYPE_TAG_ARROW UINT32_C(3)
#define IR8_PACKET_TYPE_TAG_CLOSED UINT32_C(1)
#define IR8_PACKET_TYPE_TAG_RIGID UINT32_C(2)
#define IR8_PACKET_VECTOR_SUBKIND_CODE_CAPTURES UINT32_C(2)
#define IR8_PACKET_VECTOR_SUBKIND_DATA_FIELDS UINT32_C(9)
#define IR8_PACKET_VECTOR_SUBKIND_ENV UINT32_C(1)
#define IR8_PACKET_VECTOR_SUBKIND_EXECUTION_CAPTURES UINT32_C(3)
#define IR8_PACKET_VECTOR_SUBKIND_FAMILY_VARIANT_POINTERS UINT32_C(7)
#define IR8_PACKET_VECTOR_SUBKIND_FAMILY_VARIANTS UINT32_C(6)
#define IR8_PACKET_VECTOR_SUBKIND_INTRO_SITES UINT32_C(4)
#define IR8_PACKET_VECTOR_SUBKIND_USE_OCCURRENCES UINT32_C(5)
#define IR8_PACKET_VECTOR_SUBKIND_VARIANT_FIELDS UINT32_C(8)
#define IR8_PACKET_ELEMENT_TYPE UINT32_C(1)
#define IR8_PACKET_ELEMENT_CALLABLE_CONTRACT UINT32_C(2)
#define IR8_PACKET_ELEMENT_SCHEME UINT32_C(3)
#define IR8_PACKET_ELEMENT_ENV UINT32_C(4)
#define IR8_PACKET_ELEMENT_CODE_TYPING UINT32_C(5)
#define IR8_PACKET_ELEMENT_CODE_EXECUTION UINT32_C(6)
#define IR8_PACKET_ELEMENT_SHAPE_BINDING UINT32_C(7)
#define IR8_PACKET_ELEMENT_SHAPE_TYPING UINT32_C(8)
#define IR8_PACKET_ELEMENT_REPRESENTATION UINT32_C(9)
#define IR8_PACKET_ELEMENT_NOMINAL_FIELD UINT32_C(10)
#define IR8_PACKET_ELEMENT_FAMILY_TYPING UINT32_C(11)
#define IR8_PACKET_ELEMENT_TYPE_RESOLUTION UINT32_C(12)
#define IR8_PACKET_ELEMENT_REPRESENTATION_RESOLUTION UINT32_C(13)
#define IR8_PACKET_ELEMENT_SITE UINT32_C(14)
#define IR8_PACKET_ELEMENT_SITE_EXECUTION UINT32_C(15)
#define IR8_PACKET_ELEMENT_SLOT UINT32_C(16)
#define IR8_PACKET_ELEMENT_ACCESS UINT32_C(17)
#define IR8_PACKET_ELEMENT_INTRO UINT32_C(18)
#define IR8_PACKET_ELEMENT_USE UINT32_C(19)
#define IR8_PACKET_ELEMENT_TRANSPORT UINT32_C(20)
#define IR8_PACKET_ELEMENT_REGISTERED_ROW_REF UINT32_C(21)
#define IR8_PACKET_ELEMENT_REGISTERED_DESCRIPTOR_REF UINT32_C(22)
#define IR8_PACKET_ELEMENT_TYPE_REF UINT32_C(23)
#define IR8_PACKET_ELEMENT_CAPTURE_TYPING UINT32_C(24)
#define IR8_PACKET_ELEMENT_RESOLVED_CAPTURE UINT32_C(25)
#define IR8_PACKET_ELEMENT_SITE_REF UINT32_C(26)
#define IR8_PACKET_ELEMENT_PATH_REF UINT32_C(27)
#define IR8_PACKET_ELEMENT_VARIANT_TYPING UINT32_C(28)
#define IR8_PACKET_ELEMENT_VARIANT_REF UINT32_C(29)
#define IR8_PACKET_ELEMENT_NOMINAL_FIELD_REF UINT32_C(30)
#define IR8_PACKET_ELEMENT_SHAPE_SPEC UINT32_C(31)
#define IR8_PACKET_ELEMENT_CODE_SPEC UINT32_C(32)
#define IR8_PACKET_ELEMENT_FAMILY_SPEC UINT32_C(33)
#define IR8_PACKET_ELEMENT_VARIANT_SPEC UINT32_C(34)
#define IR8_PACKET_ELEMENT_FIELD_SPEC UINT32_C(35)
#define IR8_PACKET_ELEMENT_UTF8_BYTE UINT32_C(36)
#define IR8_PACKET_ELEMENT_PROGRAM_HEADER UINT32_C(37)
#define IR8_PACKET_ELEMENT_TYPED_HEADER UINT32_C(38)
#define IR8_PACKET_ELEMENT_DIGEST32 UINT32_C(39)
#define IR8_PACKET_ELEMENT_OBJECT_DIRECTORY_ENTRY UINT32_C(40)

typedef uint32_t Ir8PacketStatus;
typedef struct Ir8PacketSpan {
    uint32_t object;
    uint32_t count;
} Ir8PacketSpan;

typedef struct Ir8PacketType {
    uint32_t id;
    uint32_t tag;
    uint32_t atom;
    uint32_t scheme;
    uint32_t index;
    uint32_t argument;
    uint32_t result;
    uint32_t protocol;
    uint32_t result_identity;
} Ir8PacketType;

typedef struct Ir8PacketCallableContract {
    uint32_t id;
    uint32_t type;
    uint32_t argument;
    uint32_t result;
    uint32_t protocol;
    uint32_t result_identity;
} Ir8PacketCallableContract;

typedef struct Ir8PacketScheme {
    uint32_t id;
    uint32_t name;
    uint32_t parameters;
    uint32_t body;
    uint32_t neutral_env;
    uint32_t intro;
} Ir8PacketScheme;

typedef struct Ir8PacketEnv {
    uint32_t id;
    uint32_t scheme;
    uint32_t mode;
    Ir8PacketSpan arguments;
} Ir8PacketEnv;

typedef struct Ir8PacketCodeTyping {
    uint32_t id;
    uint32_t kind;
    uint32_t name;
    uint32_t scope;
    uint32_t callable_type;
    uint32_t argument;
    uint32_t result;
    Ir8PacketSpan captures;
    uint32_t body_path;
    uint32_t expected_protocol;
    uint32_t expected_identity_flag;
} Ir8PacketCodeTyping;

typedef struct Ir8PacketCodeExecution {
    uint32_t id;
    uint32_t code;
    uint32_t env;
    uint32_t callable_type;
    uint32_t argument;
    uint32_t result;
    Ir8PacketSpan captures;
} Ir8PacketCodeExecution;

typedef struct Ir8PacketShapeBinding {
    uint32_t id;
    uint32_t source_tag;
    uint32_t source_reference;
    uint32_t source_type;
    uint32_t source_scheme;
    uint32_t kind;
    uint32_t argument_rep;
    uint32_t result_rep;
} Ir8PacketShapeBinding;

typedef struct Ir8PacketShapeTyping {
    uint32_t id;
    uint32_t shape;
    uint32_t type;
    uint32_t scope;
    uint32_t contract;
} Ir8PacketShapeTyping;

typedef struct Ir8PacketRepresentation {
    uint32_t id;
    uint32_t shape;
    uint32_t typing;
    uint32_t ready_kind;
} Ir8PacketRepresentation;

typedef struct Ir8PacketNominalField {
    uint32_t id;
    uint32_t shape;
    uint32_t variant;
    uint32_t position;
    uint32_t name;
    uint32_t type;
    uint32_t declared_rep;
} Ir8PacketNominalField;

typedef struct Ir8PacketFamilyTyping {
    uint32_t id;
    uint32_t name;
    uint32_t shape;
    Ir8PacketSpan variants;
} Ir8PacketFamilyTyping;

typedef struct Ir8PacketTypeResolution {
    uint32_t id;
    uint32_t type;
    uint32_t env;
    uint32_t result;
} Ir8PacketTypeResolution;

typedef struct Ir8PacketRepresentationResolution {
    uint32_t id;
    uint32_t type;
    uint32_t env;
    uint32_t representation;
} Ir8PacketRepresentationResolution;

typedef struct Ir8PacketSite {
    uint32_t id;
    uint32_t path;
    uint32_t arm;
    uint32_t scope;
    uint32_t principal_type;
    uint32_t category;
    uint32_t code;
    uint32_t legacy_physical;
    uint32_t context_tag;
    uint32_t context_intro;
    uint32_t context_code;
    uint32_t context_scheme;
    uint32_t sum_family;
    uint32_t sum_variant;
} Ir8PacketSite;

typedef struct Ir8PacketSiteExecution {
    uint32_t id;
    uint32_t site;
    uint32_t env;
    uint32_t origin_kind;
    uint32_t principal_type;
    uint32_t representation;
    uint32_t code_execution;
} Ir8PacketSiteExecution;

typedef struct Ir8PacketSlot {
    uint32_t id;
    uint32_t site;
    uint32_t role_tag;
    uint32_t role_name;
    uint32_t role_variant;
    uint32_t role_field;
    uint32_t type;
    uint32_t relation;
} Ir8PacketSlot;

typedef struct Ir8PacketAccess {
    uint32_t id;
    uint32_t site;
    uint32_t origin_env;
    uint32_t mode;
    uint32_t use_env;
    uint32_t type;
    uint32_t scheme;
} Ir8PacketAccess;

typedef struct Ir8PacketIntro {
    uint32_t id;
    uint32_t scheme;
    uint32_t container_tag;
    uint32_t container_code;
    uint32_t generalize_path;
    uint32_t seal_path;
    uint32_t body_type;
    Ir8PacketSpan result_sites;
} Ir8PacketIntro;

typedef struct Ir8PacketUse {
    uint32_t id;
    uint32_t name;
    uint32_t scheme;
    Ir8PacketSpan arguments;
    uint32_t env;
    uint32_t result_type;
    Ir8PacketSpan occurrences;
} Ir8PacketUse;

typedef struct Ir8PacketTransport {
    uint32_t id;
    uint32_t source_access;
    uint32_t projection_env;
    uint32_t result_access;
    uint32_t kind;
} Ir8PacketTransport;

typedef struct Ir8PacketRegisteredRowRef {
    uint32_t domain;
    uint32_t row;
} Ir8PacketRegisteredRowRef;

typedef struct Ir8PacketRegisteredDescriptorRef {
    uint32_t domain;
    uint32_t row;
} Ir8PacketRegisteredDescriptorRef;

typedef struct Ir8PacketTypeRef {
    uint32_t row;
} Ir8PacketTypeRef;

typedef struct Ir8PacketCaptureTyping {
    uint32_t name;
    uint32_t type;
    uint32_t relation;
} Ir8PacketCaptureTyping;

typedef struct Ir8PacketResolvedCapture {
    uint32_t code;
    uint32_t position;
    uint32_t type;
} Ir8PacketResolvedCapture;

typedef struct Ir8PacketSiteRef {
    uint32_t row;
} Ir8PacketSiteRef;

typedef struct Ir8PacketPathRef {
    uint32_t path;
} Ir8PacketPathRef;

typedef struct Ir8PacketVariantTyping {
    uint32_t name;
    uint32_t index;
    Ir8PacketSpan fields;
} Ir8PacketVariantTyping;

typedef struct Ir8PacketVariantRef {
    uint32_t row;
} Ir8PacketVariantRef;

typedef struct Ir8PacketNominalFieldRef {
    uint32_t row;
} Ir8PacketNominalFieldRef;

typedef struct Ir8PacketShapeSpec {
    uint32_t shape;
    uint32_t typing;
    uint32_t representation;
    uint32_t kind;
    uint32_t fields_object;
    uint32_t field_first;
    uint32_t field_count;
    uint32_t argument_rep;
    uint32_t result_rep;
} Ir8PacketShapeSpec;

typedef struct Ir8PacketCodeSpec {
    uint32_t code;
    uint32_t principal_env;
    uint32_t principal_rep;
    uint32_t capture_object;
    uint32_t capture_first;
    uint32_t capture_count;
    uint32_t body_binding;
} Ir8PacketCodeSpec;

typedef struct Ir8PacketFamilySpec {
    uint32_t family;
    uint32_t shape;
    Ir8PacketSpan variants;
} Ir8PacketFamilySpec;

typedef struct Ir8PacketVariantSpec {
    uint32_t family;
    uint32_t index;
    uint32_t name;
    uint32_t shape;
    uint32_t fields_object;
    uint32_t field_first;
    uint32_t field_count;
} Ir8PacketVariantSpec;

typedef struct Ir8PacketFieldSpec {
    uint32_t owner_kind;
    uint32_t owner;
    uint32_t position;
    uint32_t name;
    uint32_t type;
    uint32_t nominal_declared_rep;
    uint32_t code_principal_rep;
    uint32_t relation;
} Ir8PacketFieldSpec;

typedef struct Ir8PacketProgramHeader {
    unsigned char magic[8];
    uint32_t abi_revision;
    uint32_t purpose;
    uint32_t packet_bytes;
    uint32_t packet_alignment;
    uint32_t directory_offset;
    uint32_t directory_count;
    uint32_t typed_header_object;
    uint32_t bindings_object;
    uint32_t string_pool_object;
    uint32_t resolution_access_transport_rows;
} Ir8PacketProgramHeader;

typedef struct Ir8PacketTypedHeader {
    Ir8PacketSpan table[20];
    Ir8PacketSpan table_index[20];
    Ir8PacketSpan descriptor[6];
    Ir8PacketSpan descriptor_index[6];
} Ir8PacketTypedHeader;

typedef struct Ir8PacketDigest32 {
    unsigned char bytes[32];
} Ir8PacketDigest32;

typedef struct Ir8PacketObjectDirectoryEntry {
    uint32_t source_inventory_id;
    uint32_t kind;
    uint32_t domain_or_subkind;
    uint32_t owner;
    uint32_t secondary_owner;
    uint32_t element_type;
    uint32_t offset;
    uint32_t count;
    uint32_t element_bytes;
    uint32_t element_alignment;
    uint32_t object_bytes;
} Ir8PacketObjectDirectoryEntry;

typedef struct Ir8PacketWalkFrame {
    uint32_t type;
    uint32_t env;
    uint32_t phase;
    uint32_t expected;
} Ir8PacketWalkFrame;

typedef struct Ir8PacketWorkspace {
    uint32_t type_depth[4096];
    uint32_t type_scope_mask[4096];
    unsigned char directory_seen[16384];
    Ir8PacketWalkFrame walk[32];
    uint64_t work_used;
    uint32_t scratch_state[16];
    unsigned char canonical_key[2][128];
} Ir8PacketWorkspace;

typedef struct Ir8PacketExpectedBindings {
    Ir8PacketDigest32 digests[5];
} Ir8PacketExpectedBindings;

typedef struct Ir8PacketReport {
    uint32_t status;
    uint32_t phase;
    uint32_t domain;
    uint32_t object;
    uint32_t row;
    uint32_t field;
    uint32_t detail;
    uint32_t packet_bytes;
    uint32_t declared_packet_alignment;
    uint32_t member_bytes_sum;
    uint32_t padding_bytes;
    uint32_t directory_entries;
    uint32_t member_objects;
    uint32_t resolution_access_transport_rows;
    uint64_t work_used;
    uint32_t workspace_bytes;
    uint32_t graph_executed;
    uint32_t source_admitted;
    uint32_t runtime_admitted;
    uint32_t runtime_guards_executed;
} Ir8PacketReport;

/* Prove representability before any compiled size/alignment is narrowed.
 * These expressions measure the actual target ABI; they do not prescribe it. */
_Static_assert(sizeof(Ir8PacketType) <= UINT32_MAX, "Ir8PacketType size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketType) <= UINT32_MAX, "Ir8PacketType alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketCallableContract) <= UINT32_MAX, "Ir8PacketCallableContract size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketCallableContract) <= UINT32_MAX, "Ir8PacketCallableContract alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketScheme) <= UINT32_MAX, "Ir8PacketScheme size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketScheme) <= UINT32_MAX, "Ir8PacketScheme alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketEnv) <= UINT32_MAX, "Ir8PacketEnv size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketEnv) <= UINT32_MAX, "Ir8PacketEnv alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketCodeTyping) <= UINT32_MAX, "Ir8PacketCodeTyping size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketCodeTyping) <= UINT32_MAX, "Ir8PacketCodeTyping alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketCodeExecution) <= UINT32_MAX, "Ir8PacketCodeExecution size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketCodeExecution) <= UINT32_MAX, "Ir8PacketCodeExecution alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketShapeBinding) <= UINT32_MAX, "Ir8PacketShapeBinding size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketShapeBinding) <= UINT32_MAX, "Ir8PacketShapeBinding alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketShapeTyping) <= UINT32_MAX, "Ir8PacketShapeTyping size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketShapeTyping) <= UINT32_MAX, "Ir8PacketShapeTyping alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketRepresentation) <= UINT32_MAX, "Ir8PacketRepresentation size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketRepresentation) <= UINT32_MAX, "Ir8PacketRepresentation alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketNominalField) <= UINT32_MAX, "Ir8PacketNominalField size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketNominalField) <= UINT32_MAX, "Ir8PacketNominalField alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketFamilyTyping) <= UINT32_MAX, "Ir8PacketFamilyTyping size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketFamilyTyping) <= UINT32_MAX, "Ir8PacketFamilyTyping alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketTypeResolution) <= UINT32_MAX, "Ir8PacketTypeResolution size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketTypeResolution) <= UINT32_MAX, "Ir8PacketTypeResolution alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketRepresentationResolution) <= UINT32_MAX, "Ir8PacketRepresentationResolution size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketRepresentationResolution) <= UINT32_MAX, "Ir8PacketRepresentationResolution alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketSite) <= UINT32_MAX, "Ir8PacketSite size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketSite) <= UINT32_MAX, "Ir8PacketSite alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketSiteExecution) <= UINT32_MAX, "Ir8PacketSiteExecution size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketSiteExecution) <= UINT32_MAX, "Ir8PacketSiteExecution alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketSlot) <= UINT32_MAX, "Ir8PacketSlot size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketSlot) <= UINT32_MAX, "Ir8PacketSlot alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketAccess) <= UINT32_MAX, "Ir8PacketAccess size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketAccess) <= UINT32_MAX, "Ir8PacketAccess alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketIntro) <= UINT32_MAX, "Ir8PacketIntro size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketIntro) <= UINT32_MAX, "Ir8PacketIntro alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketUse) <= UINT32_MAX, "Ir8PacketUse size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketUse) <= UINT32_MAX, "Ir8PacketUse alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketTransport) <= UINT32_MAX, "Ir8PacketTransport size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketTransport) <= UINT32_MAX, "Ir8PacketTransport alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketRegisteredRowRef) <= UINT32_MAX, "Ir8PacketRegisteredRowRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketRegisteredRowRef) <= UINT32_MAX, "Ir8PacketRegisteredRowRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketRegisteredDescriptorRef) <= UINT32_MAX, "Ir8PacketRegisteredDescriptorRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketRegisteredDescriptorRef) <= UINT32_MAX, "Ir8PacketRegisteredDescriptorRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketTypeRef) <= UINT32_MAX, "Ir8PacketTypeRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketTypeRef) <= UINT32_MAX, "Ir8PacketTypeRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketCaptureTyping) <= UINT32_MAX, "Ir8PacketCaptureTyping size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketCaptureTyping) <= UINT32_MAX, "Ir8PacketCaptureTyping alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketResolvedCapture) <= UINT32_MAX, "Ir8PacketResolvedCapture size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketResolvedCapture) <= UINT32_MAX, "Ir8PacketResolvedCapture alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketSiteRef) <= UINT32_MAX, "Ir8PacketSiteRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketSiteRef) <= UINT32_MAX, "Ir8PacketSiteRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketPathRef) <= UINT32_MAX, "Ir8PacketPathRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketPathRef) <= UINT32_MAX, "Ir8PacketPathRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketVariantTyping) <= UINT32_MAX, "Ir8PacketVariantTyping size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketVariantTyping) <= UINT32_MAX, "Ir8PacketVariantTyping alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketVariantRef) <= UINT32_MAX, "Ir8PacketVariantRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketVariantRef) <= UINT32_MAX, "Ir8PacketVariantRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketNominalFieldRef) <= UINT32_MAX, "Ir8PacketNominalFieldRef size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketNominalFieldRef) <= UINT32_MAX, "Ir8PacketNominalFieldRef alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketShapeSpec) <= UINT32_MAX, "Ir8PacketShapeSpec size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketShapeSpec) <= UINT32_MAX, "Ir8PacketShapeSpec alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketCodeSpec) <= UINT32_MAX, "Ir8PacketCodeSpec size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketCodeSpec) <= UINT32_MAX, "Ir8PacketCodeSpec alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketFamilySpec) <= UINT32_MAX, "Ir8PacketFamilySpec size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketFamilySpec) <= UINT32_MAX, "Ir8PacketFamilySpec alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketVariantSpec) <= UINT32_MAX, "Ir8PacketVariantSpec size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketVariantSpec) <= UINT32_MAX, "Ir8PacketVariantSpec alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketFieldSpec) <= UINT32_MAX, "Ir8PacketFieldSpec size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketFieldSpec) <= UINT32_MAX, "Ir8PacketFieldSpec alignment fits uint32_t");
_Static_assert(sizeof(unsigned char) <= UINT32_MAX, "unsigned char size fits uint32_t");
_Static_assert(_Alignof(unsigned char) <= UINT32_MAX, "unsigned char alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketProgramHeader) <= UINT32_MAX, "Ir8PacketProgramHeader size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketProgramHeader) <= UINT32_MAX, "Ir8PacketProgramHeader alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketTypedHeader) <= UINT32_MAX, "Ir8PacketTypedHeader size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketTypedHeader) <= UINT32_MAX, "Ir8PacketTypedHeader alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketDigest32) <= UINT32_MAX, "Ir8PacketDigest32 size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketDigest32) <= UINT32_MAX, "Ir8PacketDigest32 alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketObjectDirectoryEntry) <= UINT32_MAX, "Ir8PacketObjectDirectoryEntry size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketObjectDirectoryEntry) <= UINT32_MAX, "Ir8PacketObjectDirectoryEntry alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketSpan) <= UINT32_MAX, "Ir8PacketSpan size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketSpan) <= UINT32_MAX, "Ir8PacketSpan alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketWalkFrame) <= UINT32_MAX, "Ir8PacketWalkFrame size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketWalkFrame) <= UINT32_MAX, "Ir8PacketWalkFrame alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketWorkspace) <= UINT32_MAX, "Ir8PacketWorkspace size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketWorkspace) <= UINT32_MAX, "Ir8PacketWorkspace alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketExpectedBindings) <= UINT32_MAX, "Ir8PacketExpectedBindings size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketExpectedBindings) <= UINT32_MAX, "Ir8PacketExpectedBindings alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketReport) <= UINT32_MAX, "Ir8PacketReport size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketReport) <= UINT32_MAX, "Ir8PacketReport alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketStatus) <= UINT32_MAX, "Ir8PacketStatus size fits uint32_t");
_Static_assert(_Alignof(Ir8PacketStatus) <= UINT32_MAX, "Ir8PacketStatus alignment fits uint32_t");
_Static_assert(sizeof(Ir8PacketWorkspace) <= 131072, "IR8 workspace budget");
/* Preconditions: root is readable and immutable for root_bytes; expected,
 * workspace and report are valid, correctly sized, disjoint caller objects.
 * Unaligned readable root copies are supported. No arbitrary host-pointer
 * safety, source authenticity, executable capability or retained view is given.
 * Every call starts fresh. All four admission/execution flags remain zero. */
Ir8PacketStatus ir8_packet_validate(const void *root, size_t root_bytes,
    const Ir8PacketExpectedBindings *expected, Ir8PacketWorkspace *workspace,
    Ir8PacketReport *report);
#endif
