/* Stage05A: no allocator, Context implementation, callbacks or instruction runs.
 * Readers borrow freshly admitted immutable roots; they are not a C sandbox. */
#include "rir8_binding_internal.h"
#include <string.h>

#define S(x) RT8_STATUS_##x
#define P(x) RT8_PHASE_##x
#define D(x) RT8_DETAIL_##x
#define N RT8_NULL
#define TRY(e) do { uint32_t rt8_rc_=(e); if (rt8_rc_!=S(OK)) return rt8_rc_; } while (0)
/* Fixed predicate groups reserve their full bounded cost before evaluation. */
#define REQUIRE(s,n,p,k,d) do { TRY(rt8_work_reserve((s),(n))); \
    if (!(p)) return fail((s),S(k),D(d)); } while (0)

static uint32_t fail(Rt8ReadState *s,uint32_t status,uint32_t detail) {
    if (s && s->diagnostic) {
        if (s->diagnostic->status!=S(OK)) return s->diagnostic->status;
        s->diagnostic->status=status; s->diagnostic->detail=detail;
    }
    return status;
}
static uint32_t active(Rt8ReadState *s) {
    if (!s) return S(ARGUMENT);
    if (!s->work || !s->diagnostic) return fail(s,S(ARGUMENT),D(NULL_ARGUMENT));
    return s->diagnostic->status;
}
uint32_t rt8_work_reserve(Rt8ReadState *s,uint64_t units) {
    uint32_t status=active(s);
    if (status!=S(OK)) return status;
    /* These fixed accounting preconditions cannot recursively charge. */
    if (!s->work->limit || s->work->limit>RT8_MAX_GUARD_WORK)
        return fail(s,S(ARGUMENT),D(COUNT));
    if (s->work->used>s->work->limit || s->work->total<s->work->used)
        return fail(s,S(INTERNAL),D(INTERNAL_INVARIANT));
    if (units>s->work->limit-s->work->used)
        return fail(s,S(WORK_LIMIT),D(WORK_EXHAUSTED));
    if (units>UINT64_MAX-s->work->total)
        return fail(s,S(OVERFLOW),D(OVERFLOW));
    s->work->used+=units; s->work->total+=units;
    return S(OK);
}
static void location(Rt8ReadState *s,uint32_t region,uint32_t kind,
                     uint32_t domain,uint32_t object,uint32_t row,uint32_t field) {
    if (s->diagnostic->status!=S(OK)) return;
    s->diagnostic->region=region; s->diagnostic->domain_kind=kind;
    s->diagnostic->domain=domain; s->diagnostic->object=object;
    s->diagnostic->row=row; s->diagnostic->field=field;
    s->diagnostic->guard_index=N;
}
static void phase(Rt8ReadState *s,uint32_t p) {
    if (s->diagnostic->status!=S(OK)) return;
    s->diagnostic->phase=p;
    location(s,RT8_REGION_NONE,RT8_DOMAIN_KIND_NONE,N,N,N,N);
}
static uint32_t reader_begin(const Rt8ProgramView *v,Rt8ReadState *s,const void *out) {
    TRY(active(s));
    if (!v || !out) return fail(s,S(ARGUMENT),D(NULL_ARGUMENT));
    if (s->diagnostic->phase==P(NONE)) s->diagnostic->phase=P(LOOKUP);
    return S(OK);
}
static uint32_t add32(Rt8ReadState *s,uint32_t a,uint32_t b,uint32_t *out) {
    REQUIRE(s,2,b<=UINT32_MAX-a,OVERFLOW,OVERFLOW);
    *out=a+b; return S(OK);
}
static uint32_t mul32(Rt8ReadState *s,uint32_t a,uint32_t b,uint32_t *out) {
    REQUIRE(s,3,a==0 || b<=UINT32_MAX/a,OVERFLOW,OVERFLOW);
    *out=a*b; return S(OK);
}
static uint32_t extent(Rt8ReadState *s,size_t total,uint32_t off,size_t n) {
    REQUIRE(s,1,total<=RT8_MAX_STATIC_BYTES,SIZE_LIMIT,LENGTH);
    REQUIRE(s,1,(size_t)off<=total,REFERENCE,OFFSET);
    REQUIRE(s,2,n<=total-(size_t)off,REFERENCE,OFFSET);
    return S(OK);
}
static uint32_t root_range(Rt8ReadState *s,const void *root,size_t bytes) {
    if (!root) return fail(s,S(ARGUMENT),D(NULL_ARGUMENT));
    REQUIRE(s,1,bytes<=RT8_MAX_STATIC_BYTES,SIZE_LIMIT,LENGTH);
    REQUIRE(s,2,(uintptr_t)root<=UINTPTR_MAX-(uintptr_t)bytes,OVERFLOW,OVERFLOW);
    return S(OK);
}
static uint32_t absolute_alignment(Rt8ReadState *s,const void *root,size_t total,
                                   uint32_t off,size_t alignment) {
    TRY(root_range(s,root,total)); TRY(extent(s,total,off,0));
    REQUIRE(s,1,alignment!=0,ALIGNMENT,ALIGNMENT);
    TRY(rt8_work_reserve(s,3));
    if (((uintptr_t)root+(uintptr_t)off)%(uintptr_t)alignment!=0)
        return fail(s,S(ALIGNMENT),D(ALIGNMENT));
    return S(OK);
}
static uint32_t copy_root(Rt8ReadState *s,const void *root,size_t total,
                           uint32_t off,size_t bytes,void *out) {
    if (!out) return fail(s,S(ARGUMENT),D(NULL_ARGUMENT));
    TRY(root_range(s,root,total)); TRY(extent(s,total,off,bytes));
    /* Reservation failure cannot write even the first destination byte. */
    TRY(rt8_work_reserve(s,(uint64_t)bytes));
    memcpy(out,(const unsigned char *)root+(size_t)off,bytes); return S(OK);
}
static uint32_t layout(Rt8ReadState *s,uint32_t element,size_t *bytes,size_t *align) {
    /* Fixed dispatch is bounded; reserve all 40 possible tag predicates. */
    TRY(rt8_work_reserve(s,40));
    switch (element) {
    case 1: *bytes=sizeof(Ir8PacketType); *align=_Alignof(Ir8PacketType); return S(OK);
    case 2: *bytes=sizeof(Ir8PacketCallableContract); *align=_Alignof(Ir8PacketCallableContract); return S(OK);
    case 3: *bytes=sizeof(Ir8PacketScheme); *align=_Alignof(Ir8PacketScheme); return S(OK);
    case 4: *bytes=sizeof(Ir8PacketEnv); *align=_Alignof(Ir8PacketEnv); return S(OK);
    case 5: *bytes=sizeof(Ir8PacketCodeTyping); *align=_Alignof(Ir8PacketCodeTyping); return S(OK);
    case 6: *bytes=sizeof(Ir8PacketCodeExecution); *align=_Alignof(Ir8PacketCodeExecution); return S(OK);
    case 7: *bytes=sizeof(Ir8PacketShapeBinding); *align=_Alignof(Ir8PacketShapeBinding); return S(OK);
    case 8: *bytes=sizeof(Ir8PacketShapeTyping); *align=_Alignof(Ir8PacketShapeTyping); return S(OK);
    case 9: *bytes=sizeof(Ir8PacketRepresentation); *align=_Alignof(Ir8PacketRepresentation); return S(OK);
    case 10: *bytes=sizeof(Ir8PacketNominalField); *align=_Alignof(Ir8PacketNominalField); return S(OK);
    case 11: *bytes=sizeof(Ir8PacketFamilyTyping); *align=_Alignof(Ir8PacketFamilyTyping); return S(OK);
    case 12: *bytes=sizeof(Ir8PacketTypeResolution); *align=_Alignof(Ir8PacketTypeResolution); return S(OK);
    case 13: *bytes=sizeof(Ir8PacketRepresentationResolution); *align=_Alignof(Ir8PacketRepresentationResolution); return S(OK);
    case 14: *bytes=sizeof(Ir8PacketSite); *align=_Alignof(Ir8PacketSite); return S(OK);
    case 15: *bytes=sizeof(Ir8PacketSiteExecution); *align=_Alignof(Ir8PacketSiteExecution); return S(OK);
    case 16: *bytes=sizeof(Ir8PacketSlot); *align=_Alignof(Ir8PacketSlot); return S(OK);
    case 17: *bytes=sizeof(Ir8PacketAccess); *align=_Alignof(Ir8PacketAccess); return S(OK);
    case 18: *bytes=sizeof(Ir8PacketIntro); *align=_Alignof(Ir8PacketIntro); return S(OK);
    case 19: *bytes=sizeof(Ir8PacketUse); *align=_Alignof(Ir8PacketUse); return S(OK);
    case 20: *bytes=sizeof(Ir8PacketTransport); *align=_Alignof(Ir8PacketTransport); return S(OK);
    case 21: *bytes=sizeof(Ir8PacketRegisteredRowRef); *align=_Alignof(Ir8PacketRegisteredRowRef); return S(OK);
    case 22: *bytes=sizeof(Ir8PacketRegisteredDescriptorRef); *align=_Alignof(Ir8PacketRegisteredDescriptorRef); return S(OK);
    case 23: *bytes=sizeof(Ir8PacketTypeRef); *align=_Alignof(Ir8PacketTypeRef); return S(OK);
    case 24: *bytes=sizeof(Ir8PacketCaptureTyping); *align=_Alignof(Ir8PacketCaptureTyping); return S(OK);
    case 25: *bytes=sizeof(Ir8PacketResolvedCapture); *align=_Alignof(Ir8PacketResolvedCapture); return S(OK);
    case 26: *bytes=sizeof(Ir8PacketSiteRef); *align=_Alignof(Ir8PacketSiteRef); return S(OK);
    case 27: *bytes=sizeof(Ir8PacketPathRef); *align=_Alignof(Ir8PacketPathRef); return S(OK);
    case 28: *bytes=sizeof(Ir8PacketVariantTyping); *align=_Alignof(Ir8PacketVariantTyping); return S(OK);
    case 29: *bytes=sizeof(Ir8PacketVariantRef); *align=_Alignof(Ir8PacketVariantRef); return S(OK);
    case 30: *bytes=sizeof(Ir8PacketNominalFieldRef); *align=_Alignof(Ir8PacketNominalFieldRef); return S(OK);
    case 31: *bytes=sizeof(Ir8PacketShapeSpec); *align=_Alignof(Ir8PacketShapeSpec); return S(OK);
    case 32: *bytes=sizeof(Ir8PacketCodeSpec); *align=_Alignof(Ir8PacketCodeSpec); return S(OK);
    case 33: *bytes=sizeof(Ir8PacketFamilySpec); *align=_Alignof(Ir8PacketFamilySpec); return S(OK);
    case 34: *bytes=sizeof(Ir8PacketVariantSpec); *align=_Alignof(Ir8PacketVariantSpec); return S(OK);
    case 35: *bytes=sizeof(Ir8PacketFieldSpec); *align=_Alignof(Ir8PacketFieldSpec); return S(OK);
    case 36: *bytes=sizeof(unsigned char); *align=_Alignof(unsigned char); return S(OK);
    case 37: *bytes=sizeof(Ir8PacketProgramHeader); *align=_Alignof(Ir8PacketProgramHeader); return S(OK);
    case 38: *bytes=sizeof(Ir8PacketTypedHeader); *align=_Alignof(Ir8PacketTypedHeader); return S(OK);
    case 39: *bytes=sizeof(Ir8PacketDigest32); *align=_Alignof(Ir8PacketDigest32); return S(OK);
    case 40: *bytes=sizeof(Ir8PacketObjectDirectoryEntry); *align=_Alignof(Ir8PacketObjectDirectoryEntry); return S(OK);
    default: return fail(s,S(REFERENCE),D(DOMAIN));
    }
}
static uint32_t directory(const Rt8ProgramView *v,uint32_t id,
                          Ir8PacketObjectDirectoryEntry *out,Rt8ReadState *s) {
    uint32_t delta,off,all_bytes,object_bytes;
    Ir8PacketObjectDirectoryEntry d; size_t bytes,align;
    REQUIRE(s,1,v->packet_header.directory_count<=IR8_PACKET_MAX_DIRECTORY,REFERENCE,COUNT);
    REQUIRE(s,1,id<v->packet_header.directory_count,REFERENCE,UNREGISTERED);
    TRY(mul32(s,v->packet_header.directory_count,(uint32_t)sizeof(d),&all_bytes));
    TRY(extent(s,v->program.packet_bytes,v->packet_header.directory_offset,all_bytes));
    TRY(mul32(s,id,(uint32_t)sizeof(d),&delta));
    TRY(add32(s,v->packet_header.directory_offset,delta,&off));
    TRY(absolute_alignment(s,v->program.packet,v->program.packet_bytes,off,_Alignof(Ir8PacketObjectDirectoryEntry)));
    TRY(copy_root(s,v->program.packet,v->program.packet_bytes,off,sizeof(d),&d));
    TRY(layout(s,d.element_type,&bytes,&align));
    REQUIRE(s,1,d.element_bytes==bytes,REFERENCE,LENGTH);
    REQUIRE(s,1,d.element_alignment==align,ALIGNMENT,ALIGNMENT);
    REQUIRE(s,2,d.kind>=1 && d.kind<=8,REFERENCE,DOMAIN);
    TRY(mul32(s,d.count,d.element_bytes,&object_bytes));
    REQUIRE(s,1,d.object_bytes==object_bytes,REFERENCE,LENGTH);
    TRY(rt8_work_reserve(s,1));
    if (d.count==0) {
        REQUIRE(s,1,d.offset==N,REFERENCE,OFFSET);
    } else {
        REQUIRE(s,1,d.offset!=N,REFERENCE,OFFSET);
        TRY(extent(s,v->program.packet_bytes,d.offset,d.object_bytes));
        TRY(absolute_alignment(s,v->program.packet,v->program.packet_bytes,d.offset,align));
    }
    TRY(rt8_work_reserve(s,sizeof(d))); *out=d; return S(OK);
}
/* d is the call-local result of directory(), still covered by the borrowed
 * immutable-root precondition. No entry is retained between reader calls. */
