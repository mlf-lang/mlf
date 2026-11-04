/* Reader-only differential controls, not whole-packet/runtime admission.
 * All roots and pointer arithmetic below use real, bounded caller storage.
 * Deliberately malformed local views exercise defense-in-depth failures; they
 * are not claimed to satisfy fresh binding_prepare's immutable-view contract.
 */
#include "rir8_binding_internal.h"
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define ROWS 5u
#define OBJECTS 26u
#define OUT_BYTES 1024u
#define TABLES(X) \
 X(1,Ir8PacketType,t1) X(2,Ir8PacketCallableContract,t2) \
 X(3,Ir8PacketScheme,t3) X(4,Ir8PacketEnv,t4) \
 X(5,Ir8PacketCodeTyping,t5) X(6,Ir8PacketCodeExecution,t6) \
 X(7,Ir8PacketShapeBinding,t7) X(8,Ir8PacketShapeTyping,t8) \
 X(9,Ir8PacketRepresentation,t9) X(10,Ir8PacketNominalField,t10) \
 X(11,Ir8PacketFamilyTyping,t11) X(12,Ir8PacketTypeResolution,t12) \
 X(13,Ir8PacketRepresentationResolution,t13) X(14,Ir8PacketSite,t14) \
 X(15,Ir8PacketSiteExecution,t15) X(16,Ir8PacketSlot,t16) \
 X(17,Ir8PacketAccess,t17) X(18,Ir8PacketIntro,t18) \
 X(19,Ir8PacketUse,t19) X(20,Ir8PacketTransport,t20)
#define DESCRIPTORS(X) \
 X(1,31,Ir8PacketShapeSpec,d1) X(2,32,Ir8PacketCodeSpec,d2) \
 X(3,33,Ir8PacketFamilySpec,d3) X(4,34,Ir8PacketVariantSpec,d4) \
 X(5,35,Ir8PacketFieldSpec,d5) X(6,35,Ir8PacketFieldSpec,d6)
#define DECL_TABLE(id,type,member) type member[ROWS];
#define DECL_DESCRIPTOR(id,element,type,member) type member[ROWS];
typedef struct Root {
    Ir8PacketObjectDirectoryEntry directory[OBJECTS];
    TABLES(DECL_TABLE)
    DESCRIPTORS(DECL_DESCRIPTOR)
} Root;
#undef DECL_TABLE
#undef DECL_DESCRIPTOR
#define ASSERT_TABLE(id,type,member) _Static_assert(sizeof(type)<=OUT_BYTES,"row output capacity");
#define ASSERT_DESCRIPTOR(id,element,type,member) ASSERT_TABLE(id,type,member)
TABLES(ASSERT_TABLE)
DESCRIPTORS(ASSERT_DESCRIPTOR)
_Static_assert(sizeof(Root)<RT8_MAX_STATIC_BYTES,"bounded readable test root");

enum Operation { READ, REF, AUTH, OBJECT_READ };
typedef struct Result {
    uint32_t status;
    Rt8Diagnostic diagnostic;
    uint64_t used,total,result;
    int output_ok;
} Result;
static Root root;
static unsigned char foreign;
static unsigned failures;

static void setup(Rt8ProgramView *v) {
    memset(&root,0,sizeof(root)); memset(v,0,sizeof(*v));
    v->program.packet=&root; v->program.packet_bytes=sizeof(root);
    v->packet_header.directory_offset=(uint32_t)offsetof(Root,directory);
    v->packet_header.directory_count=OBJECTS;
#define INIT(object,kind,domain,element,type,member) do { \
    Ir8PacketObjectDirectoryEntry *d=&root.directory[object]; \
    *d=(Ir8PacketObjectDirectoryEntry){object,kind,domain,RT8_NULL,RT8_NULL,element, \
        (uint32_t)offsetof(Root,member),ROWS,(uint32_t)sizeof(type), \
        (uint32_t)_Alignof(type),(uint32_t)sizeof(root.member)}; \
    for(uint32_t i=0;i<ROWS;++i) { \
        memset(&root.member[i],(int)(0x30u+object+i),sizeof(type)); \
        if(kind==1u) memcpy(&root.member[i],&i,sizeof(i)); \
    } \
} while(0)
#define INIT_TABLE(id,type,member) INIT(id-1u,1u,id,id,type,member); \
    v->typed_header.table[id-1u]=(Ir8PacketSpan){id-1u,ROWS};
#define INIT_DESCRIPTOR(id,element,type,member) INIT(19u+id,3u,id,element,type,member); \
    v->typed_header.descriptor[id-1u]=(Ir8PacketSpan){19u+id,ROWS};
    TABLES(INIT_TABLE)
    DESCRIPTORS(INIT_DESCRIPTOR)
#undef INIT_TABLE
#undef INIT_DESCRIPTOR
#undef INIT
}

static uint64_t digest(const unsigned char *p,size_t n) {
    uint64_t h=UINT64_C(1469598103934665603);
    for(size_t i=0;i<n;++i) h=(h^p[i])*UINT64_C(1099511628211);
    return h;
}

/* original is copied before any mutation; references never use a corrupt
 * directory offset to manufacture an address. No foreign pointer is read. */
static Result invoke(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                     uint32_t row,enum Operation op,const Ir8PacketObjectDirectoryEntry *original,
                     const void *reference,size_t wanted,uint64_t limit) {
    Rt8Work work={0,17,limit};
    Rt8Diagnostic d={0};
    d.domain=d.object=d.row=d.field=d.guard_index=RT8_NULL;
    Rt8ReadState s={&work,&d};
    unsigned char out[OUT_BYTES],before[OUT_BYTES];
    memset(out,0xa5,sizeof(out)); memcpy(before,out,sizeof(out));
    const void *pointer=&foreign; uint32_t identity=UINT32_C(0xfedcba98);
    uint32_t object=kind==RT8_DOMAIN_KIND_PACKET_TABLE?domain-1u:19u+domain;
    uint32_t rc;
    if(op==READ) rc=kind==RT8_DOMAIN_KIND_PACKET_TABLE?
        rt8_view_table_read(v,domain,row,out,wanted,&s):
        rt8_view_descriptor_read(v,domain,row,out,wanted,&s);
    else if(op==REF) rc=kind==RT8_DOMAIN_KIND_PACKET_TABLE?
        rt8_view_table_ref(v,domain,row,&pointer,&s):
        rt8_view_descriptor_ref(v,domain,row,&pointer,&s);
    else if(op==AUTH) rc=kind==RT8_DOMAIN_KIND_PACKET_TABLE?
        rt8_view_table_auth(v,domain,reference,&identity,&s):
        rt8_view_descriptor_auth(v,domain,reference,&identity,&s);
    else rc=rt8_view_object_read(v,object,original->element_type,row,out,wanted,&s);
    Result r={rc,d,work.used,work.total,0,1};
    if(rc==RT8_STATUS_OK) {
        const unsigned char *expected=(const unsigned char *)&root+original->offset+row*original->element_bytes;
        if(op==READ || op==OBJECT_READ) {
            r.output_ok=memcmp(out,expected,original->element_bytes)==0 &&
                memcmp(out+original->element_bytes,before+original->element_bytes,OUT_BYTES-original->element_bytes)==0;
            r.result=digest(out,original->element_bytes);
        } else if(op==REF) {
            r.output_ok=pointer==expected; r.result=original->offset+row*original->element_bytes;
        } else {r.output_ok=identity==row;r.result=identity;}
    } else if(op==READ || op==OBJECT_READ) r.output_ok=memcmp(out,before,sizeof(out))==0;
    else if(op==REF) r.output_ok=pointer==&foreign;
    else r.output_ok=identity==UINT32_C(0xfedcba98);
    if(!r.output_ok || rc!=d.status || work.used>limit || work.total!=work.used+17u) ++failures;
    return r;
}

static void emit(const char *label,uint32_t kind,uint32_t domain,uint32_t row,
                 enum Operation op,const Result *r) {
    const Rt8Diagnostic *d=&r->diagnostic;
    printf("{\"case\":\"%s\",\"kind\":%u,\"domain\":%u,\"row\":%u,\"op\":%u,"
           "\"status\":%u,\"diagnostic\":[%u,%u,%u,%u,%u,%u,%u,%u,%u,%u],"
           "\"used\":%"PRIu64",\"total\":%"PRIu64",\"result\":%"PRIu64",\"output_ok\":%d}\n",
           label,kind,domain,row,(unsigned)op,r->status,d->status,d->phase,d->detail,d->region,
           d->domain_kind,d->domain,d->object,d->row,d->field,d->guard_index,
           r->used,r->total,r->result,r->output_ok);
}