static uint32_t object_location_checked(const Rt8ProgramView *v,
                               const Ir8PacketObjectDirectoryEntry *d,uint32_t element,
                               uint32_t row,size_t wanted,uint32_t *off,Rt8ReadState *s) {
    uint32_t delta,result; size_t bytes,align;
    TRY(layout(s,element,&bytes,&align));
    REQUIRE(s,1,d->element_type==element,REFERENCE,DOMAIN);
    REQUIRE(s,1,wanted==bytes,ARGUMENT,LENGTH);
    REQUIRE(s,1,row<d->count,REFERENCE,UNREGISTERED);
    TRY(mul32(s,row,d->element_bytes,&delta));
    TRY(extent(s,d->object_bytes,delta,bytes)); TRY(add32(s,d->offset,delta,&result));
    TRY(extent(s,v->program.packet_bytes,result,bytes));
    TRY(absolute_alignment(s,v->program.packet,v->program.packet_bytes,result,align));
    *off=result; return S(OK);
}
static uint32_t object_location(const Rt8ProgramView *v,uint32_t object,uint32_t element,
                               uint32_t row,size_t wanted,uint32_t *off,Rt8ReadState *s) {
    Ir8PacketObjectDirectoryEntry d;
    TRY(directory(v,object,&d,s));
    return object_location_checked(v,&d,element,row,wanted,off,s);
}
uint32_t rt8_view_object_read(const Rt8ProgramView *v,uint32_t object,uint32_t element,
                             uint32_t row,void *out,size_t n,Rt8ReadState *s) {
    uint32_t off;
    TRY(reader_begin(v,s,out));
    location(s,RT8_REGION_PACKET,RT8_DOMAIN_KIND_NONE,N,object,row,N);
    TRY(object_location(v,object,element,row,n,&off,s));
    return copy_root(s,v->program.packet,v->program.packet_bytes,off,n,out);
}
static uint32_t descriptor_element(Rt8ReadState *s,uint32_t domain,uint32_t *out) {
    REQUIRE(s,2,domain>=1 && domain<=6,REFERENCE,DOMAIN);
    TRY(rt8_work_reserve(s,6));
    switch(domain) {
    case 1: *out=31; break; case 2: *out=32; break; case 3: *out=33; break;
    case 4: *out=34; break; case 5: case 6: *out=35; break;
    default: return fail(s,S(INTERNAL),D(INTERNAL_INVARIANT));
    }
    return S(OK);
}
static uint32_t domain_span(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                            Ir8PacketSpan *span,uint32_t *element,Rt8ReadState *s) {
    TRY(rt8_work_reserve(s,1));
    if (kind==RT8_DOMAIN_KIND_PACKET_TABLE) {
        REQUIRE(s,2,domain>=1 && domain<=20,REFERENCE,DOMAIN);
        TRY(rt8_work_reserve(s,sizeof(*span))); *span=v->typed_header.table[domain-1]; *element=domain;
    } else {
        REQUIRE(s,1,kind==RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,REFERENCE,DOMAIN);
        TRY(descriptor_element(s,domain,element));
        TRY(rt8_work_reserve(s,sizeof(*span))); *span=v->typed_header.descriptor[domain-1];
    }
    /* A finite row ceiling is still needed before an authentication scan. */
    REQUIRE(s,1,span->count<=RT8_MAX_STATIC_BYTES/sizeof(uint32_t),REFERENCE,COUNT);
    TRY(rt8_work_reserve(s,1));
    if (span->count==0) REQUIRE(s,1,span->object==N,REFERENCE,MISSING);
    else REQUIRE(s,1,span->object!=N,REFERENCE,MISSING);
    return S(OK);
}
static uint32_t domain_location(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                               uint32_t row,size_t wanted,uint32_t *off,Rt8ReadState *s) {
    Ir8PacketSpan span; Ir8PacketObjectDirectoryEntry d;
    uint32_t element,offset,id,expected_kind;
    TRY(domain_span(v,kind,domain,&span,&element,s));
    location(s,RT8_REGION_PACKET,kind,domain,span.object,row,N);
    REQUIRE(s,1,row<span.count,REFERENCE,UNREGISTERED);
    TRY(directory(v,span.object,&d,s));
    TRY(rt8_work_reserve(s,1)); expected_kind=kind==RT8_DOMAIN_KIND_PACKET_TABLE?1:3;
    REQUIRE(s,1,d.kind==expected_kind,REFERENCE,DOMAIN);
    REQUIRE(s,1,d.domain_or_subkind==domain,REFERENCE,DOMAIN);
    REQUIRE(s,1,d.owner==N,REFERENCE,APPLICABILITY);
    REQUIRE(s,1,d.secondary_owner==N,REFERENCE,APPLICABILITY);
    REQUIRE(s,1,d.count==span.count,REFERENCE,COUNT);
    TRY(object_location_checked(v,&d,element,row,wanted,&offset,s));
    TRY(rt8_work_reserve(s,1));
    if (kind==RT8_DOMAIN_KIND_PACKET_TABLE) {
        /* All twenty table row types begin with their checked uint32_t id. */
        TRY(copy_root(s,v->program.packet,v->program.packet_bytes,offset,sizeof(id),&id));
        REQUIRE(s,1,id==row,REFERENCE,UNREGISTERED);
    }
    *off=offset; return S(OK);
}
static uint32_t domain_read(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                            uint32_t row,void *out,size_t n,Rt8ReadState *s) {
    uint32_t off;
    TRY(reader_begin(v,s,out)); location(s,RT8_REGION_PACKET,kind,domain,N,row,N);
    TRY(domain_location(v,kind,domain,row,n,&off,s));
    return copy_root(s,v->program.packet,v->program.packet_bytes,off,n,out);
}
uint32_t rt8_view_table_read(const Rt8ProgramView *v,uint32_t d,uint32_t row,
                            void *out,size_t n,Rt8ReadState *s) {
    return domain_read(v,RT8_DOMAIN_KIND_PACKET_TABLE,d,row,out,n,s);
}
uint32_t rt8_view_descriptor_read(const Rt8ProgramView *v,uint32_t d,uint32_t row,
                                 void *out,size_t n,Rt8ReadState *s) {
    return domain_read(v,RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,d,row,out,n,s);
}
static uint32_t domain_ref(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                           uint32_t row,const void **out,Rt8ReadState *s) {
    uint32_t element,off; size_t bytes,align; Ir8PacketSpan span;
    TRY(reader_begin(v,s,out)); location(s,RT8_REGION_PACKET,kind,domain,N,row,N);
    TRY(domain_span(v,kind,domain,&span,&element,s)); TRY(layout(s,element,&bytes,&align));
    TRY(domain_location(v,kind,domain,row,bytes,&off,s));
    TRY(rt8_work_reserve(s,sizeof(*out)+1));
    *out=(const unsigned char *)v->program.packet+(size_t)off; return S(OK);
}
uint32_t rt8_view_table_ref(const Rt8ProgramView *v,uint32_t d,uint32_t row,
                           const void **out,Rt8ReadState *s) {
    return domain_ref(v,RT8_DOMAIN_KIND_PACKET_TABLE,d,row,out,s);
}
uint32_t rt8_view_descriptor_ref(const Rt8ProgramView *v,uint32_t d,uint32_t row,
                                const void **out,Rt8ReadState *s) {
    return domain_ref(v,RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,d,row,out,s);
}
static uint32_t domain_auth(const Rt8ProgramView *v,uint32_t kind,uint32_t domain,
                            const void *reference,uint32_t *out,Rt8ReadState *s) {
    uint32_t i,element; Ir8PacketSpan span;
    TRY(reader_begin(v,s,out)); location(s,RT8_REGION_PACKET,kind,domain,N,N,N);
    if (!reference) return fail(s,S(REFERENCE),D(UNREGISTERED));
    TRY(domain_span(v,kind,domain,&span,&element,s));
    for(i=0;;++i) {
        const void *candidate;
        TRY(rt8_work_reserve(s,1)); if (i>=span.count) break;
        TRY(rt8_work_reserve(s,1));
        TRY(domain_ref(v,kind,domain,i,&candidate,s));
        TRY(rt8_work_reserve(s,1));
        if (reference==candidate) {
            TRY(rt8_work_reserve(s,sizeof(*out))); *out=i; return S(OK);
        }
    }
    location(s,RT8_REGION_PACKET,kind,domain,span.object,N,N);
    return fail(s,S(REFERENCE),D(UNREGISTERED));
}
uint32_t rt8_view_table_auth(const Rt8ProgramView *v,uint32_t d,const void *ref,
                            uint32_t *out,Rt8ReadState *s) {
    return domain_auth(v,RT8_DOMAIN_KIND_PACKET_TABLE,d,ref,out,s);
}
uint32_t rt8_view_descriptor_auth(const Rt8ProgramView *v,uint32_t d,const void *ref,
                                 uint32_t *out,Rt8ReadState *s) {
    return domain_auth(v,RT8_DOMAIN_KIND_PACKET_DESCRIPTOR,d,ref,out,s);
}
static uint32_t code_offset(const Rt8ProgramView *v,uint32_t id,uint32_t *out,Rt8ReadState *s) {
    uint32_t bytes,delta,off;
    REQUIRE(s,1,v->binding_header.code_count<=2048,REFERENCE,COUNT);
    REQUIRE(s,1,v->binding_header.code_count==v->typed_header.table[4].count,BINDING,COUNT);
    REQUIRE(s,1,v->binding_header.code_count==v->typed_header.descriptor[1].count,BINDING,COUNT);
    REQUIRE(s,1,id<v->binding_header.code_count,REFERENCE,UNREGISTERED);
    REQUIRE(s,1,v->binding_header.code_offset!=N,REFERENCE,MISSING);
    TRY(mul32(s,v->binding_header.code_count,(uint32_t)sizeof(Rt8Code),&bytes));
    TRY(extent(s,v->program.binding_bytes,v->binding_header.code_offset,bytes));
    TRY(mul32(s,id,(uint32_t)sizeof(Rt8Code),&delta));
    TRY(add32(s,v->binding_header.code_offset,delta,&off));
    TRY(absolute_alignment(s,v->program.binding,v->program.binding_bytes,off,_Alignof(Rt8Code)));
    *out=off; return S(OK);
}
uint32_t rt8_view_code_read(const Rt8ProgramView *v,uint32_t id,Rt8Code *out,Rt8ReadState *s) {
    uint32_t off; Rt8Code code; Ir8PacketCodeTyping typing; Ir8PacketCodeSpec spec;
    TRY(reader_begin(v,s,out));
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NATIVE_CODE,0,N,id,N);
    TRY(code_offset(v,id,&off,s));
    TRY(copy_root(s,v->program.binding,v->program.binding_bytes,off,sizeof(code),&code));
    s->diagnostic->field=0; REQUIRE(s,1,code.code_id==id,BINDING,ORDER);
    s->diagnostic->field=1; REQUIRE(s,1,code.body!=NULL,UNBOUND,NULL_CALLBACK);
    TRY(rt8_view_table_read(v,5,id,&typing,sizeof(typing),s));
    TRY(rt8_view_descriptor_read(v,2,id,&spec,sizeof(spec),s));
    s->diagnostic->field=0; REQUIRE(s,1,spec.code==id,BINDING,APPLICABILITY);
    s->diagnostic->field=6;
    REQUIRE(s,1,spec.body_binding==IR8_PACKET_BODY_BINDING_UNBOUND,BINDING,APPLICABILITY);
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NATIVE_CODE,0,N,id,N);
    TRY(rt8_work_reserve(s,sizeof(code))); *out=code; return S(OK);
}
uint32_t rt8_view_code_ref(const Rt8ProgramView *v,uint32_t id,const Rt8Code **out,Rt8ReadState *s) {
    Rt8Code code; uint32_t off;
    TRY(reader_begin(v,s,out)); TRY(rt8_view_code_read(v,id,&code,s));
    TRY(code_offset(v,id,&off,s));
    TRY(rt8_work_reserve(s,sizeof(*out)+1));
    *out=(const Rt8Code *)((const unsigned char *)v->program.binding+(size_t)off);
    return S(OK);
}
uint32_t rt8_view_code_auth(const Rt8ProgramView *v,const Rt8Code *ref,uint32_t *out,Rt8ReadState *s) {
    uint32_t i;
    TRY(reader_begin(v,s,out));
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NATIVE_CODE,0,N,N,N);
    if (!ref) return fail(s,S(REFERENCE),D(UNREGISTERED));
    REQUIRE(s,1,v->binding_header.code_count<=2048,REFERENCE,COUNT);
    for(i=0;;++i) {
        const Rt8Code *candidate;
        TRY(rt8_work_reserve(s,1)); if(i>=v->binding_header.code_count) break;
        TRY(rt8_work_reserve(s,1)); TRY(rt8_view_code_ref(v,i,&candidate,s));
        TRY(rt8_work_reserve(s,1));
        if(ref==candidate) { TRY(rt8_work_reserve(s,sizeof(*out))); *out=i; return S(OK); }
    }
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NATIVE_CODE,0,N,N,N);
    return fail(s,S(REFERENCE),D(UNREGISTERED));
}
static uint32_t label_index(const Rt8ProgramView *v,uint32_t id,uint32_t *out,Rt8ReadState *s) {
    uint32_t bytes,delta,off,index;
    REQUIRE(s,1,v->binding_header.label_count<=RT8_MAX_LABELS,REFERENCE,COUNT);
    REQUIRE(s,1,v->binding_header.label_bytes<=RT8_MAX_LABEL_BYTES,REFERENCE,LENGTH);
    REQUIRE(s,1,id<v->binding_header.label_count,REFERENCE,UNREGISTERED);
    REQUIRE(s,1,v->binding_header.label_index_offset!=N,REFERENCE,MISSING);
    REQUIRE(s,1,v->binding_header.label_bytes_offset!=N,REFERENCE,MISSING);
    TRY(mul32(s,v->binding_header.label_count,(uint32_t)sizeof(uint32_t),&bytes));
    TRY(extent(s,v->program.binding_bytes,v->binding_header.label_index_offset,bytes));
    TRY(extent(s,v->program.binding_bytes,v->binding_header.label_bytes_offset,v->binding_header.label_bytes));
    TRY(mul32(s,id,(uint32_t)sizeof(uint32_t),&delta));
    TRY(add32(s,v->binding_header.label_index_offset,delta,&off));
    TRY(absolute_alignment(s,v->program.binding,v->program.binding_bytes,off,_Alignof(uint32_t)));
    TRY(copy_root(s,v->program.binding,v->program.binding_bytes,off,sizeof(index),&index));
    REQUIRE(s,1,index<v->binding_header.label_bytes,REFERENCE,OFFSET);
    TRY(rt8_work_reserve(s,sizeof(*out))); *out=index; return S(OK);
}
static uint32_t label_byte(const Rt8ProgramView *v,uint32_t index,unsigned char *out,Rt8ReadState *s) {
    uint32_t off;
    REQUIRE(s,1,v->binding_header.label_bytes<=RT8_MAX_LABEL_BYTES,REFERENCE,LENGTH);
    REQUIRE(s,1,index<v->binding_header.label_bytes,REFERENCE,OFFSET);
    TRY(add32(s,v->binding_header.label_bytes_offset,index,&off));
    return copy_root(s,v->program.binding,v->program.binding_bytes,off,sizeof(*out),out);
}
static uint32_t label_bounds(const Rt8ProgramView *v,uint32_t id,
                             uint32_t *start,uint32_t *end,Rt8ReadState *s) {
    uint32_t first,last,next; unsigned char b;
    TRY(label_index(v,id,&first,s)); TRY(add32(s,id,1,&next));
    TRY(rt8_work_reserve(s,1));
    if(next<v->binding_header.label_count) TRY(label_index(v,next,&last,s));
    else last=v->binding_header.label_bytes;
    REQUIRE(s,1,last>first,REFERENCE,ORDER);
    REQUIRE(s,2,last-first>=2,REFERENCE,LENGTH); /* one nonempty string + NUL */
    TRY(rt8_work_reserve(s,1));
    if(id==0) REQUIRE(s,1,first==0,REFERENCE,OFFSET);
    else {
        REQUIRE(s,1,first!=0,REFERENCE,OFFSET);
        TRY(rt8_work_reserve(s,1)); TRY(label_byte(v,first-1,&b,s));
        REQUIRE(s,1,b==0,REFERENCE,OFFSET);
    }
    TRY(rt8_work_reserve(s,1)); TRY(label_byte(v,last-1,&b,s));
    REQUIRE(s,1,b==0,REFERENCE,LENGTH);
    *start=first; *end=last; return S(OK);
}
uint32_t rt8_view_label(const Rt8ProgramView *v,uint32_t id,const char **out,Rt8ReadState *s) {
    uint32_t first,last,off;
    TRY(reader_begin(v,s,out));
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_LABEL,0,N,id,0);
    TRY(label_bounds(v,id,&first,&last,s));
    TRY(add32(s,v->binding_header.label_bytes_offset,first,&off));
    TRY(extent(s,v->program.binding_bytes,off,1));
    TRY(rt8_work_reserve(s,sizeof(*out)+1));
    *out=(const char *)((const unsigned char *)v->program.binding+(size_t)off); return S(OK);
}
uint32_t rt8_view_label_auth(const Rt8ProgramView *v,const char *ref,uint32_t *out,Rt8ReadState *s) {
    uint32_t i;
    TRY(reader_begin(v,s,out)); location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_LABEL,0,N,N,N);
    if(!ref) return fail(s,S(REFERENCE),D(UNREGISTERED));
    REQUIRE(s,1,v->binding_header.label_count<=RT8_MAX_LABELS,REFERENCE,COUNT);
    for(i=0;;++i) {
        const char *candidate;
        TRY(rt8_work_reserve(s,1)); if(i>=v->binding_header.label_count) break;
        TRY(rt8_work_reserve(s,1)); TRY(rt8_view_label(v,i,&candidate,s));
        TRY(rt8_work_reserve(s,1));
        if(ref==candidate) { TRY(rt8_work_reserve(s,sizeof(*out))); *out=i; return S(OK); }
    }
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_LABEL,0,N,N,N);
    return fail(s,S(REFERENCE),D(UNREGISTERED));
}
/* Strict UTF-8; bounded sequences, no locale or host string functions. */
static uint32_t utf8_string(const Rt8ProgramView *v,uint32_t first,uint32_t last,Rt8ReadState *s) {
    uint32_t pos=first,stop,length,j,next; unsigned char a,b;
    REQUIRE(s,1,last>first,BINDING,LENGTH); TRY(rt8_work_reserve(s,1)); stop=last-1;
    for(;;) {
        TRY(rt8_work_reserve(s,1)); if(pos>=stop) break;
        TRY(rt8_work_reserve(s,1)); TRY(label_byte(v,pos,&a,s));
        REQUIRE(s,1,a!=0,BINDING,LENGTH);
        TRY(rt8_work_reserve(s,8));
        if(a<0x80) length=1;
        else if(a>=0xc2 && a<=0xdf) length=2;
        else if(a>=0xe0 && a<=0xef) length=3;
        else if(a>=0xf0 && a<=0xf4) length=4;
        else return fail(s,S(BINDING),D(UNSUPPORTED));
        TRY(add32(s,pos,length,&next)); REQUIRE(s,1,next<=stop,BINDING,LENGTH);
        for(j=1;;++j) {
            uint32_t at;
            TRY(rt8_work_reserve(s,1)); if(j>=length) break;
            TRY(rt8_work_reserve(s,1)); TRY(add32(s,pos,j,&at)); TRY(label_byte(v,at,&b,s));
            REQUIRE(s,2,b>=0x80 && b<=0xbf,BINDING,UNSUPPORTED);
            TRY(rt8_work_reserve(s,13));
            if(j==1 && ((a==0xe0 && b<0xa0)||(a==0xed && b>0x9f)||
                        (a==0xf0 && b<0x90)||(a==0xf4 && b>0x8f)))
                return fail(s,S(BINDING),D(UNSUPPORTED));
        }
        pos=next;
    }
    REQUIRE(s,1,pos==stop,BINDING,LENGTH); return S(OK);
}
static uint32_t label_order(const Rt8ProgramView *v,uint32_t a,uint32_t aend,
                            uint32_t b,uint32_t bend,Rt8ReadState *s) {
    for(;;) {
        unsigned char x,y;
        TRY(rt8_work_reserve(s,1));
        REQUIRE(s,1,a<aend,BINDING,LENGTH); REQUIRE(s,1,b<bend,BINDING,LENGTH);
        TRY(label_byte(v,a,&x,s)); TRY(label_byte(v,b,&y,s));
        TRY(rt8_work_reserve(s,1)); if(x<y) return S(OK);
        REQUIRE(s,1,x==y,BINDING,ORDER);
        REQUIRE(s,1,x!=0,BINDING,DUPLICATE);
        TRY(add32(s,a,1,&a)); TRY(add32(s,b,1,&b));
    }
}
static uint32_t check_labels(const Rt8ProgramView *v,Rt8ReadState *s) {
    uint32_t i,previous=0,previous_end=0,expected=0;
    REQUIRE(s,1,v->binding_header.label_count<=RT8_MAX_LABELS,BINDING,COUNT);
    for(i=0;;++i) {
        uint32_t first,last;
        TRY(rt8_work_reserve(s,1)); if(i>=v->binding_header.label_count) break;
        TRY(rt8_work_reserve(s,1));
        location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_LABEL,0,N,i,0);
        TRY(label_bounds(v,i,&first,&last,s)); REQUIRE(s,1,first==expected,BINDING,OFFSET);
        s->diagnostic->field=1; TRY(utf8_string(v,first,last,s));
        TRY(rt8_work_reserve(s,1)); if(i!=0) TRY(label_order(v,previous,previous_end,first,last,s));
        previous=first; previous_end=last; expected=last;
    }
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_LABEL,0,N,N,N);
    REQUIRE(s,1,expected==v->binding_header.label_bytes,BINDING,LENGTH);
    return S(OK);
}
static uint32_t header_field(Rt8ReadState *s,uint32_t field) {
    location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NONE,N,N,N,field);
    return S(OK);
}
static uint32_t check_native_header(Rt8ProgramView *v,Rt8ReadState *s) {
    const unsigned char magic[8]=RT8_BINDING_MAGIC; uint32_t i;
    Rt8BindingHeader *h=&v->binding_header;
    TRY(copy_root(s,v->program.binding,v->program.binding_bytes,0,sizeof(*h),h));
    TRY(header_field(s,0));
    for(i=0;;++i) {
        TRY(rt8_work_reserve(s,1)); if(i>=8) break;
        TRY(rt8_work_reserve(s,1)); REQUIRE(s,1,h->magic[i]==magic[i],ABI,MAGIC);
    }
    TRY(header_field(s,1)); REQUIRE(s,1,h->abi_revision==RT8_BINDING_ABI_REVISION,ABI,REVISION);
    TRY(header_field(s,2)); REQUIRE(s,1,h->purpose==RT8_BINDING_PURPOSE_STATIC_REAL_BODIES,ABI,PURPOSE);
    TRY(header_field(s,3)); REQUIRE(s,1,h->binding_bytes==v->program.binding_bytes,ABI,LENGTH);
    TRY(header_field(s,4)); REQUIRE(s,1,h->binding_alignment!=0,ALIGNMENT,ALIGNMENT);
    TRY(header_field(s,5)); REQUIRE(s,1,h->packet_bytes==v->program.packet_bytes,BINDING,LENGTH);
    TRY(header_field(s,6)); REQUIRE(s,1,h->packet_alignment!=0,ALIGNMENT,ALIGNMENT);
    TRY(header_field(s,8)); REQUIRE(s,1,h->code_count<=2048,BINDING,COUNT);
    TRY(header_field(s,10)); REQUIRE(s,1,h->label_count<=RT8_MAX_LABELS,BINDING,COUNT);
    TRY(header_field(s,12)); REQUIRE(s,1,h->label_bytes<=RT8_MAX_LABEL_BYTES,BINDING,LENGTH);
    return S(OK);
}
static uint32_t check_expected(const Rt8BindingHeader *h,const Ir8PacketExpectedBindings *e,Rt8ReadState *s) {
    uint32_t i,j; TRY(header_field(s,14));
    for(i=0;;++i) {
        TRY(rt8_work_reserve(s,1)); if(i>=5) break;
        TRY(rt8_work_reserve(s,1));
        for(j=0;;++j) {
            TRY(rt8_work_reserve(s,1)); if(j>=32) break;
            TRY(rt8_work_reserve(s,1));
            REQUIRE(s,1,h->expected.digests[i].bytes[j]==e->digests[i].bytes[j],BINDING,BINDING_MISMATCH);
        }
    }
    return S(OK);
}
static uint32_t member(const Rt8ProgramView *v,uint32_t offset,uint32_t count,
                        size_t size,size_t alignment,uint32_t *cursor,uint32_t *bytes,Rt8ReadState *s) {
    uint32_t n,end;
    TRY(mul32(s,count,(uint32_t)size,&n));
    TRY(rt8_work_reserve(s,1));
    if(count==0) {
        REQUIRE(s,1,offset==N,BINDING,EXTRA); *bytes=0; return S(OK);
    }
    REQUIRE(s,1,offset!=N,BINDING,MISSING);
    REQUIRE(s,1,offset>=*cursor,BINDING,OVERLAP);
    REQUIRE(s,2,v->binding_header.binding_alignment%alignment==0,ALIGNMENT,ALIGNMENT);
    TRY(extent(s,v->program.binding_bytes,offset,n));
    TRY(absolute_alignment(s,v->program.binding,v->program.binding_bytes,offset,alignment));
    TRY(add32(s,offset,n,&end)); *cursor=end; *bytes=n; return S(OK);
}
static uint32_t check_layout(Rt8ProgramView *v,Rt8BindingReport *r,Rt8ReadState *s) {
    uint32_t i,cursor=(uint32_t)sizeof(Rt8BindingHeader),bytes;
    Ir8PacketObjectDirectoryEntry d; Ir8PacketTypedHeader typed;
    TRY(header_field(s,4));
    REQUIRE(s,2,v->binding_header.binding_alignment%_Alignof(Rt8BindingHeader)==0,ALIGNMENT,ALIGNMENT);
    REQUIRE(s,2,v->program.binding_bytes%v->binding_header.binding_alignment==0,ALIGNMENT,ALIGNMENT);
    TRY(absolute_alignment(s,v->program.binding,v->program.binding_bytes,0,v->binding_header.binding_alignment));
    TRY(header_field(s,6));
    TRY(copy_root(s,v->program.packet,v->program.packet_bytes,0,sizeof(v->packet_header),&v->packet_header));
    REQUIRE(s,1,v->binding_header.packet_alignment==v->packet_header.packet_alignment,BINDING,ALIGNMENT);
    REQUIRE(s,1,v->packet_header.packet_alignment!=0,ALIGNMENT,ALIGNMENT);
    REQUIRE(s,2,v->packet_header.packet_alignment%_Alignof(Ir8PacketProgramHeader)==0,ALIGNMENT,ALIGNMENT);
    REQUIRE(s,2,v->program.packet_bytes%v->packet_header.packet_alignment==0,ALIGNMENT,ALIGNMENT);
    TRY(absolute_alignment(s,v->program.packet,v->program.packet_bytes,0,v->packet_header.packet_alignment));
    REQUIRE(s,1,v->packet_header.directory_count<=IR8_PACKET_MAX_DIRECTORY,BINDING,COUNT);
    /* Even unused nonempty packet members must satisfy absolute alignment. */
    for(i=0;;++i) {
        TRY(rt8_work_reserve(s,1)); if(i>=v->packet_header.directory_count) break;
        TRY(rt8_work_reserve(s,1));
        location(s,RT8_REGION_PACKET,RT8_DOMAIN_KIND_NONE,N,i,N,N);
        TRY(directory(v,i,&d,s));
        TRY(rt8_work_reserve(s,1));
        if(d.count!=0) REQUIRE(s,2,v->packet_header.packet_alignment%d.element_alignment==0,ALIGNMENT,ALIGNMENT);
    }
    location(s,RT8_REGION_PACKET,RT8_DOMAIN_KIND_NONE,N,v->packet_header.typed_header_object,0,N);
    TRY(directory(v,v->packet_header.typed_header_object,&d,s));
    REQUIRE(s,1,d.kind==IR8_PACKET_OBJECT_KIND_HEADER,REFERENCE,DOMAIN);
    REQUIRE(s,1,d.domain_or_subkind==IR8_PACKET_HEADER_SUBKIND_TYPED,REFERENCE,DOMAIN);
    REQUIRE(s,1,d.owner==N,REFERENCE,APPLICABILITY);
    REQUIRE(s,1,d.secondary_owner==N,REFERENCE,APPLICABILITY);
    REQUIRE(s,1,d.count==1,REFERENCE,COUNT);
    TRY(rt8_view_object_read(v,v->packet_header.typed_header_object,IR8_PACKET_ELEMENT_TYPED_HEADER,
                            0,&typed,sizeof(typed),s));
    TRY(rt8_work_reserve(s,sizeof(typed))); v->typed_header=typed;
    location(s,RT8_REGION_PACKET,RT8_DOMAIN_KIND_NONE,N,v->packet_header.string_pool_object,N,N);
    TRY(directory(v,v->packet_header.string_pool_object,&d,s));
    TRY(rt8_work_reserve(s,sizeof(d))); v->string_pool=d;
    REQUIRE(s,1,v->string_pool.kind==IR8_PACKET_OBJECT_KIND_STRING_POOL,REFERENCE,DOMAIN);
    REQUIRE(s,1,v->string_pool.element_type==IR8_PACKET_ELEMENT_UTF8_BYTE,REFERENCE,DOMAIN);
    TRY(header_field(s,7));
    TRY(member(v,v->binding_header.code_offset,v->binding_header.code_count,sizeof(Rt8Code),_Alignof(Rt8Code),&cursor,&bytes,s));
    r->code_bytes=bytes;
    TRY(header_field(s,9));
    TRY(member(v,v->binding_header.label_index_offset,v->binding_header.label_count,sizeof(uint32_t),_Alignof(uint32_t),&cursor,&bytes,s));
    r->label_index_bytes=bytes;
    TRY(header_field(s,11));
    TRY(member(v,v->binding_header.label_bytes_offset,v->binding_header.label_bytes,sizeof(unsigned char),_Alignof(unsigned char),&cursor,&bytes,s));
    r->label_bytes=bytes;
    TRY(header_field(s,10));
    TRY(rt8_work_reserve(s,1));
    if(v->binding_header.label_count==0) REQUIRE(s,1,v->binding_header.label_bytes==0,BINDING,EXTRA);
    else REQUIRE(s,1,v->binding_header.label_bytes!=0,BINDING,MISSING);
    r->header_bytes=(uint32_t)sizeof(Rt8BindingHeader);
    return S(OK);
}
static uint32_t check_codes(const Rt8ProgramView *v,Rt8ReadState *s) {
    uint32_t i,j;
    TRY(header_field(s,8));
    REQUIRE(s,1,v->binding_header.code_count==v->typed_header.table[4].count,BINDING,COUNT);
    REQUIRE(s,1,v->binding_header.code_count==v->typed_header.descriptor[1].count,BINDING,COUNT);
    TRY(header_field(s,15)); REQUIRE(s,1,v->binding_header.entry!=NULL,UNBOUND,NULL_CALLBACK);
    for(i=0;;++i) {
        Rt8Code code;
        TRY(rt8_work_reserve(s,1)); if(i>=v->binding_header.code_count) break;
        TRY(rt8_work_reserve(s,1)); TRY(rt8_view_code_read(v,i,&code,s));
        for(j=0;;++j) {
            Rt8Code previous;
            TRY(rt8_work_reserve(s,1)); if(j>=i) break;
            TRY(rt8_work_reserve(s,1)); TRY(rt8_view_code_read(v,j,&previous,s));
            location(s,RT8_REGION_BINDING,RT8_DOMAIN_KIND_NATIVE_CODE,0,N,i,1);
            REQUIRE(s,1,code.body!=previous.body,BINDING,DUPLICATE);
        }
    }
    return S(OK);
}
static uint32_t census(const Rt8ProgramView *v,Rt8BindingReport *r,Rt8ReadState *s) {
    uint32_t total,members,packet_total;
    TRY(add32(s,(uint32_t)v->program.packet_bytes,(uint32_t)v->program.binding_bytes,&total));
    REQUIRE(s,1,total<=RT8_MAX_STATIC_BYTES,STATIC_LIMIT,STATIC_BUDGET);
    TRY(header_field(s,13));
    REQUIRE(s,1,total==v->binding_header.runtime_total_static_bytes,BINDING,EQUATION);
    TRY(add32(s,r->header_bytes,r->code_bytes,&members));
    TRY(add32(s,members,r->label_index_bytes,&members)); TRY(add32(s,members,r->label_bytes,&members));
    REQUIRE(s,1,members<=v->program.binding_bytes,BINDING,LENGTH);
    TRY(add32(s,r->packet.member_bytes_sum,r->packet.padding_bytes,&packet_total));
    REQUIRE(s,1,packet_total==v->program.packet_bytes,BINDING,EQUATION);
    TRY(rt8_work_reserve(s,1)); r->padding_bytes=(uint32_t)v->program.binding_bytes-members;
    r->runtime_total_static_bytes=total; return S(OK);
}
static uint32_t validate_all(const Rt8Program *program,const Ir8PacketExpectedBindings *expected,
                             Rt8BindingWorkspace *workspace,Rt8ProgramView *v,
                             Rt8BindingReport *r,Rt8ReadState *s) {
    Ir8PacketExpectedBindings e; uint32_t packet_status;
    uintptr_t packet_start,binding_start,packet_end,binding_end;
    /* Typed wrapper/expected storage is a valid, disjoint caller precondition. */
    TRY(rt8_work_reserve(s,sizeof(v->program))); memcpy(&v->program,program,sizeof(v->program));
    TRY(rt8_work_reserve(s,sizeof(e))); memcpy(&e,expected,sizeof(e));
    if(!v->program.packet || !v->program.binding) return fail(s,S(ARGUMENT),D(NULL_ARGUMENT));
    REQUIRE(s,1,v->program.packet_bytes>=sizeof(Ir8PacketProgramHeader),SIZE_LIMIT,LENGTH);
    REQUIRE(s,1,v->program.binding_bytes>=sizeof(Rt8BindingHeader),SIZE_LIMIT,LENGTH);
    TRY(root_range(s,v->program.packet,v->program.packet_bytes));
    TRY(root_range(s,v->program.binding,v->program.binding_bytes));
    TRY(rt8_work_reserve(s,4));
    packet_start=(uintptr_t)v->program.packet; binding_start=(uintptr_t)v->program.binding;
    packet_end=packet_start+(uintptr_t)v->program.packet_bytes;
    binding_end=binding_start+(uintptr_t)v->program.binding_bytes;
    REQUIRE(s,3,packet_end<=binding_start || binding_end<=packet_start,ARGUMENT,OVERLAP);
    r->packet_bytes=(uint32_t)v->program.packet_bytes; r->binding_bytes=(uint32_t)v->program.binding_bytes;
    phase(s,P(NATIVE_HEADER)); TRY(check_native_header(v,s));
    r->code_count=v->binding_header.code_count; r->label_count=v->binding_header.label_count;
    phase(s,P(EXPECTED_BINDINGS)); TRY(check_expected(&v->binding_header,&e,s));
    phase(s,P(PACKET)); r->packet_checked=1;
    packet_status=ir8_packet_validate(v->program.packet,v->program.packet_bytes,&e,workspace,&r->packet);
    /* The packet's separate bounded work is not charged a second time here. */
    REQUIRE(s,1,packet_status==r->packet.status,INTERNAL,INTERNAL_INVARIANT);
    TRY(rt8_work_reserve(s,1));
    if(packet_status!=IR8_PACKET_NATIVE_STATUS_OK) {
        location(s,RT8_REGION_PACKET,RT8_DOMAIN_KIND_NONE,r->packet.domain,
                 r->packet.object,r->packet.row,r->packet.field);
        return fail(s,S(PACKET),D(EQUATION));
    }
    REQUIRE(s,4,r->packet.graph_executed==0 && r->packet.source_admitted==0 &&
                 r->packet.runtime_admitted==0 && r->packet.runtime_guards_executed==0,INTERNAL,INTERNAL_INVARIANT);
    phase(s,P(NATIVE_LAYOUT)); TRY(check_layout(v,r,s));
    phase(s,P(CODE_BINDINGS)); TRY(check_codes(v,s));
    phase(s,P(LABELS)); TRY(check_labels(v,s));
    phase(s,P(STATIC_CENSUS)); TRY(census(v,r,s));
    phase(s,P(FINAL)); return S(OK);
}
static void report_diagnostic(Rt8BindingReport *r,const Rt8Diagnostic *d) {
    r->status=d->status; r->phase=d->phase; r->detail=d->detail;
    r->region=d->region; r->domain_kind=d->domain_kind; r->domain=d->domain;
    r->object=d->object; r->row=d->row; r->field=d->field; r->guard_index=d->guard_index;
}
uint32_t rt8_binding_prepare(const Rt8Program *program,const Ir8PacketExpectedBindings *expected,
                             Rt8BindingWorkspace *workspace,Rt8ProgramView *out,Rt8BindingReport *report) {
    Rt8ProgramView v={0}; Rt8Work work={0,0,RT8_MAX_BINDING_WORK};
    Rt8Diagnostic diagnostic={0}; Rt8ReadState state={&work,&diagnostic}; uint32_t status;
    /* Fixed result initialization must remain possible without a work budget. */
    if(out) *out=(Rt8ProgramView){0};
    if(!report) return S(ARGUMENT);
    *report=(Rt8BindingReport){0}; report->status=S(INTERNAL);
    report->work_limit=RT8_MAX_BINDING_WORK;
    report->workspace_bytes=(uint32_t)sizeof(Rt8BindingWorkspace);
    phase(&state,P(ARGUMENTS)); report_diagnostic(report,&diagnostic); report->status=S(INTERNAL);
    if(!program || !expected || !workspace || !out) {
        status=fail(&state,S(ARGUMENT),D(NULL_ARGUMENT));
    } else {
        status=validate_all(program,expected,workspace,&v,report,&state);
        if(status==S(OK)) {
            status=rt8_work_reserve(&state,sizeof(v));
            if(status==S(OK)) { *out=v; report->binding_validated=1; }
        }
    }
    report_diagnostic(report,&diagnostic); report->status=status;
    report->work_used=work.used;
    /* Nothing here grants runtime/source/graph/guard authority. */
    return status;
}
uint32_t rt8_binding_validate(const Rt8Program *program,const Ir8PacketExpectedBindings *expected,
                              Rt8BindingWorkspace *workspace,Rt8BindingReport *report) {
    Rt8ProgramView view;
    return rt8_binding_prepare(program,expected,workspace,&view,report);
}