static const char *const mutations[]={
    "element-tag","element-mismatch","element-size","element-alignment","kind-invalid",
    "kind-wrong","domain-wrong","owner","secondary-owner","count-mismatch","object-bytes",
    "offset-null","offset-outside","offset-unaligned","count-overflow","empty-object",
    "empty-offset","directory-count-over","directory-count-zero","directory-range",
    "directory-alignment","span-missing","span-empty-nonnull","span-empty","span-count-over",
    "null-root","oversized-root","directory-object-unregistered"
};
static void mutate(Rt8ProgramView *v,uint32_t kind,uint32_t domain,unsigned n) {
    uint32_t object=kind==RT8_DOMAIN_KIND_PACKET_TABLE?domain-1u:19u+domain;
    Ir8PacketObjectDirectoryEntry *d=&root.directory[object];
    Ir8PacketSpan *span=kind==RT8_DOMAIN_KIND_PACKET_TABLE?&v->typed_header.table[domain-1u]:&v->typed_header.descriptor[domain-1u];
    switch(n) {
    case 0:d->element_type=41;break;
    case 1:d->element_type=36;d->element_bytes=1;d->element_alignment=1;d->object_bytes=d->count;break;
    case 2:++d->element_bytes;break;
    case 3:++d->element_alignment;break;
    case 4:d->kind=9;break;
    case 5:d->kind=2;break;
    case 6:++d->domain_or_subkind;break;
    case 7:d->owner=0;break;
    case 8:d->secondary_owner=0;break;
    case 9:--d->count;d->object_bytes=d->count*d->element_bytes;break;
    case 10:--d->object_bytes;break;
    case 11:d->offset=RT8_NULL;break;
    case 12:d->offset=(uint32_t)sizeof(root)-1u;break;
    case 13:++d->offset;break;
    case 14:d->count=UINT32_MAX;break;
    case 15:d->count=0;d->object_bytes=0;d->offset=RT8_NULL;break;
    case 16:d->count=0;d->object_bytes=0;break;
    case 17:v->packet_header.directory_count=IR8_PACKET_MAX_DIRECTORY+1u;break;
    case 18:v->packet_header.directory_count=0;break;
    case 19:v->packet_header.directory_offset=(uint32_t)sizeof(root)-1u;break;
    case 20:++v->packet_header.directory_offset;break;
    case 21:span->object=RT8_NULL;break;
    case 22:span->count=0;break;
    case 23:span->count=0;span->object=RT8_NULL;break;
    case 24:span->count=RT8_MAX_STATIC_BYTES/sizeof(uint32_t)+1u;break;
    case 25:v->program.packet=NULL;break;
    case 26:v->program.packet_bytes=(size_t)RT8_MAX_STATIC_BYTES+1u;break;
    case 27:span->object=OBJECTS;break;
    default:++failures;break;
    }
}

static void domain_cases(uint32_t kind,uint32_t domain) {
    Rt8ProgramView v; setup(&v);
    uint32_t object=kind==RT8_DOMAIN_KIND_PACKET_TABLE?domain-1u:19u+domain;
    Ir8PacketObjectDirectoryEntry original=root.directory[object];
    for(uint32_t row=0;row<ROWS;row+=2u) for(unsigned op=READ;op<=OBJECT_READ;++op) {
        const void *ref=(const unsigned char *)&root+original.offset+row*original.element_bytes;
        Result r=invoke(&v,kind,domain,row,(enum Operation)op,&original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_OK) ++failures;
        emit("valid",kind,domain,row,(enum Operation)op,&r);
    }
    for(unsigned n=0;n<sizeof(mutations)/sizeof(mutations[0]);++n) {
        setup(&v); mutate(&v,kind,domain,n);
        for(unsigned op=READ;op<=OBJECT_READ;++op) {
            const void *ref=(const unsigned char *)&root+original.offset+4u*original.element_bytes;
            Result r=invoke(&v,kind,domain,4,(enum Operation)op,&original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
            int object_exception=op==OBJECT_READ && (n==5u || n==6u || n==7u || n==8u ||
                (n>=21u && n<=24u) || n==27u);
            if((r.status==RT8_STATUS_OK)!=object_exception) ++failures;
            emit(mutations[n],kind,domain,4,(enum Operation)op,&r);
        }
    }
    setup(&v);
    const unsigned char *base=(const unsigned char *)&root+original.offset;
    const void *bad_refs[]={NULL,&foreign,base+1u,base+ROWS*original.element_bytes};
    const char *bad_names[]={"null-ref","foreign-ref","interior-ref","one-past-ref"};
    for(unsigned i=0;i<4;++i) {
        Result r=invoke(&v,kind,domain,4,AUTH,&original,bad_refs[i],original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_REFERENCE) ++failures;
        emit(bad_names[i],kind,domain,4,AUTH,&r);
    }
    for(unsigned op=READ;op<=OBJECT_READ;++op) {
        if(op!=AUTH) {
            Result r=invoke(&v,kind,domain,ROWS,(enum Operation)op,&original,base,original.element_bytes,RT8_MAX_GUARD_WORK);
            if(r.status!=RT8_STATUS_REFERENCE) ++failures;
            emit("row-outside",kind,domain,ROWS,(enum Operation)op,&r);
        }
        if(op==READ || op==OBJECT_READ) {
            Result r=invoke(&v,kind,domain,4,(enum Operation)op,&original,base,SIZE_MAX,RT8_MAX_GUARD_WORK);
            if(r.status!=RT8_STATUS_ARGUMENT) ++failures;
            emit("wanted-size",kind,domain,4,(enum Operation)op,&r);
            r=invoke(&v,kind,domain,4,(enum Operation)op,&original,base,0,RT8_MAX_GUARD_WORK);
            if(r.status!=RT8_STATUS_ARGUMENT) ++failures;
            emit("wanted-zero",kind,domain,4,(enum Operation)op,&r);
        }
    }
    if(kind==RT8_DOMAIN_KIND_PACKET_TABLE) for(uint32_t bad=0;bad<ROWS;bad+=2u) {
        setup(&v); uint32_t wrong=UINT32_MAX;
        memcpy((unsigned char *)&root+original.offset+bad*original.element_bytes,&wrong,sizeof(wrong));
        Result r=invoke(&v,kind,domain,4,AUTH,&original,base+4u*original.element_bytes,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.row!=bad || r.diagnostic.detail!=RT8_DETAIL_UNREGISTERED) ++failures;
        emit(bad==0?"preceding-id-first":bad==2?"preceding-id-middle":"target-id",kind,domain,4,AUTH,&r);
    }
    /* Every possible available-work budget below the successful cost must fail
     * without changing any output. Success cost and exact boundary are recorded
     * independently per binary; optimization intentionally changes this cost. */
    setup(&v);
    for(unsigned op=READ;op<=OBJECT_READ;++op) {
        const void *ref=base+4u*original.element_bytes;
        Result full=invoke(&v,kind,domain,4,(enum Operation)op,&original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(full.status!=RT8_STATUS_OK || full.used>10000u) {++failures;continue;}
        for(uint64_t limit=1;limit<full.used;++limit) {
            Result r=invoke(&v,kind,domain,4,(enum Operation)op,&original,ref,original.element_bytes,limit);
            if(r.status!=RT8_STATUS_WORK_LIMIT || r.diagnostic.detail!=RT8_DETAIL_WORK_EXHAUSTED) ++failures;
        }
        Result edge=invoke(&v,kind,domain,4,(enum Operation)op,&original,ref,original.element_bytes,full.used);
        if(edge.status!=RT8_STATUS_OK || edge.used!=full.used) ++failures;
        emit("budget-exact-and-all-below",kind,domain,4,(enum Operation)op,&edge);
    }
}

/* Mutations happen only between completed calls. This checks that no local
 * authentication descriptor accidentally becomes a persistent credential. */
static void authentication_cases(uint32_t kind,uint32_t domain) {
    Rt8ProgramView v; setup(&v);
    uint32_t object=kind==RT8_DOMAIN_KIND_PACKET_TABLE?domain-1u:19u+domain;
    Ir8PacketObjectDirectoryEntry original=root.directory[object];
    Ir8PacketSpan *span=kind==RT8_DOMAIN_KIND_PACKET_TABLE?
        &v.typed_header.table[domain-1u]:&v.typed_header.descriptor[domain-1u];
    const unsigned char *base=(const unsigned char *)&root+original.offset;
    const void *last=base+4u*original.element_bytes;
    Result r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_OK) ++failures;
    emit("freshness-prime",kind,domain,4,AUTH,&r);
    root.directory[object].owner=0;
    r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.detail!=RT8_DETAIL_APPLICABILITY ||
       r.diagnostic.row!=0 || r.diagnostic.object!=object) ++failures;
    emit("freshness-owner",kind,domain,4,AUTH,&r);
    root.directory[object]=original;
    r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_OK) ++failures;
    emit("freshness-restored",kind,domain,4,AUTH,&r);
    ++root.directory[object].element_alignment;
    r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_ALIGNMENT || r.diagnostic.detail!=RT8_DETAIL_ALIGNMENT ||
       r.diagnostic.row!=0 || r.diagnostic.object!=object) ++failures;
    emit("freshness-alignment",kind,domain,4,AUTH,&r);
    for(uint32_t count=1;count<=2;++count) {
        root.directory[object]=original;
        root.directory[object].count=count;
        root.directory[object].object_bytes=count*original.element_bytes;
        span->count=count;
        const void *ref=base+(count-1u)*original.element_bytes;
        r=invoke(&v,kind,domain,count-1u,AUTH,&original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_OK) ++failures;
        emit(count==1?"short-one":"short-two",kind,domain,count-1u,AUTH,&r);
        r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.detail!=RT8_DETAIL_UNREGISTERED ||
           r.diagnostic.row!=RT8_NULL || r.diagnostic.object!=object) ++failures;
        emit(count==1?"short-one-miss":"short-two-miss",kind,domain,4,AUTH,&r);
    }
    setup(&v);
    if(kind==RT8_DOMAIN_KIND_PACKET_TABLE) {
        uint32_t wrong=UINT32_MAX;
        memcpy((unsigned char *)&root+original.offset+4u*original.element_bytes,&wrong,sizeof(wrong));
        r=invoke(&v,kind,domain,2,AUTH,&original,base+2u*original.element_bytes,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_OK) ++failures;
        emit("after-target-id",kind,domain,2,AUTH,&r);
    }
    setup(&v); v.packet_header.directory_count=0;
    r=invoke(&v,kind,domain,4,AUTH,&original,NULL,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.detail!=RT8_DETAIL_UNREGISTERED ||
       r.used!=0 || r.diagnostic.object!=RT8_NULL || r.diagnostic.row!=RT8_NULL) ++failures;
    emit("null-before-directory",kind,domain,4,AUTH,&r);
    span->count=0; span->object=RT8_NULL;
    r=invoke(&v,kind,domain,4,AUTH,&original,last,original.element_bytes,RT8_MAX_GUARD_WORK);
    if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.detail!=RT8_DETAIL_UNREGISTERED ||
       r.diagnostic.object!=RT8_NULL || r.diagnostic.row!=RT8_NULL) ++failures;
    emit("empty-before-directory",kind,domain,4,AUTH,&r);
    setup(&v);
    for(uint32_t row=0;row<=2;row+=2) {
        const void *ref=base+row*original.element_bytes;
        Result full=invoke(&v,kind,domain,row,AUTH,&original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(full.status!=RT8_STATUS_OK || full.used>10000u) {++failures;continue;}
        for(uint64_t limit=1;limit<full.used;++limit) {
            r=invoke(&v,kind,domain,row,AUTH,&original,ref,original.element_bytes,limit);
            if(r.status!=RT8_STATUS_WORK_LIMIT || r.diagnostic.detail!=RT8_DETAIL_WORK_EXHAUSTED) ++failures;
        }
        r=invoke(&v,kind,domain,row,AUTH,&original,ref,original.element_bytes,full.used);
        if(r.status!=RT8_STATUS_OK || r.used!=full.used) ++failures;
        emit("budget-auth-first-middle",kind,domain,row,AUTH,&r);
    }
}

static void argument_cases(void) {
    Rt8ProgramView v; setup(&v);
    Ir8PacketObjectDirectoryEntry original=root.directory[0];
    const void *ref=(const unsigned char *)&root+original.offset;
    for(unsigned op=READ;op<=OBJECT_READ;++op) {
        Result r=invoke(NULL,RT8_DOMAIN_KIND_PACKET_TABLE,1,0,(enum Operation)op,
                        &original,ref,original.element_bytes,RT8_MAX_GUARD_WORK);
        if(r.status!=RT8_STATUS_ARGUMENT || r.used!=0) ++failures;
        emit("null-view",RT8_DOMAIN_KIND_PACKET_TABLE,1,0,(enum Operation)op,&r);
    }
    for(unsigned k=0;k<2;++k) {
        uint32_t kind=k?RT8_DOMAIN_KIND_PACKET_DESCRIPTOR:RT8_DOMAIN_KIND_PACKET_TABLE;
        uint32_t domains[]={0,k?7u:21u,UINT32_MAX};
        for(unsigned i=0;i<3;++i) for(unsigned op=READ;op<=AUTH;++op) {
            Result r=invoke(&v,kind,domains[i],0,(enum Operation)op,&original,ref,
                            original.element_bytes,RT8_MAX_GUARD_WORK);
            if(r.status!=RT8_STATUS_REFERENCE || r.diagnostic.detail!=RT8_DETAIL_DOMAIN) ++failures;
            emit("domain-outside",kind,domains[i],0,(enum Operation)op,&r);
        }
    }
    for(unsigned op=READ;op<=OBJECT_READ;++op) {
        Rt8Work w={5,22,RT8_MAX_GUARD_WORK}; Rt8Diagnostic d={0}; Rt8ReadState s={&w,&d};
        uint32_t rc;
        if(op==READ) rc=rt8_view_table_read(&v,1,0,NULL,original.element_bytes,&s);
        else if(op==REF) rc=rt8_view_table_ref(&v,1,0,NULL,&s);
        else if(op==AUTH) rc=rt8_view_table_auth(&v,1,ref,NULL,&s);
        else rc=rt8_view_object_read(&v,0,1,0,NULL,original.element_bytes,&s);
        Result r={rc,d,w.used,w.total,0,w.used==5 && w.total==22};
        if(rc!=RT8_STATUS_ARGUMENT || !r.output_ok) ++failures;
        emit("null-output",RT8_DOMAIN_KIND_PACKET_TABLE,1,0,(enum Operation)op,&r);
    }
    Rt8Work w={5,22,5}; Rt8Diagnostic d={0}; Rt8ReadState s={&w,&d};
    uint32_t rc=rt8_work_reserve(&s,1);
    Result r={rc,d,w.used,w.total,0,w.used==5 && w.total==22};
    if(rc!=RT8_STATUS_WORK_LIMIT || !r.output_ok) ++failures;
    emit("reservation-atomic",0,0,0,READ,&r);
}

int main(void) {
    for(uint32_t domain=1;domain<=20;++domain) domain_cases(RT8_DOMAIN_KIND_PACKET_TABLE,domain);
    for(uint32_t domain=1;domain<=6;++domain) domain_cases(RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,domain);
    for(uint32_t domain=1;domain<=20;++domain) authentication_cases(RT8_DOMAIN_KIND_PACKET_TABLE,domain);
    for(uint32_t domain=1;domain<=6;++domain) authentication_cases(RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,domain);
    argument_cases();
    /* Independently sum the fixed nonempty directory predicate/copy charges:
     * 97 predicate/range/dispatch units plus two complete directory copies. */
    printf("{\"summary\":true,\"failures\":%u,\"table_domains\":20,\"descriptor_domains\":6,"
           "\"directory_work\":%zu}\n",failures,(size_t)97+2*sizeof(Ir8PacketObjectDirectoryEntry));
    if(fflush(stdout)!=0) return 74;
    return failures?1:0;
}
