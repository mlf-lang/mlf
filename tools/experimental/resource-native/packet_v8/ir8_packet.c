/* Stage04 packet structural checking only. No allocator, callbacks or Rt ABI.
 * Every packet read is byte based and checked before a charged memcpy. */
#include "ir8_packet.h"
#include <string.h>

#define N IR8_PACKET_NULL
#define S(x) IR8_PACKET_NATIVE_STATUS_##x
#define P(x) IR8_PACKET_NATIVE_PHASE_##x
#define D(x) IR8_PACKET_NATIVE_DETAIL_##x
#define TRY(x) do { if (!(x)) return 0; } while (0)
#define REQUIRE_N(x,s,d,n) do { TRY(charge(c,(n))); if (!(x)) return bad(c,S(s),D(d)); } while (0)
#define REQUIRE(x,s,d) REQUIRE_N(x,s,d,1)
#define EQ(a,b,s) REQUIRE((a)==(b),s,EQUATION)

typedef struct Check {
    const unsigned char *root;
    size_t bytes;
    Ir8PacketWorkspace *w;
    Ir8PacketReport *r;
    Ir8PacketProgramHeader h;
    Ir8PacketTypedHeader t;
    Ir8PacketObjectDirectoryEntry pool;
} Check;

static int bad(Check *c, uint32_t status, uint32_t detail) {
    c->r->status=status; c->r->detail=detail; return 0;
}
static int charge(Check *c, uint64_t units) {
    if (units>IR8_PACKET_MAX_WORK-c->r->work_used)
        { return bad(c,S(WORK_LIMIT),D(WORK_EXHAUSTED)); }
    c->r->work_used+=units; return 1;
}
static void at(Check *c,uint32_t domain,uint32_t object,uint32_t row,uint32_t field) {
    c->r->domain=domain; c->r->object=object;
    c->r->row=row; c->r->field=field;
}
static void phase(Check *c,uint32_t p) { c->r->phase=p; at(c,N,N,N,N); }
static int copy(Check *c,uint32_t off,size_t n,void *out) {
    if ((size_t)off>c->bytes || n>c->bytes-(size_t)off)
        { return bad(c,S(DIRECTORY),D(OFFSET)); }
    TRY(charge(c,n)); memcpy(out,c->root+(size_t)off,n); return 1;
}
static int extent(Check *c,uint32_t count,uint32_t size,uint32_t *bytes) {
    if (size && count>UINT32_MAX/size) { return bad(c,S(DIRECTORY),D(OVERFLOW)); }
    *bytes=count*size; return 1;
}
static int layout(uint32_t element,size_t *bytes,size_t *alignment) {
    switch(element) {
    case 1: *bytes=sizeof(Ir8PacketType); *alignment=_Alignof(Ir8PacketType); return 1;
    case 2: *bytes=sizeof(Ir8PacketCallableContract); *alignment=_Alignof(Ir8PacketCallableContract); return 1;
    case 3: *bytes=sizeof(Ir8PacketScheme); *alignment=_Alignof(Ir8PacketScheme); return 1;
    case 4: *bytes=sizeof(Ir8PacketEnv); *alignment=_Alignof(Ir8PacketEnv); return 1;
    case 5: *bytes=sizeof(Ir8PacketCodeTyping); *alignment=_Alignof(Ir8PacketCodeTyping); return 1;
    case 6: *bytes=sizeof(Ir8PacketCodeExecution); *alignment=_Alignof(Ir8PacketCodeExecution); return 1;
    case 7: *bytes=sizeof(Ir8PacketShapeBinding); *alignment=_Alignof(Ir8PacketShapeBinding); return 1;
    case 8: *bytes=sizeof(Ir8PacketShapeTyping); *alignment=_Alignof(Ir8PacketShapeTyping); return 1;
    case 9: *bytes=sizeof(Ir8PacketRepresentation); *alignment=_Alignof(Ir8PacketRepresentation); return 1;
    case 10: *bytes=sizeof(Ir8PacketNominalField); *alignment=_Alignof(Ir8PacketNominalField); return 1;
    case 11: *bytes=sizeof(Ir8PacketFamilyTyping); *alignment=_Alignof(Ir8PacketFamilyTyping); return 1;
    case 12: *bytes=sizeof(Ir8PacketTypeResolution); *alignment=_Alignof(Ir8PacketTypeResolution); return 1;
    case 13: *bytes=sizeof(Ir8PacketRepresentationResolution); *alignment=_Alignof(Ir8PacketRepresentationResolution); return 1;
    case 14: *bytes=sizeof(Ir8PacketSite); *alignment=_Alignof(Ir8PacketSite); return 1;
    case 15: *bytes=sizeof(Ir8PacketSiteExecution); *alignment=_Alignof(Ir8PacketSiteExecution); return 1;
    case 16: *bytes=sizeof(Ir8PacketSlot); *alignment=_Alignof(Ir8PacketSlot); return 1;
    case 17: *bytes=sizeof(Ir8PacketAccess); *alignment=_Alignof(Ir8PacketAccess); return 1;
    case 18: *bytes=sizeof(Ir8PacketIntro); *alignment=_Alignof(Ir8PacketIntro); return 1;
    case 19: *bytes=sizeof(Ir8PacketUse); *alignment=_Alignof(Ir8PacketUse); return 1;
    case 20: *bytes=sizeof(Ir8PacketTransport); *alignment=_Alignof(Ir8PacketTransport); return 1;
    case 21: *bytes=sizeof(Ir8PacketRegisteredRowRef); *alignment=_Alignof(Ir8PacketRegisteredRowRef); return 1;
    case 22: *bytes=sizeof(Ir8PacketRegisteredDescriptorRef); *alignment=_Alignof(Ir8PacketRegisteredDescriptorRef); return 1;
    case 23: *bytes=sizeof(Ir8PacketTypeRef); *alignment=_Alignof(Ir8PacketTypeRef); return 1;
    case 24: *bytes=sizeof(Ir8PacketCaptureTyping); *alignment=_Alignof(Ir8PacketCaptureTyping); return 1;
    case 25: *bytes=sizeof(Ir8PacketResolvedCapture); *alignment=_Alignof(Ir8PacketResolvedCapture); return 1;
    case 26: *bytes=sizeof(Ir8PacketSiteRef); *alignment=_Alignof(Ir8PacketSiteRef); return 1;
    case 27: *bytes=sizeof(Ir8PacketPathRef); *alignment=_Alignof(Ir8PacketPathRef); return 1;
    case 28: *bytes=sizeof(Ir8PacketVariantTyping); *alignment=_Alignof(Ir8PacketVariantTyping); return 1;
    case 29: *bytes=sizeof(Ir8PacketVariantRef); *alignment=_Alignof(Ir8PacketVariantRef); return 1;
    case 30: *bytes=sizeof(Ir8PacketNominalFieldRef); *alignment=_Alignof(Ir8PacketNominalFieldRef); return 1;
    case 31: *bytes=sizeof(Ir8PacketShapeSpec); *alignment=_Alignof(Ir8PacketShapeSpec); return 1;
    case 32: *bytes=sizeof(Ir8PacketCodeSpec); *alignment=_Alignof(Ir8PacketCodeSpec); return 1;
    case 33: *bytes=sizeof(Ir8PacketFamilySpec); *alignment=_Alignof(Ir8PacketFamilySpec); return 1;
    case 34: *bytes=sizeof(Ir8PacketVariantSpec); *alignment=_Alignof(Ir8PacketVariantSpec); return 1;
    case 35: *bytes=sizeof(Ir8PacketFieldSpec); *alignment=_Alignof(Ir8PacketFieldSpec); return 1;
    case 36: *bytes=sizeof(unsigned char); *alignment=_Alignof(unsigned char); return 1;
    case 37: *bytes=sizeof(Ir8PacketProgramHeader); *alignment=_Alignof(Ir8PacketProgramHeader); return 1;
    case 38: *bytes=sizeof(Ir8PacketTypedHeader); *alignment=_Alignof(Ir8PacketTypedHeader); return 1;
    case 39: *bytes=sizeof(Ir8PacketDigest32); *alignment=_Alignof(Ir8PacketDigest32); return 1;
    case 40: *bytes=sizeof(Ir8PacketObjectDirectoryEntry); *alignment=_Alignof(Ir8PacketObjectDirectoryEntry); return 1;
    default: return 0;
    }
}
static int directory(Check *c,uint32_t id,Ir8PacketObjectDirectoryEntry *out) {
    uint32_t delta;
    if (id>=c->h.directory_count) { return bad(c,S(DIRECTORY),D(REFERENCE)); }
    TRY(extent(c,id,(uint32_t)sizeof(*out),&delta));
    if (delta>UINT32_MAX-c->h.directory_offset) { return bad(c,S(DIRECTORY),D(OVERFLOW)); }
    TRY(charge(c,1)); return copy(c,c->h.directory_offset+delta,sizeof(*out),out);
}
static int object_read(Check *c,uint32_t object,uint32_t element,uint32_t row,void *out) {
    Ir8PacketObjectDirectoryEntry d; size_t bytes,align; uint32_t delta;
    TRY(directory(c,object,&d));
    if (!layout(element,&bytes,&align)) { return bad(c,S(INTERNAL),D(TAG)); }
    REQUIRE_N(d.element_type==element && d.element_bytes==bytes && d.element_alignment==align,DIRECTORY,TAG,3);
    REQUIRE_N(d.offset!=N && row<d.count && d.offset%align==0,DIRECTORY,REFERENCE,3);
    TRY(extent(c,row,d.element_bytes,&delta));
    REQUIRE_N(delta<=d.object_bytes && bytes<=d.object_bytes-delta,DIRECTORY,OFFSET,2);
    if (delta>UINT32_MAX-d.offset) { return bad(c,S(DIRECTORY),D(OVERFLOW)); }
    TRY(charge(c,1)); return copy(c,d.offset+delta,bytes,out);
}
static int row(Check *c,uint32_t domain,uint32_t id,void *out) {
    Ir8PacketObjectDirectoryEntry d;
    if (domain<1 || domain>20) { return bad(c,S(INTERNAL),D(TAG)); }
    REQUIRE_N(id<c->t.table[domain-1].count,MEMBERSHIP,REFERENCE,1);
    TRY(directory(c,c->t.table[domain-1].object,&d));
    REQUIRE_N(d.kind==1 && d.domain_or_subkind==domain && d.owner==N && d.secondary_owner==N,MEMBERSHIP,OWNER,4);
    return object_read(c,c->t.table[domain-1].object,domain,id,out);
}
static uint32_t descriptor_element(uint32_t d) {
    return d==1?31:d==2?32:d==3?33:d==4?34:(d==5||d==6)?35:0;
}
static int descriptor(Check *c,uint32_t domain,uint32_t id,void *out) {
    Ir8PacketObjectDirectoryEntry d;
    if (domain<1 || domain>6) { return bad(c,S(INTERNAL),D(TAG)); }
    REQUIRE_N(id<c->t.descriptor[domain-1].count,MEMBERSHIP,REFERENCE,1);
    TRY(directory(c,c->t.descriptor[domain-1].object,&d));
    REQUIRE_N(d.kind==3 && d.domain_or_subkind==domain && d.owner==N && d.secondary_owner==N,MEMBERSHIP,OWNER,4);
    return object_read(c,c->t.descriptor[domain-1].object,descriptor_element(domain),id,out);
}
static const char *table_name(uint32_t d) {
    switch(d) {
    case 1:return "types"; case 2:return "callable_contracts"; case 3:return "schemes";
    case 4:return "environments"; case 5:return "codes"; case 6:return "code_executions";
    case 7:return "shapes"; case 8:return "shape_typing"; case 9:return "representations";
    case 10:return "nominal_fields"; case 11:return "families"; case 12:return "type_resolutions";
    case 13:return "representation_resolutions"; case 14:return "sites"; case 15:return "site_executions";
    case 16:return "slots"; case 17:return "accesses"; case 18:return "introductions";
    case 19:return "uses"; case 20:return "transports"; default:return 0;
    }
}
static const char *descriptor_name(uint32_t d) {
    switch(d) { case 1:return "shapes";case 2:return "codes";case 3:return "families";
    case 4:return "variants";case 5:return "nominal-fields";case 6:return "code-capture-fields";default:return 0; }
}
static const char *vector_name(uint32_t d) {
    switch(d) {case 1:return "env";case 2:return "code-captures";case 3:return "execution-captures";
    case 4:return "intro-sites";case 5:return "use-occurrences";case 6:return "family-variants";
    case 7:return "family-variant-pointers";case 8:return "variant-fields";case 9:return "data-fields";default:return 0;}
}
static uint32_t vector_element(uint32_t d) {
    switch(d) {case 1:return 23;case 2:return 24;case 3:return 25;case 4:return 26;
    case 5:return 27;case 6:return 28;case 7:return 29;case 8:case 9:return 30;default:return 0;}
}
static int key_text(Check *c,unsigned char *b,uint32_t *n,const char *s) {
    uint32_t i=0; if (!s) { return bad(c,S(DIRECTORY),D(TAG)); }
    while(s[i]) { TRY(charge(c,1)); if (*n>=127) { return bad(c,S(INTERNAL),D(LIMIT)); } b[(*n)++]=(unsigned char)s[i++]; }
    b[*n]=0; return 1;
}
static int key_number(Check *c,unsigned char *b,uint32_t *n,uint32_t value) {
    uint32_t scale=1;
    while(value/scale>=10) { scale*=10; }
    do { TRY(charge(c,1)); if(*n>=127){ return bad(c,S(INTERNAL),D(LIMIT)); }
        b[(*n)++]=(unsigned char)('0'+value/scale); value%=scale; scale/=10;
    } while(scale); b[*n]=0;return 1;
}
/* Category byte preserves Stage03 inventory kind ordering; suffix is exact key. */
static int object_key(Check *c,const Ir8PacketObjectDirectoryEntry *d,unsigned char *b) {
    uint32_t n=1,k=d->kind,sub=d->domain_or_subkind;
    REQUIRE_N(k>=1 && k<=8,DIRECTORY,TAG,2);
    REQUIRE_N(k==5 || (d->owner==N && d->secondary_owner==N),DIRECTORY,OWNER,3);
    b[0]=(unsigned char)(k==1?1:k==5?2:k==3?3:(k==2||k==4)?4:k==6?5:k==7?6:7); b[1]=0;
    if(k==1||k==2) { TRY(key_text(c,b,&n,k==1?"table/":"index/table/")); TRY(key_text(c,b,&n,table_name(sub))); }
    else { if(k==3||k==4) { TRY(key_text(c,b,&n,k==3?"descriptor/":"index/descriptor/")); TRY(key_text(c,b,&n,descriptor_name(sub))); }
    else { if(k==5) {
        REQUIRE_N(d->owner!=N && ((sub==8)==(d->secondary_owner!=N)),DIRECTORY,OWNER,4);
        TRY(key_text(c,b,&n,"vector/"));TRY(key_text(c,b,&n,vector_name(sub)));TRY(key_text(c,b,&n,"/"));TRY(key_number(c,b,&n,d->owner));
        if(sub==8){TRY(key_text(c,b,&n,"/"));TRY(key_number(c,b,&n,d->secondary_owner));}
    } else { if(k==6) {REQUIRE(sub==1,DIRECTORY,TAG);TRY(key_text(c,b,&n,"pool/strings"));}
    else { if(k==7) {TRY(key_text(c,b,&n,sub==1?"header/program":sub==2?"header/typed":sub==3?"header/bindings":0));}
    else {REQUIRE(sub==1,DIRECTORY,TAG);TRY(key_text(c,b,&n,"packet/object-directory"));} } } } }
    return 1;
}
static int key_cmp(Check *c,const unsigned char *a,const unsigned char *b,int *result) {
    uint32_t i=0;
    do {TRY(charge(c,3));if(a[i]!=b[i]){*result=a[i]<b[i]?-1:1;return 1;} if(!a[i]){ break; }++i;}while(i<128);
    *result=0;return 1;
}
static int find_object(Check *c,uint32_t kind,uint32_t sub,uint32_t owner,uint32_t secondary,uint32_t *id) {
    Ir8PacketObjectDirectoryEntry target={N,kind,sub,owner,secondary,0,0,0,0,0,0}, d;
    uint32_t lo=3,hi=c->h.directory_count-1; int cmp;
    TRY(object_key(c,&target,c->w->canonical_key[0]));
    while(lo<hi) {uint32_t mid=lo+(hi-lo)/2;TRY(directory(c,mid,&d));TRY(object_key(c,&d,c->w->canonical_key[1]));
        TRY(key_cmp(c,c->w->canonical_key[1],c->w->canonical_key[0],&cmp));if(cmp<0){ lo=mid+1; }else { hi=mid; }}
    REQUIRE_N(lo<c->h.directory_count-1,DIRECTORY,MISSING,1);TRY(directory(c,lo,&d));
    REQUIRE_N(d.kind==kind&&d.domain_or_subkind==sub&&d.owner==owner&&d.secondary_owner==secondary,DIRECTORY,MISSING,4);
    *id=lo;return 1;
}
static int span(Check *c,Ir8PacketSpan s,uint32_t kind,uint32_t sub,uint32_t owner,uint32_t secondary,uint32_t element) {
    uint32_t id;Ir8PacketObjectDirectoryEntry d;
    TRY(find_object(c,kind,sub,owner,secondary,&id));TRY(directory(c,id,&d));
    REQUIRE_N(d.element_type==element && d.count==s.count,MEMBERSHIP,COUNT,2);
    REQUIRE_N((s.count==0&&s.object==N)||(s.count!=0&&s.object==id),MEMBERSHIP,NULL_DOMAIN,4);
    TRY(charge(c,1));c->w->directory_seen[id]=1;return 1;
}
static int vector(Check *c,Ir8PacketSpan s,uint32_t sub,uint32_t owner,uint32_t secondary) {
    return span(c,s,5,sub,owner,secondary,vector_element(sub));
}
static int vector_read(Check *c,Ir8PacketSpan s,uint32_t elem,uint32_t i,void *out) {
    REQUIRE_N(i<s.count && s.object!=N,MEMBERSHIP,REFERENCE,2);return object_read(c,s.object,elem,i,out);
}
static int ref(Check *c,uint32_t id,uint32_t dom,int nullable) {
    REQUIRE_N((nullable&&id==N)||(dom>=1&&dom<=20&&id<c->t.table[dom-1].count),SCHEMA,REFERENCE,4);return 1;
}
static int enum_value(Check *c,uint32_t v,uint32_t min,uint32_t max,int nullable) {
    REQUIRE_N((nullable&&v==N)||(v>=min&&v<=max),SCHEMA,TAG,3);return 1;
}
static int pool_byte(Check *c,uint32_t off,unsigned char *v) {
    REQUIRE_N(off<c->pool.count,SCHEMA,STRING_BOUNDARY,1);
    if(off>UINT32_MAX-c->pool.offset){ return bad(c,S(DIRECTORY),D(OVERFLOW)); }
    TRY(charge(c,1));return copy(c,c->pool.offset+off,1,v);
}
static int string_ref(Check *c,uint32_t off,int nullable) {
    unsigned char v;
    if(nullable&&off==N){ return 1; }
    REQUIRE_N(off<c->pool.count,SCHEMA,STRING_BOUNDARY,1);
    if(off){TRY(pool_byte(c,off-1,&v));REQUIRE(v==0,SCHEMA,STRING_BOUNDARY);}return 1;
}
static int string_cmp(Check *c,uint32_t a,uint32_t b,int *cmp) {
    unsigned char x,y;TRY(string_ref(c,a,0));TRY(string_ref(c,b,0));
    for(;;){TRY(pool_byte(c,a++,&x));TRY(pool_byte(c,b++,&y));TRY(charge(c,1));
        if(x!=y){*cmp=x<y?-1:1;return 1;}if(!x){*cmp=0;return 1;}}
}
static int string_is(Check *c,uint32_t a,const char *s,int *yes) {
    unsigned char x;uint32_t i=0;TRY(string_ref(c,a,0));
    for(;;){TRY(pool_byte(c,a++,&x));TRY(charge(c,2));if(x!=(unsigned char)s[i]){*yes=0;return 1;}
        if(!x){*yes=1;return 1;}++i;}
}
static int check_directory(Check *c) {
    uint32_t i,bytes,end=0,sum=0,members=0,expected_source;int cmp;
    Ir8PacketObjectDirectoryEntry d,previous;
    REQUIRE_N(c->h.directory_count>=57 && c->h.directory_count<=IR8_PACKET_MAX_DIRECTORY,COUNT_LIMIT,LIMIT,2);
    REQUIRE(c->h.packet_alignment!=0,DIRECTORY,ALIGNMENT);
    TRY(extent(c,c->h.directory_count,(uint32_t)sizeof(d),&bytes));
    REQUIRE_N(c->h.directory_offset%_Alignof(Ir8PacketObjectDirectoryEntry)==0,DIRECTORY,ALIGNMENT,1);
    REQUIRE_N(c->h.directory_offset<=c->bytes && bytes<=c->bytes-c->h.directory_offset,DIRECTORY,OFFSET,2);
    for(i=0;i<c->h.directory_count;++i) {
        size_t size,align;uint32_t elem=0;at(c,N,i,N,N);TRY(directory(c,i,&d));
        expected_source=i==0?c->h.directory_count-3:i==1?c->h.directory_count-2:i==2?c->h.directory_count-4:i==c->h.directory_count-1?N:i-3;
        REQUIRE(d.source_inventory_id==expected_source,DIRECTORY,ORDER);
        TRY(object_key(c,&d,c->w->canonical_key[0]));
        if(i>=4 && i<c->h.directory_count-1) {
            TRY(object_key(c,&previous,c->w->canonical_key[1]));
            TRY(key_cmp(c,c->w->canonical_key[1],c->w->canonical_key[0],&cmp));
            REQUIRE(cmp<0,DIRECTORY,ORDER);
        }
        if(d.kind==1) { elem=d.domain_or_subkind; }
        else { if(d.kind==2){ elem=21; }
        else { if(d.kind==3){ elem=descriptor_element(d.domain_or_subkind); }
        else { if(d.kind==4){ elem=22; }
        else { if(d.kind==5){ elem=vector_element(d.domain_or_subkind); }
        else { if(d.kind==6){ elem=36; }
        else { if(d.kind==7){ elem=d.domain_or_subkind==1?37:d.domain_or_subkind==2?38:39; }
        else { if(d.kind==8){ elem=40; } } } } } } } }
        REQUIRE(elem==d.element_type && layout(elem,&size,&align),DIRECTORY,TAG);
        REQUIRE_N(size<=UINT32_MAX && align<=UINT32_MAX,DIRECTORY,OVERFLOW,2);
        REQUIRE_N(d.element_bytes==size && d.element_alignment==align,DIRECTORY,ALIGNMENT,2);
        TRY(extent(c,d.count,d.element_bytes,&bytes));REQUIRE(d.object_bytes==bytes,DIRECTORY,COUNT);
        if(d.count==0) {REQUIRE_N(d.offset==N && d.object_bytes==0,DIRECTORY,NULL_DOMAIN,2);}
        else {
            REQUIRE_N(d.offset!=N && d.offset%align==0,DIRECTORY,ALIGNMENT,2);
            REQUIRE_N(d.offset<=c->bytes && bytes<=c->bytes-d.offset,DIRECTORY,OFFSET,2);
            REQUIRE(d.offset>=end,DIRECTORY,OVERLAP);
            end=d.offset+bytes;
            if(sum>UINT32_MAX-bytes){ return bad(c,S(DIRECTORY),D(OVERFLOW)); }
            sum+=bytes;++members;REQUIRE(c->h.packet_alignment%align==0,DIRECTORY,ALIGNMENT);
        }
        if(i<3){REQUIRE_N(d.kind==7 && d.domain_or_subkind==i+1 && d.count==(i==2?5u:1u),DIRECTORY,ORDER,4);
            if(i==0){ REQUIRE(d.offset==0,DIRECTORY,OFFSET); }c->w->directory_seen[i]=1;}
        else { if(i==c->h.directory_count-1){
            REQUIRE_N(d.kind==8 && d.domain_or_subkind==1 && d.count==c->h.directory_count && d.offset==c->h.directory_offset,DIRECTORY,ORDER,4);
            c->w->directory_seen[i]=1;
        }else { REQUIRE_N(d.kind!=7 && d.kind!=8,DIRECTORY,EXTRA,2); } }
        TRY(charge(c,sizeof(d)));memcpy(&previous,&d,sizeof(d));
    }
    REQUIRE(c->bytes%c->h.packet_alignment==0,DIRECTORY,ALIGNMENT);
    REQUIRE_N(sum<=c->bytes,DIRECTORY,OVERLAP,1);
    c->r->declared_packet_alignment=c->h.packet_alignment;c->r->member_bytes_sum=sum;
    c->r->padding_bytes=(uint32_t)c->bytes-sum;c->r->directory_entries=c->h.directory_count;c->r->member_objects=members;
    return 1;
}
static int check_pool(Check *c) {
    uint32_t pos=0,previous=N,start;int cmp;
    while(pos<c->pool.count) {
        unsigned char b,x;uint32_t scalar,need,min,j;start=pos;
        for(;;) {
            TRY(pool_byte(c,pos++,&b));if(!b){ break; }
            if(b<0x80){ continue; }
            if(b>=0xc2&&b<=0xdf){need=1;scalar=b&31u;min=0x80;}
            else { if(b>=0xe0&&b<=0xef){need=2;scalar=b&15u;min=0x800;}
            else { if(b>=0xf0&&b<=0xf4){need=3;scalar=b&7u;min=0x10000;}
            else { return bad(c,S(SCHEMA),D(UTF8)); } } }
            for(j=0;j<need;++j){TRY(pool_byte(c,pos++,&x));REQUIRE_N(x>=0x80&&x<=0xbf,SCHEMA,UTF8,2);scalar=(scalar<<6)|(x&63u);}
            REQUIRE_N(scalar>=min && scalar<=0x10ffff && !(scalar>=0xd800&&scalar<=0xdfff),SCHEMA,UTF8,4);
        }
        if(previous!=N){TRY(string_cmp(c,previous,start,&cmp));REQUIRE(cmp<0,SCHEMA,ORDER);}
        previous=start;
    }
    return 1;
}
static int check_memberships(Check *c,const Ir8PacketExpectedBindings *expected) {
    uint32_t d,i,object,total=0;Ir8PacketObjectDirectoryEntry pool;
    Ir8PacketRegisteredRowRef rr;Ir8PacketRegisteredDescriptorRef dr;Ir8PacketDigest32 digest;
    REQUIRE_N(c->h.typed_header_object==1 && c->h.bindings_object==2,MEMBERSHIP,REFERENCE,2);
    TRY(object_read(c,1,38,0,&c->t));
    for(d=1;d<=20;++d) {
        at(c,d,N,N,N);TRY(span(c,c->t.table[d-1],1,d,N,N,d));
        TRY(span(c,c->t.table_index[d-1],2,d,N,N,21));
        REQUIRE_N(c->t.table[d-1].count==c->t.table_index[d-1].count,MEMBERSHIP,COUNT,1);
        for(i=0;i<c->t.table_index[d-1].count;++i){at(c,d,c->t.table_index[d-1].object,i,N);
            TRY(object_read(c,c->t.table_index[d-1].object,21,i,&rr));REQUIRE_N(rr.domain==d&&rr.row==i,MEMBERSHIP,REFERENCE,2);}
    }
    for(d=1;d<=6;++d) {
        at(c,d,N,N,N);TRY(span(c,c->t.descriptor[d-1],3,d,N,N,descriptor_element(d)));
        TRY(span(c,c->t.descriptor_index[d-1],4,d,N,N,22));
        REQUIRE_N(c->t.descriptor[d-1].count==c->t.descriptor_index[d-1].count,MEMBERSHIP,COUNT,1);
        for(i=0;i<c->t.descriptor_index[d-1].count;++i){at(c,d,c->t.descriptor_index[d-1].object,i,N);
            TRY(object_read(c,c->t.descriptor_index[d-1].object,22,i,&dr));REQUIRE_N(dr.domain==d&&dr.row==i,MEMBERSHIP,REFERENCE,2);}
    }
    REQUIRE_N(c->t.table[0].count>=2 && c->t.table[0].count<=4096 && c->t.table[2].count<=16 && c->t.table[3].count>=1 && c->t.table[3].count<=1024 && c->t.table[18].count<=1024,COUNT_LIMIT,LIMIT,6);
    REQUIRE_N(c->t.table[10].count<=64,COUNT_LIMIT,LIMIT,1);
    REQUIRE_N(c->t.table[4].count<=2048 && c->t.table[13].count<=2048-c->t.table[4].count,COUNT_LIMIT,LIMIT,2);
    for(d=0;d<4;++d){uint32_t count=c->t.table[d==0?11:d==1?12:d==2?16:19].count;
        REQUIRE(count<=65536-total,COUNT_LIMIT,LIMIT);total+=count;}
    REQUIRE_N(total==c->h.resolution_access_transport_rows,MEMBERSHIP,COUNT,1);
    c->r->resolution_access_transport_rows=total;
    TRY(find_object(c,6,1,N,N,&object));TRY(directory(c,object,&pool));
    REQUIRE_N(c->h.string_pool_object==(pool.count?object:N),MEMBERSHIP,NULL_DOMAIN,1);
    TRY(charge(c,sizeof(pool)));memcpy(&c->pool,&pool,sizeof(pool));c->w->directory_seen[object]=1;
    for(i=0;i<5;++i){uint32_t b;at(c,N,2,i,N);TRY(object_read(c,2,39,i,&digest));
        for(b=0;b<32;++b){c->r->field=b;TRY(charge(c,3));if(digest.bytes[b]!=expected->digests[i].bytes[b]){ return bad(c,S(BINDING),D(BINDING_MISMATCH)); }}}
    return 1;
}

static int check_row_domains(Check *c) {
 uint32_t i;
 TRY(check_pool(c));
 for(i=0;i<c->t.table[0].count;++i) { Ir8PacketType v;
  at(c,1,c->t.table[0].object,i,N); TRY(row(c,1,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(enum_value(c,v.tag,1,3,0));
  c->r->field=2; TRY(string_ref(c,v.atom,1));
  c->r->field=3; TRY(ref(c,v.scheme,3,1));
  c->r->field=4; /* Scalar/span coupling checked by exact equations. */
  c->r->field=5; TRY(ref(c,v.argument,1,1));
  c->r->field=6; TRY(ref(c,v.result,1,1));
  c->r->field=7; TRY(enum_value(c,v.protocol,1,1,1));
  c->r->field=8; TRY(enum_value(c,v.result_identity,1,2,1));
 }
 for(i=0;i<c->t.table[1].count;++i) { Ir8PacketCallableContract v;
  at(c,2,c->t.table[1].object,i,N); TRY(row(c,2,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.type,1,0));
  c->r->field=2; TRY(ref(c,v.argument,1,0));
  c->r->field=3; TRY(ref(c,v.result,1,0));
  c->r->field=4; TRY(enum_value(c,v.protocol,1,1,0));
  c->r->field=5; TRY(enum_value(c,v.result_identity,1,2,0));
 }
 for(i=0;i<c->t.table[2].count;++i) { Ir8PacketScheme v;
  at(c,3,c->t.table[2].object,i,N); TRY(row(c,3,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(string_ref(c,v.name,0));
  c->r->field=2; /* Scalar/span coupling checked by exact equations. */
  c->r->field=3; TRY(ref(c,v.body,1,0));
  c->r->field=4; TRY(ref(c,v.neutral_env,4,0));
  c->r->field=5; TRY(ref(c,v.intro,18,0));
 }
 for(i=0;i<c->t.table[3].count;++i) { Ir8PacketEnv v;
  at(c,4,c->t.table[3].object,i,N); TRY(row(c,4,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.scheme,3,1));
  c->r->field=2; TRY(enum_value(c,v.mode,1,3,0));
  c->r->field=3; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[4].count;++i) { Ir8PacketCodeTyping v;
  at(c,5,c->t.table[4].object,i,N); TRY(row(c,5,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(enum_value(c,v.kind,1,2,0));
  c->r->field=2; TRY(string_ref(c,v.name,0));
  c->r->field=3; TRY(ref(c,v.scope,3,1));
  c->r->field=4; TRY(ref(c,v.callable_type,1,1));
  c->r->field=5; TRY(ref(c,v.argument,1,1));
  c->r->field=6; TRY(ref(c,v.result,1,0));
  c->r->field=7; /* Scalar/span coupling checked by exact equations. */
  c->r->field=8; TRY(string_ref(c,v.body_path,0));
  c->r->field=9; TRY(enum_value(c,v.expected_protocol,1,1,1));
  c->r->field=10; TRY(enum_value(c,v.expected_identity_flag,0,1,0));
 }
 for(i=0;i<c->t.table[5].count;++i) { Ir8PacketCodeExecution v;
  at(c,6,c->t.table[5].object,i,N); TRY(row(c,6,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.code,5,0));
  c->r->field=2; TRY(ref(c,v.env,4,0));
  c->r->field=3; TRY(ref(c,v.callable_type,1,1));
  c->r->field=4; TRY(ref(c,v.argument,1,1));
  c->r->field=5; TRY(ref(c,v.result,1,0));
  c->r->field=6; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[6].count;++i) { Ir8PacketShapeBinding v;
  at(c,7,c->t.table[6].object,i,N); TRY(row(c,7,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(enum_value(c,v.source_tag,1,3,0));
  c->r->field=2; TRY(string_ref(c,v.source_reference,1));
  c->r->field=3; TRY(ref(c,v.source_type,1,1));
  c->r->field=4; TRY(ref(c,v.source_scheme,3,1));
  c->r->field=5; TRY(enum_value(c,v.kind,1,6,0));
  c->r->field=6; TRY(ref(c,v.argument_rep,9,1));
  c->r->field=7; TRY(ref(c,v.result_rep,9,1));
 }
 for(i=0;i<c->t.table[7].count;++i) { Ir8PacketShapeTyping v;
  at(c,8,c->t.table[7].object,i,N); TRY(row(c,8,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.shape,7,0));
  c->r->field=2; TRY(ref(c,v.type,1,0));
  c->r->field=3; TRY(ref(c,v.scope,3,1));
  c->r->field=4; TRY(ref(c,v.contract,2,1));
 }
 for(i=0;i<c->t.table[8].count;++i) { Ir8PacketRepresentation v;
  at(c,9,c->t.table[8].object,i,N); TRY(row(c,9,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.shape,7,0));
  c->r->field=2; TRY(ref(c,v.typing,8,0));
  c->r->field=3; TRY(enum_value(c,v.ready_kind,1,5,0));
 }
 for(i=0;i<c->t.table[9].count;++i) { Ir8PacketNominalField v;
  at(c,10,c->t.table[9].object,i,N); TRY(row(c,10,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.shape,7,0));
  c->r->field=2; /* Scalar/span coupling checked by exact equations. */
  c->r->field=3; /* Scalar/span coupling checked by exact equations. */
  c->r->field=4; TRY(string_ref(c,v.name,0));
  c->r->field=5; TRY(ref(c,v.type,1,0));
  c->r->field=6; TRY(ref(c,v.declared_rep,9,0));
 }
 for(i=0;i<c->t.table[10].count;++i) { Ir8PacketFamilyTyping v;
  at(c,11,c->t.table[10].object,i,N); TRY(row(c,11,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(string_ref(c,v.name,0));
  c->r->field=2; TRY(ref(c,v.shape,7,0));
  c->r->field=3; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[11].count;++i) { Ir8PacketTypeResolution v;
  at(c,12,c->t.table[11].object,i,N); TRY(row(c,12,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.type,1,0));
  c->r->field=2; TRY(ref(c,v.env,4,0));
  c->r->field=3; TRY(ref(c,v.result,1,0));
 }
 for(i=0;i<c->t.table[12].count;++i) { Ir8PacketRepresentationResolution v;
  at(c,13,c->t.table[12].object,i,N); TRY(row(c,13,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.type,1,0));
  c->r->field=2; TRY(ref(c,v.env,4,0));
  c->r->field=3; TRY(ref(c,v.representation,9,0));
 }
 for(i=0;i<c->t.table[13].count;++i) { Ir8PacketSite v;
  at(c,14,c->t.table[13].object,i,N); TRY(row(c,14,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(string_ref(c,v.path,0));
  c->r->field=2; /* Scalar/span coupling checked by exact equations. */
  c->r->field=3; TRY(ref(c,v.scope,3,1));
  c->r->field=4; TRY(ref(c,v.principal_type,1,0));
  c->r->field=5; TRY(enum_value(c,v.category,1,7,0));
  c->r->field=6; TRY(ref(c,v.code,5,1));
  c->r->field=7; TRY(string_ref(c,v.legacy_physical,1));
  c->r->field=8; TRY(enum_value(c,v.context_tag,1,3,0));
  c->r->field=9; TRY(ref(c,v.context_intro,18,1));
  c->r->field=10; TRY(ref(c,v.context_code,5,1));
  c->r->field=11; TRY(ref(c,v.context_scheme,3,1));
  c->r->field=12; TRY(ref(c,v.sum_family,11,1));
  c->r->field=13; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[14].count;++i) { Ir8PacketSiteExecution v;
  at(c,15,c->t.table[14].object,i,N); TRY(row(c,15,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.site,14,0));
  c->r->field=2; TRY(ref(c,v.env,4,0));
  c->r->field=3; TRY(enum_value(c,v.origin_kind,1,3,0));
  c->r->field=4; TRY(ref(c,v.principal_type,1,0));
  c->r->field=5; TRY(ref(c,v.representation,9,0));
  c->r->field=6; TRY(ref(c,v.code_execution,6,1));
 }
 for(i=0;i<c->t.table[15].count;++i) { Ir8PacketSlot v;
  at(c,16,c->t.table[15].object,i,N); TRY(row(c,16,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.site,14,0));
  c->r->field=2; TRY(enum_value(c,v.role_tag,1,6,0));
  c->r->field=3; TRY(string_ref(c,v.role_name,1));
  c->r->field=4; /* Scalar/span coupling checked by exact equations. */
  c->r->field=5; TRY(ref(c,v.role_field,10,1));
  c->r->field=6; TRY(ref(c,v.type,1,0));
  c->r->field=7; TRY(enum_value(c,v.relation,1,3,0));
 }
 for(i=0;i<c->t.table[16].count;++i) { Ir8PacketAccess v;
  at(c,17,c->t.table[16].object,i,N); TRY(row(c,17,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.site,14,0));
  c->r->field=2; TRY(ref(c,v.origin_env,4,0));
  c->r->field=3; TRY(enum_value(c,v.mode,1,2,0));
  c->r->field=4; TRY(ref(c,v.use_env,4,1));
  c->r->field=5; TRY(ref(c,v.type,1,0));
  c->r->field=6; TRY(ref(c,v.scheme,3,1));
 }
 for(i=0;i<c->t.table[17].count;++i) { Ir8PacketIntro v;
  at(c,18,c->t.table[17].object,i,N); TRY(row(c,18,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.scheme,3,0));
  c->r->field=2; TRY(enum_value(c,v.container_tag,1,2,0));
  c->r->field=3; TRY(ref(c,v.container_code,5,1));
  c->r->field=4; TRY(string_ref(c,v.generalize_path,0));
  c->r->field=5; TRY(string_ref(c,v.seal_path,0));
  c->r->field=6; TRY(ref(c,v.body_type,1,0));
  c->r->field=7; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[18].count;++i) { Ir8PacketUse v;
  at(c,19,c->t.table[18].object,i,N); TRY(row(c,19,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(string_ref(c,v.name,0));
  c->r->field=2; TRY(ref(c,v.scheme,3,0));
  c->r->field=3; /* Scalar/span coupling checked by exact equations. */
  c->r->field=4; TRY(ref(c,v.env,4,0));
  c->r->field=5; TRY(ref(c,v.result_type,1,0));
  c->r->field=6; /* Scalar/span coupling checked by exact equations. */
 }
 for(i=0;i<c->t.table[19].count;++i) { Ir8PacketTransport v;
  at(c,20,c->t.table[19].object,i,N); TRY(row(c,20,i,&v));
  c->r->field=0; REQUIRE(v.id==i,SCHEMA,REFERENCE);
  c->r->field=1; TRY(ref(c,v.source_access,17,0));
  c->r->field=2; TRY(ref(c,v.projection_env,4,1));
  c->r->field=3; TRY(ref(c,v.result_access,17,0));
  c->r->field=4; TRY(enum_value(c,v.kind,1,2,0));
 }
 return 1;
}
static int check_payloads(Check *c) {
    uint32_t i,j;int cmp;
    for(i=0;i<c->t.table[0].count;++i){Ir8PacketType v;at(c,1,c->t.table[0].object,i,N);TRY(row(c,1,i,&v));
        if(v.tag==1) { REQUIRE_N(v.atom!=N&&v.scheme==N&&v.index==N&&v.argument==N&&v.result==N&&v.protocol==N&&v.result_identity==N,SCHEMA,NULL_DOMAIN,7); }
        else { if(v.tag==2) { REQUIRE_N(v.atom==N&&v.scheme!=N&&v.index!=N&&v.argument==N&&v.result==N&&v.protocol==N&&v.result_identity==N,SCHEMA,NULL_DOMAIN,7); }
        else { REQUIRE_N(v.atom==N&&v.scheme==N&&v.index==N&&v.argument!=N&&v.result!=N&&v.protocol==1&&v.result_identity!=N,SCHEMA,NULL_DOMAIN,7); } }
    }
    for(i=0;i<c->t.table[3].count;++i){Ir8PacketEnv v;at(c,4,c->t.table[3].object,i,N);TRY(row(c,4,i,&v));
        TRY(vector(c,v.arguments,1,i,N));
        for(j=0;j<v.arguments.count;++j){Ir8PacketTypeRef t;TRY(vector_read(c,v.arguments,23,j,&t));TRY(ref(c,t.row,1,0));}
        REQUIRE_N((v.mode==1&&i==0&&v.scheme==N&&v.arguments.count==0)||(v.mode!=1&&i!=0&&v.scheme!=N),SCHEMA,NULL_DOMAIN,7);
    }
    for(i=0;i<c->t.table[4].count;++i){Ir8PacketCodeTyping v;uint32_t prev=N;at(c,5,c->t.table[4].object,i,N);TRY(row(c,5,i,&v));REQUIRE(v.captures.count<=64,COUNT_LIMIT,LIMIT);TRY(vector(c,v.captures,2,i,N));
        REQUIRE_N((v.kind==1&&v.callable_type!=N&&v.argument!=N&&v.expected_protocol==1)||(v.kind==2&&v.callable_type==N&&v.argument==N&&v.expected_protocol==N&&v.expected_identity_flag==0),SCHEMA,NULL_DOMAIN,9);
        for(j=0;j<v.captures.count;++j){Ir8PacketCaptureTyping t;TRY(vector_read(c,v.captures,24,j,&t));TRY(string_ref(c,t.name,0));TRY(ref(c,t.type,1,0));TRY(enum_value(c,t.relation,1,3,0));
            if(prev!=N){TRY(string_cmp(c,prev,t.name,&cmp));REQUIRE(cmp<0,SCHEMA,ORDER);}prev=t.name;}
    }
    for(i=0;i<c->t.table[5].count;++i){Ir8PacketCodeExecution v;at(c,6,c->t.table[5].object,i,N);TRY(row(c,6,i,&v));REQUIRE(v.captures.count<=64,COUNT_LIMIT,LIMIT);TRY(vector(c,v.captures,3,i,N));
        for(j=0;j<v.captures.count;++j){Ir8PacketResolvedCapture t;TRY(vector_read(c,v.captures,25,j,&t));TRY(ref(c,t.code,5,0));TRY(ref(c,t.type,1,0));REQUIRE_N(t.position==j&&t.code==v.code,SCHEMA,REFERENCE,2);}}
    for(i=0;i<c->t.table[6].count;++i){Ir8PacketShapeBinding v;at(c,7,c->t.table[6].object,i,N);TRY(row(c,7,i,&v));
        REQUIRE_N((v.source_tag==1&&v.source_reference!=N&&v.source_type==N&&v.source_scheme==N)||(v.source_tag==2&&v.source_reference==N&&v.source_type!=N&&v.source_scheme==N)||(v.source_tag==3&&v.source_reference==N&&v.source_type!=N&&v.source_scheme!=N),SCHEMA,NULL_DOMAIN,12);
        REQUIRE_N((v.kind==5&&v.argument_rep!=N&&v.result_rep!=N)||(v.kind!=5&&v.argument_rep==N&&v.result_rep==N),SCHEMA,NULL_DOMAIN,6);}
    for(i=0;i<c->t.table[10].count;++i){Ir8PacketFamilyTyping v;at(c,11,c->t.table[10].object,i,N);TRY(row(c,11,i,&v));REQUIRE_N(v.variants.count>=1&&v.variants.count<=64,COUNT_LIMIT,LIMIT,2);TRY(vector(c,v.variants,6,i,N));
        for(j=0;j<v.variants.count;++j){Ir8PacketVariantTyping t;uint32_t k;TRY(vector_read(c,v.variants,28,j,&t));TRY(string_ref(c,t.name,0));REQUIRE(t.index==j,SCHEMA,REFERENCE);REQUIRE(t.fields.count<=32,COUNT_LIMIT,LIMIT);TRY(vector(c,t.fields,8,i,j));
            for(k=0;k<t.fields.count;++k){Ir8PacketNominalFieldRef f;TRY(vector_read(c,t.fields,30,k,&f));TRY(ref(c,f.row,10,0));}}}
    for(i=0;i<c->t.table[13].count;++i){Ir8PacketSite v;at(c,14,c->t.table[13].object,i,N);TRY(row(c,14,i,&v));
        REQUIRE_N(((v.category==2||v.category==3)==(v.code!=N))&&(v.arm==N||v.category==3),SCHEMA,NULL_DOMAIN,6);
        REQUIRE_N((v.category==7&&v.sum_family!=N&&v.sum_variant!=N)||(v.category!=7&&v.sum_family==N&&v.sum_variant==N),SCHEMA,NULL_DOMAIN,6);
        REQUIRE_N((v.context_tag==1&&v.context_intro==N&&v.context_code==N&&v.context_scheme==N)||(v.context_tag==2&&v.context_intro!=N&&v.context_code==N&&v.context_scheme==N)||(v.context_tag==3&&v.context_intro==N&&v.context_code!=N&&v.context_scheme!=N),SCHEMA,NULL_DOMAIN,12);
        /* The validated unique pool makes offset equality string equality.
         * This checks stored identity, not canonical raw-path provenance. */
        c->r->field=1;
        for(j=0;j<i;++j){Ir8PacketSite prior;TRY(row(c,14,j,&prior));
            REQUIRE_N(v.path!=prior.path||v.arm!=prior.arm,SCHEMA,DUPLICATE,2);}
        c->r->field=N;}
    for(i=0;i<c->t.table[15].count;++i){Ir8PacketSlot v;at(c,16,c->t.table[15].object,i,N);TRY(row(c,16,i,&v));
        REQUIRE_N((v.role_tag==1&&v.role_name!=N&&v.role_variant==N&&v.role_field==N)||(v.role_tag==2&&v.role_name==N&&v.role_variant==N&&v.role_field!=N)||(v.role_tag==3&&v.role_name==N&&v.role_variant!=N&&v.role_field!=N)||(v.role_tag>=4&&v.role_name==N&&v.role_variant==N&&v.role_field==N),SCHEMA,NULL_DOMAIN,16);}
    for(i=0;i<c->t.table[16].count;++i){Ir8PacketAccess v;at(c,17,c->t.table[16].object,i,N);TRY(row(c,17,i,&v));
        REQUIRE_N((v.mode==1&&v.use_env!=N&&v.scheme==N)||(v.mode==2&&v.use_env==N&&v.scheme!=N),SCHEMA,NULL_DOMAIN,6);}
    for(i=0;i<c->t.table[17].count;++i){Ir8PacketIntro v;at(c,18,c->t.table[17].object,i,N);TRY(row(c,18,i,&v));TRY(vector(c,v.result_sites,4,i,N));
        REQUIRE_N((v.container_tag==1&&v.container_code==N)||(v.container_tag==2&&v.container_code!=N),SCHEMA,NULL_DOMAIN,4);
        for(j=0;j<v.result_sites.count;++j){Ir8PacketSiteRef s;TRY(vector_read(c,v.result_sites,26,j,&s));TRY(ref(c,s.row,14,0));}}
    for(i=0;i<c->t.table[18].count;++i){Ir8PacketUse v;Ir8PacketEnv e;at(c,19,c->t.table[18].object,i,N);TRY(row(c,19,i,&v));TRY(row(c,4,v.env,&e));
        REQUIRE_N(v.arguments.count==e.arguments.count&&v.arguments.object==e.arguments.object,SCHEMA,VECTOR_SHARING,2);
        TRY(vector(c,v.occurrences,5,i,N));for(j=0;j<v.occurrences.count;++j){Ir8PacketPathRef p;uint32_t k,l;
            TRY(vector_read(c,v.occurrences,27,j,&p));TRY(string_ref(c,p.path,0));
            at(c,19,v.occurrences.object,j,0);
            /* Each stored occurrence belongs to exactly one Use. Check all
             * earlier occurrences, including those in this same vector. */
            for(k=0;k<=i;++k){Ir8PacketUse prior;uint32_t count;
                TRY(row(c,19,k,&prior));count=k==i?j:prior.occurrences.count;
                for(l=0;l<count;++l){Ir8PacketPathRef q;
                    TRY(vector_read(c,prior.occurrences,27,l,&q));
                    REQUIRE(p.path!=q.path,SCHEMA,DUPLICATE);}}
            at(c,19,c->t.table[18].object,i,N);}}
    for(i=0;i<c->t.table[19].count;++i){Ir8PacketTransport v;at(c,20,c->t.table[19].object,i,N);TRY(row(c,20,i,&v));
        REQUIRE_N((v.kind==1&&v.projection_env==N)||(v.kind==2&&v.projection_env!=N),SCHEMA,NULL_DOMAIN,4);}
    return 1;
}
/* JSON scalar ordering is streamed, never an expanded recursive Type key. */
typedef struct JsonString { uint32_t off,pos,n,state;unsigned char pending[6]; } JsonString;
static int json_byte(Check *c,JsonString *j,unsigned char *out) {
    unsigned char b;static const char hex[]="0123456789abcdef";
    TRY(charge(c,1));
    if(j->state==0){j->state=1;*out='"';return 1;}
    if(j->pos<j->n){*out=j->pending[j->pos++];return 1;}
    if(j->state==2){j->state=3;*out='"';return 1;}
    if(j->state==3){*out=0;return 1;}
    TRY(pool_byte(c,j->off++,&b));j->pos=0;j->n=0;
    if(!b){j->state=3;*out='"';return 1;}
    if(b=='"'||b=='\\'){j->pending[0]=b;j->n=1;*out='\\';return 1;}
    if(b<32){unsigned char escape=b==8?'b':b==9?'t':b==10?'n':b==12?'f':b==13?'r':0;
        if(escape){j->pending[0]=escape;j->n=1;}
        else {j->pending[0]='u';j->pending[1]='0';j->pending[2]='0';j->pending[3]=hex[b>>4];j->pending[4]=hex[b&15];j->n=5;}
        *out='\\';return 1;}
    *out=b;return 1;
}
static int json_string_cmp(Check *c,uint32_t a,uint32_t b,int *cmp) {
    JsonString x={a,0,0,0,{0}},y={b,0,0,0,{0}};unsigned char u,v;
    for(;;){TRY(json_byte(c,&x,&u));TRY(json_byte(c,&y,&v));TRY(charge(c,1));if(u!=v){*cmp=u<v?-1:1;return 1;}if(!u){*cmp=0;return 1;}}
}
static int structural_cmp(Check *c,uint32_t a,uint32_t b,int *cmp) {
    uint32_t depth=0;
    while(a!=b) {
        Ir8PacketType x,y;TRY(charge(c,1));REQUIRE(++depth<=32,TYPE_EQUATION,LIMIT);TRY(row(c,1,a,&x));TRY(row(c,1,b,&y));
        TRY(charge(c,1));if(x.tag!=y.tag){uint32_t ax=x.tag==3?0:x.tag==1?1:2,by=y.tag==3?0:y.tag==1?1:2;TRY(charge(c,1));*cmp=ax<by?-1:1;return 1;}
        if(x.tag==1){ return json_string_cmp(c,x.atom,y.atom,cmp); }
        if(x.tag==2){Ir8PacketScheme sx,sy;TRY(row(c,3,x.scheme,&sx));TRY(row(c,3,y.scheme,&sy));TRY(json_string_cmp(c,sx.name,sy.name,cmp));if(*cmp){ return 1; }TRY(charge(c,1));*cmp=x.index<y.index?-1:x.index>y.index?1:0;return 1;}
        TRY(charge(c,1));if(x.argument!=y.argument){a=x.argument;b=y.argument;continue;}
        TRY(charge(c,1));if(x.result!=y.result){a=x.result;b=y.result;continue;}
        TRY(charge(c,2));*cmp=x.result_identity==y.result_identity?0:x.result_identity==2?-1:1;return 1;
    }
    *cmp=0;return 1;
}
static int generic_body(Check *c,uint32_t root,uint32_t scheme);
static int scope_type(Check *c,uint32_t type,uint32_t scheme) {
    uint32_t allowed;
    TRY(ref(c,type,1,0));TRY(ref(c,scheme,3,1));
    allowed=scheme==N?0:UINT32_C(1)<<scheme;
    REQUIRE_N((c->w->type_scope_mask[type]&~allowed)==0,TYPE_EQUATION,EQUATION,1);
    if(scheme!=N){TRY(generic_body(c,type,scheme));}return 1;
}
static int resolution(Check *c,uint32_t type,uint32_t env,uint32_t *result,uint32_t *representation) {
    uint32_t lo=0,hi=c->t.table[11].count;Ir8PacketTypeResolution r;Ir8PacketRepresentationResolution q;
    while(lo<hi){uint32_t m=lo+(hi-lo)/2;TRY(row(c,12,m,&r));TRY(charge(c,2));if(r.type<type||(r.type==type&&r.env<env)){ lo=m+1; }else { hi=m; }}
    REQUIRE_N(lo<c->t.table[11].count,TYPE_EQUATION,MISSING,1);TRY(row(c,12,lo,&r));
    REQUIRE_N(r.type==type&&r.env==env,TYPE_EQUATION,MISSING,2);*result=r.result;
    if(representation){TRY(row(c,13,lo,&q));REQUIRE_N(q.type==type&&q.env==env,REPRESENTATION_EQUATION,EQUATION,2);*representation=q.representation;}
    return 1;
}
static int check_types(Check *c) {
    uint32_t i,contract=0,prev_depth=0;int cmp;
    for(i=0;i<c->t.table[0].count;++i){Ir8PacketType t;uint32_t depth=1,mask=0;at(c,1,c->t.table[0].object,i,N);TRY(row(c,1,i,&t));
        if(t.tag==2){Ir8PacketScheme s;TRY(row(c,3,t.scheme,&s));REQUIRE(t.index<s.parameters,TYPE_EQUATION,REFERENCE);mask=UINT32_C(1)<<t.scheme;}
        else { if(t.tag==3){Ir8PacketCallableContract a;
            REQUIRE_N(t.argument<i&&t.result<i,TYPE_EQUATION,ORDER,2);
            TRY(charge(c,4));depth=1+(c->w->type_depth[t.argument]>c->w->type_depth[t.result]?c->w->type_depth[t.argument]:c->w->type_depth[t.result]);mask=c->w->type_scope_mask[t.argument]|c->w->type_scope_mask[t.result];
            REQUIRE_N(t.result_identity!=2||t.argument==t.result,TYPE_EQUATION,EQUATION,2);
            TRY(row(c,2,contract,&a));REQUIRE_N(a.type==i&&a.argument==t.argument&&a.result==t.result&&a.protocol==t.protocol&&a.result_identity==t.result_identity,TYPE_EQUATION,EQUATION,5);++contract;} }
        REQUIRE_N(depth<=32&&depth>=prev_depth,TYPE_EQUATION,ORDER,2);
        if(i&&depth==prev_depth){TRY(structural_cmp(c,i-1,i,&cmp));REQUIRE(cmp<0,TYPE_EQUATION,ORDER);}
        TRY(charge(c,2));c->w->type_depth[i]=depth;c->w->type_scope_mask[i]=mask;prev_depth=depth;
    }
    REQUIRE_N(contract==c->t.table[1].count,TYPE_EQUATION,COUNT,1);
    return 1;
}
/* No expanded Type tree is allocated. Shared DAG children are examined again
 * and charged again. The explicit32-frame walk and work cap bound every path;
 * a lower-accepted highly shared DAG may exhaust this narrower packet budget. */
static int generic_body(Check *c,uint32_t root,uint32_t scheme) {
    uint32_t sp=1;
    TRY(charge(c,4));c->w->walk[0].type=root;c->w->walk[0].env=scheme;c->w->walk[0].phase=0;c->w->walk[0].expected=N;
    while(sp){Ir8PacketWalkFrame frame;Ir8PacketType t;uint32_t child;
        TRY(charge(c,sizeof(frame)));memcpy(&frame,&c->w->walk[sp-1],sizeof(frame));
        TRY(charge(c,1));TRY(row(c,1,frame.type,&t));
        if(frame.phase==0){
            if(t.tag==1){int b,i;TRY(string_is(c,t.atom,"#bool",&b));TRY(string_is(c,t.atom,"#i64",&i));REQUIRE(b||i,TYPE_EQUATION,EQUATION);--sp;continue;}
            if(t.tag==2){EQ(t.scheme,scheme,TYPE_EQUATION);--sp;continue;}
            REQUIRE_N(t.tag==3&&t.protocol==1&&t.result_identity==1,TYPE_EQUATION,EQUATION,3);
            child=t.argument;
        }else { if(frame.phase==1){ child=t.result; }
        else{--sp;continue;} }
        REQUIRE(sp<32,TYPE_EQUATION,LIMIT);
        TRY(charge(c,6));c->w->walk[sp-1].phase=frame.phase+1;
        c->w->walk[sp].type=child;c->w->walk[sp].env=scheme;c->w->walk[sp].phase=0;c->w->walk[sp].expected=N;++sp;
    }
    return 1;
}

/* Env arguments may name a published nominal atom, not an arbitrary CLOSED
 * Type. This runs before semantic Shape validation: every read remains bounded,
 * and the later complete Shape/field/descriptor checks are still mandatory. */
static int shape_find(Check *c,uint32_t tag,uint32_t first,uint32_t second,uint32_t *id);
static int nominal_argument(Check *c,const Ir8PacketType *t) {
    uint32_t id,lo=0,hi;unsigned char first;
    Ir8PacketShapeBinding s;Ir8PacketShapeTyping st;
    Ir8PacketShapeSpec spec;Ir8PacketRepresentation rep;
    TRY(shape_find(c,IR8_PACKET_SHAPE_SOURCE_LEGACY,t->atom,N,&id));
    TRY(row(c,7,id,&s));TRY(row(c,8,id,&st));TRY(row(c,9,id,&rep));
    TRY(descriptor(c,1,id,&spec));
    REQUIRE_N(t->tag==IR8_PACKET_TYPE_TAG_CLOSED&&s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&
        s.source_reference==t->atom&&s.source_type==N&&s.source_scheme==N&&
        (s.kind==IR8_PACKET_SHAPE_KIND_DATA||s.kind==IR8_PACKET_SHAPE_KIND_SUM),TYPE_EQUATION,EQUATION,7);
    REQUIRE_N(st.shape==id&&st.type==t->id&&st.scope==N&&st.contract==N&&
        rep.shape==id&&rep.typing==id&&
        rep.ready_kind==(s.kind==IR8_PACKET_SHAPE_KIND_DATA?IR8_PACKET_READY_KIND_DATA:IR8_PACKET_READY_KIND_SUM),REPRESENTATION_EQUATION,EQUATION,7);
    REQUIRE_N(spec.shape==id&&spec.typing==id&&spec.representation==id&&spec.kind==s.kind&&
        s.argument_rep==N&&s.result_rep==N&&spec.argument_rep==N&&spec.result_rep==N,REPRESENTATION_EQUATION,EQUATION,8);
    TRY(pool_byte(c,t->atom,&first));
    if(s.kind==IR8_PACKET_SHAPE_KIND_DATA){
        REQUIRE_N(first!='#'&&first!='%'&&first!='@'&&first!='^',TYPE_EQUATION,EQUATION,4);
        return 1;
    }
    EQ(first,'%',TYPE_EQUATION);
    TRY(charge(c,1));hi=c->t.table[10].count;
    while(lo<hi){Ir8PacketFamilyTyping f;uint32_t m=lo+(hi-lo)/2;
        TRY(row(c,11,m,&f));TRY(charge(c,3));if(f.shape<id){lo=m+1;}else{hi=m;}}
    {Ir8PacketFamilyTyping f;Ir8PacketFamilySpec fs;
        REQUIRE(lo<c->t.table[10].count,TYPE_EQUATION,MISSING);
        TRY(row(c,11,lo,&f));TRY(descriptor(c,3,lo,&fs));
        REQUIRE_N(f.shape==id&&fs.family==f.id&&fs.shape==id&&
            fs.variants.count==f.variants.count&&f.variants.count>=1&&f.variants.count<=64,TYPE_EQUATION,EQUATION,6);
        /* The suffix is not a separate registered pool start. Read bytes only. */
        uint32_t a=t->atom+1,b=f.name;
        for(;;){unsigned char x,y;TRY(pool_byte(c,a++,&x));TRY(pool_byte(c,b++,&y));
            EQ(x,y,TYPE_EQUATION);if(!x){break;}}
    }
    return 1;
}

/* Only the new arrow-coordinate path uses this walk. It follows Type IDs, not
 * nominal fields, and rechecks shared DAG children on every visit. Each child
 * must use the exact canonical representation named by its parent. */
static int arrow_argument(Check *c,uint32_t root) {
    uint32_t stack[32][3],sp=1;
    TRY(charge(c,sizeof(stack[0])+1));stack[0][0]=root;stack[0][1]=N;stack[0][2]=1;
    while(sp){
        uint32_t type,expected,depth,id;Ir8PacketType t;Ir8PacketShapeBinding s;
        Ir8PacketShapeTyping st;Ir8PacketRepresentation rep;Ir8PacketShapeSpec spec;
        TRY(charge(c,sizeof(stack[0])+4));--sp;
        type=stack[sp][0];expected=stack[sp][1];depth=stack[sp][2];
        at(c,1,c->t.table[0].object,type,N);TRY(row(c,1,type,&t));
        REQUIRE_N(depth<=32&&(t.tag==IR8_PACKET_TYPE_TAG_CLOSED||t.tag==IR8_PACKET_TYPE_TAG_ARROW),TYPE_EQUATION,EQUATION,3);
        TRY(shape_find(c,t.tag==IR8_PACKET_TYPE_TAG_ARROW?IR8_PACKET_SHAPE_SOURCE_CANONICAL_ARROW:IR8_PACKET_SHAPE_SOURCE_LEGACY,
            t.tag==IR8_PACKET_TYPE_TAG_ARROW?t.id:t.atom,N,&id));
        REQUIRE_N((expected==N&&depth==1)||(expected!=N&&expected==id),REPRESENTATION_EQUATION,EQUATION,4);
        TRY(row(c,7,id,&s));TRY(row(c,8,id,&st));TRY(row(c,9,id,&rep));TRY(descriptor(c,1,id,&spec));
        REQUIRE_N(st.shape==id&&st.type==t.id&&st.scope==N&&rep.shape==id&&rep.typing==id&&
            spec.shape==id&&spec.typing==id&&spec.representation==id&&spec.kind==s.kind&&
            spec.argument_rep==s.argument_rep&&spec.result_rep==s.result_rep,REPRESENTATION_EQUATION,EQUATION,11);
        if(t.tag==IR8_PACKET_TYPE_TAG_ARROW){Ir8PacketCallableContract contract;
            REQUIRE_N(t.atom==N&&t.scheme==N&&t.index==N&&t.argument<t.id&&t.result<t.id&&
                t.protocol==IR8_PACKET_PROTOCOL_REPEAT&&t.result_identity==IR8_PACKET_RESULT_IDENTITY_UNKNOWN,
                TYPE_EQUATION,EQUATION,7);
            REQUIRE_N(s.source_tag==IR8_PACKET_SHAPE_SOURCE_CANONICAL_ARROW&&s.source_type==t.id&&
                s.source_reference==N&&s.source_scheme==N&&s.kind==IR8_PACKET_SHAPE_KIND_REPEAT&&
                rep.ready_kind==IR8_PACKET_READY_KIND_FUNCTION&&s.argument_rep!=N&&s.result_rep!=N&&spec.fields_object==N&&
                spec.field_first==0&&spec.field_count==0,REPRESENTATION_EQUATION,EQUATION,11);
            TRY(row(c,2,st.contract,&contract));
            REQUIRE_N(contract.type==t.id&&contract.argument==t.argument&&contract.result==t.result&&
                contract.protocol==t.protocol&&contract.result_identity==t.result_identity,TYPE_EQUATION,EQUATION,5);
            REQUIRE_N(depth<32&&sp<=30,TYPE_EQUATION,LIMIT,2);
            TRY(charge(c,2*sizeof(stack[0])+8));
            stack[sp][0]=t.result;stack[sp][1]=s.result_rep;stack[sp][2]=depth+1;++sp;
            stack[sp][0]=t.argument;stack[sp][1]=s.argument_rep;stack[sp][2]=depth+1;++sp;
        }else{int b,i;
            REQUIRE_N(t.scheme==N&&t.index==N&&t.argument==N&&t.result==N&&t.protocol==N&&t.result_identity==N,
                TYPE_EQUATION,EQUATION,6);
            TRY(string_is(c,t.atom,"#bool",&b));TRY(string_is(c,t.atom,"#i64",&i));
            if(b||i){
                REQUIRE_N(s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&s.source_reference==t.atom&&
                    s.source_type==N&&s.source_scheme==N&&s.kind==(b?IR8_PACKET_SHAPE_KIND_BOOL:IR8_PACKET_SHAPE_KIND_I64)&&
                    st.contract==N&&rep.ready_kind==IR8_PACKET_READY_KIND_SCALAR&&s.argument_rep==N&&s.result_rep==N&&
                    spec.fields_object==N&&spec.field_first==0&&spec.field_count==0,REPRESENTATION_EQUATION,EQUATION,12);
            }else{TRY(nominal_argument(c,&t));}
        }
    }
    return 1;
}

static int check_environments(Check *c) {
    uint32_t i,eid=1,j;int cmp;
    for(i=0;i<c->t.table[2].count;++i){Ir8PacketScheme s;Ir8PacketEnv e;Ir8PacketType b;
        at(c,3,c->t.table[2].object,i,N);TRY(row(c,3,i,&s));REQUIRE_N(s.parameters>=1&&s.parameters<=8,TYPE_EQUATION,LIMIT,2);
        if(i){Ir8PacketScheme p;TRY(row(c,3,i-1,&p));TRY(string_cmp(c,p.name,s.name,&cmp));REQUIRE(cmp<0,TYPE_EQUATION,ORDER);}
        TRY(row(c,1,s.body,&b));REQUIRE(b.tag==3,TYPE_EQUATION,EQUATION);TRY(scope_type(c,s.body,i));
        REQUIRE(s.neutral_env==eid,TYPE_EQUATION,ORDER);TRY(row(c,4,eid,&e));
        REQUIRE_N(e.scheme==i&&e.mode==2&&e.arguments.count==s.parameters,TYPE_EQUATION,EQUATION,3);
        for(j=0;j<s.parameters;++j){Ir8PacketTypeRef r;Ir8PacketType t;TRY(vector_read(c,e.arguments,23,j,&r));TRY(row(c,1,r.row,&t));REQUIRE_N(t.tag==2&&t.scheme==i&&t.index==j,TYPE_EQUATION,EQUATION,3);}
        ++eid;
        while(eid<c->t.table[3].count){Ir8PacketEnv cur,prev;int order=0;
            TRY(row(c,4,eid,&cur));if(cur.scheme!=i){ break; }
            REQUIRE_N(cur.mode==3&&cur.arguments.count==s.parameters,TYPE_EQUATION,EQUATION,2);TRY(row(c,4,eid-1,&prev));
            for(j=0;j<s.parameters;++j){Ir8PacketTypeRef r,p;Ir8PacketType t;int b1,b2;
                TRY(vector_read(c,cur.arguments,23,j,&r));TRY(row(c,1,r.row,&t));
                if(t.tag==IR8_PACKET_TYPE_TAG_ARROW){TRY(arrow_argument(c,t.id));}
                else {REQUIRE(t.tag==1,TYPE_EQUATION,EQUATION);
                    TRY(string_is(c,t.atom,"#bool",&b1));TRY(string_is(c,t.atom,"#i64",&b2));
                    if(b1||b2){REQUIRE(1,TYPE_EQUATION,EQUATION);}
                    else {TRY(charge(c,1));TRY(nominal_argument(c,&t));}}
                if(prev.mode==3&&!order){TRY(vector_read(c,prev.arguments,23,j,&p));TRY(charge(c,1));order=p.row<r.row?-1:p.row>r.row?1:0;}}
            if(prev.mode==3){ REQUIRE(order<0,TYPE_EQUATION,ORDER); }++eid;
        }
    }
    REQUIRE_N(eid==c->t.table[3].count,TYPE_EQUATION,EXTRA,1);return 1;
}
static int check_resolutions(Check *c) {
    uint32_t i;Ir8PacketTypeResolution prev={0,0,0,0};
    REQUIRE_N(c->t.table[11].count==c->t.table[12].count,TYPE_EQUATION,COUNT,1);
    for(i=0;i<c->t.table[11].count;++i){Ir8PacketTypeResolution r;Ir8PacketType t,out;Ir8PacketEnv e;uint32_t result,a,b;
        at(c,12,c->t.table[11].object,i,N);TRY(row(c,12,i,&r));TRY(row(c,1,r.type,&t));TRY(row(c,1,r.result,&out));TRY(row(c,4,r.env,&e));TRY(scope_type(c,r.type,e.scheme));
        if(i){ REQUIRE_N(prev.type<r.type||(prev.type==r.type&&prev.env<r.env),TYPE_EQUATION,ORDER,3); }
        if(t.tag==1){ EQ(r.result,r.type,TYPE_EQUATION); }
        else { if(t.tag==2){Ir8PacketTypeRef tr;REQUIRE(t.scheme==e.scheme,TYPE_EQUATION,EQUATION);TRY(vector_read(c,e.arguments,23,t.index,&tr));EQ(r.result,tr.row,TYPE_EQUATION);}
        else {TRY(resolution(c,t.argument,r.env,&a,0));TRY(resolution(c,t.result,r.env,&b,0));
            REQUIRE_N(out.tag==3&&out.argument==a&&out.result==b&&out.protocol==t.protocol&&out.result_identity==t.result_identity,TYPE_EQUATION,EQUATION,5);} }
        if(e.mode==2){ EQ(r.result,r.type,TYPE_EQUATION); }else { EQ(c->w->type_scope_mask[r.result],0,TYPE_EQUATION); }
        if(c->w->type_scope_mask[r.result]==0){TRY(resolution(c,r.result,0,&result,0));EQ(result,r.result,TYPE_EQUATION);}
        TRY(charge(c,sizeof(r)));memcpy(&prev,&r,sizeof(r));
    }
    return 1;
}

static int check_descriptor_domains(Check *c) {
 uint32_t i;
 for(i=0;i<c->t.descriptor[0].count;++i) { Ir8PacketShapeSpec v;
 at(c,1,c->t.descriptor[0].object,i,N); TRY(descriptor(c,1,i,&v));
 c->r->field=0; TRY(ref(c,v.shape,7,0));
 c->r->field=1; TRY(ref(c,v.typing,8,0));
 c->r->field=2; TRY(ref(c,v.representation,9,0));
 c->r->field=3; TRY(enum_value(c,v.kind,1,6,0));
 c->r->field=4; /* Exact domain/slice coupling follows. */
 c->r->field=5; /* Exact domain/slice coupling follows. */
 c->r->field=6; /* Exact domain/slice coupling follows. */
 c->r->field=7; TRY(ref(c,v.argument_rep,9,1));
 c->r->field=8; TRY(ref(c,v.result_rep,9,1));
 }
 for(i=0;i<c->t.descriptor[1].count;++i) { Ir8PacketCodeSpec v;
 at(c,2,c->t.descriptor[1].object,i,N); TRY(descriptor(c,2,i,&v));
 c->r->field=0; TRY(ref(c,v.code,5,0));
 c->r->field=1; TRY(ref(c,v.principal_env,4,0));
 c->r->field=2; TRY(ref(c,v.principal_rep,9,0));
 c->r->field=3; /* Exact domain/slice coupling follows. */
 c->r->field=4; /* Exact domain/slice coupling follows. */
 c->r->field=5; /* Exact domain/slice coupling follows. */
 c->r->field=6; TRY(enum_value(c,v.body_binding,1,1,0));
 }
 for(i=0;i<c->t.descriptor[2].count;++i) { Ir8PacketFamilySpec v;
 at(c,3,c->t.descriptor[2].object,i,N); TRY(descriptor(c,3,i,&v));
 c->r->field=0; TRY(ref(c,v.family,11,0));
 c->r->field=1; TRY(ref(c,v.shape,7,0));
 c->r->field=2; /* Exact domain/slice coupling follows. */
 TRY(vector(c,v.variants,7,i,N));
 }
 for(i=0;i<c->t.descriptor[3].count;++i) { Ir8PacketVariantSpec v;
 at(c,4,c->t.descriptor[3].object,i,N); TRY(descriptor(c,4,i,&v));
 c->r->field=0; TRY(ref(c,v.family,11,0));
 c->r->field=1; /* Exact domain/slice coupling follows. */
 c->r->field=2; TRY(string_ref(c,v.name,0));
 c->r->field=3; TRY(ref(c,v.shape,7,0));
 c->r->field=4; /* Exact domain/slice coupling follows. */
 c->r->field=5; /* Exact domain/slice coupling follows. */
 c->r->field=6; /* Exact domain/slice coupling follows. */
 }
 for(i=0;i<c->t.descriptor[4].count;++i) { Ir8PacketFieldSpec v;
 at(c,5,c->t.descriptor[4].object,i,N); TRY(descriptor(c,5,i,&v));
 c->r->field=0; TRY(enum_value(c,v.owner_kind,1,3,0));
 c->r->field=1; /* Exact domain/slice coupling follows. */
 c->r->field=2; /* Exact domain/slice coupling follows. */
 c->r->field=3; TRY(string_ref(c,v.name,0));
 c->r->field=4; TRY(ref(c,v.type,1,0));
 c->r->field=5; TRY(ref(c,v.nominal_declared_rep,9,1));
 c->r->field=6; TRY(ref(c,v.code_principal_rep,9,1));
 c->r->field=7; TRY(enum_value(c,v.relation,1,3,1));
 }
 for(i=0;i<c->t.descriptor[5].count;++i) { Ir8PacketFieldSpec v;
 at(c,6,c->t.descriptor[5].object,i,N); TRY(descriptor(c,6,i,&v));
 c->r->field=0; TRY(enum_value(c,v.owner_kind,1,3,0));
 c->r->field=1; /* Exact domain/slice coupling follows. */
 c->r->field=2; /* Exact domain/slice coupling follows. */
 c->r->field=3; TRY(string_ref(c,v.name,0));
 c->r->field=4; TRY(ref(c,v.type,1,0));
 c->r->field=5; TRY(ref(c,v.nominal_declared_rep,9,1));
 c->r->field=6; TRY(ref(c,v.code_principal_rep,9,1));
 c->r->field=7; TRY(enum_value(c,v.relation,1,3,1));
 }
 return 1;
}
static int shape_find(Check *c,uint32_t tag,uint32_t first,uint32_t second,uint32_t *id) {
    uint32_t lo=0,hi=c->t.table[6].count;Ir8PacketShapeBinding s;int cmp;
    while(lo<hi){uint32_t m=lo+(hi-lo)/2;TRY(row(c,7,m,&s));TRY(charge(c,1));
        cmp=s.source_tag<tag?-1:s.source_tag>tag?1:0;
        if(!cmp){if(tag==1){ TRY(string_cmp(c,s.source_reference,first,&cmp)); }
            else {uint32_t a=tag==2?s.source_type:s.source_scheme;TRY(charge(c,1));cmp=a<first?-1:a>first?1:0;
                if(!cmp&&tag==3){TRY(charge(c,1));cmp=s.source_type<second?-1:s.source_type>second?1:0;}}}
        if(cmp<0){ lo=m+1; }else { hi=m; }}
    REQUIRE_N(lo<c->t.table[6].count,REPRESENTATION_EQUATION,MISSING,1);TRY(row(c,7,lo,&s));
    REQUIRE(s.source_tag==tag,REPRESENTATION_EQUATION,MISSING);
    if(tag==1){ EQ(s.source_reference,first,REPRESENTATION_EQUATION); }
    else { if(tag==2){ EQ(s.source_type,first,REPRESENTATION_EQUATION); }
    else { REQUIRE_N(s.source_scheme==first&&s.source_type==second,REPRESENTATION_EQUATION,MISSING,2); } }
    *id=lo;return 1;
}
static int check_shapes(Check *c) {
    uint32_t i,canonical=0,open=0;Ir8PacketShapeBinding previous={0};int cmp;
    REQUIRE_N(c->t.table[6].count==c->t.table[7].count&&c->t.table[6].count==c->t.table[8].count,REPRESENTATION_EQUATION,COUNT,2);
    for(i=0;i<c->t.table[6].count;++i){Ir8PacketShapeBinding s;Ir8PacketShapeTyping st;Ir8PacketRepresentation rep;Ir8PacketType t;uint32_t ready;
        at(c,7,c->t.table[6].object,i,N);TRY(row(c,7,i,&s));TRY(row(c,8,i,&st));TRY(row(c,9,i,&rep));TRY(row(c,1,st.type,&t));
        REQUIRE_N(st.shape==i&&rep.shape==i&&rep.typing==i,REPRESENTATION_EQUATION,EQUATION,3);
        if(i){REQUIRE(previous.source_tag<=s.source_tag,REPRESENTATION_EQUATION,ORDER);
            if(previous.source_tag==s.source_tag){if(s.source_tag==1){TRY(string_cmp(c,previous.source_reference,s.source_reference,&cmp));REQUIRE(cmp<0,REPRESENTATION_EQUATION,ORDER);}
                else { if(s.source_tag==2){ REQUIRE(previous.source_type<s.source_type,REPRESENTATION_EQUATION,ORDER); }
                else { REQUIRE_N(previous.source_scheme<s.source_scheme||(previous.source_scheme==s.source_scheme&&previous.source_type<s.source_type),REPRESENTATION_EQUATION,ORDER,3); } }}}
        if(s.source_tag==1){unsigned char first;int is_bool,is_i64;TRY(pool_byte(c,s.source_reference,&first));TRY(string_is(c,s.source_reference,"#bool",&is_bool));TRY(string_is(c,s.source_reference,"#i64",&is_i64));
            REQUIRE(st.scope==N,REPRESENTATION_EQUATION,EQUATION);
            if(s.kind==5){REQUIRE_N(first=='@'&&t.tag==3&&c->w->type_scope_mask[t.id]==0,REPRESENTATION_EQUATION,EQUATION,3);}
            else {REQUIRE_N(t.tag==1&&t.atom==s.source_reference,REPRESENTATION_EQUATION,EQUATION,2);
                REQUIRE_N(s.kind==(is_bool?2u:is_i64?1u:first=='%'?4u:3u),REPRESENTATION_EQUATION,EQUATION,2);
                REQUIRE_N(first!='@'&&first!='^'&&(first!='#'||is_bool||is_i64),REPRESENTATION_EQUATION,EQUATION,3);}}
        else { if(s.source_tag==2){REQUIRE_N(s.kind==5&&st.type==s.source_type&&st.scope==N&&t.tag==3&&c->w->type_scope_mask[t.id]==0,REPRESENTATION_EQUATION,EQUATION,5);++canonical;}
        else {Ir8PacketScheme scheme;uint32_t result;TRY(row(c,3,s.source_scheme,&scheme));TRY(scope_type(c,s.source_type,s.source_scheme));TRY(resolution(c,s.source_type,scheme.neutral_env,&result,0));
            REQUIRE_N(s.kind==6&&st.type==s.source_type&&st.scope==s.source_scheme&&(t.tag==2||t.tag==3)&&result==st.type,REPRESENTATION_EQUATION,EQUATION,6);++open;} }
        if(t.tag==3){Ir8PacketCallableContract ct;TRY(ref(c,st.contract,2,0));TRY(row(c,2,st.contract,&ct));EQ(ct.type,t.id,REPRESENTATION_EQUATION);}
        else { EQ(st.contract,N,REPRESENTATION_EQUATION); }
        ready=s.kind==1||s.kind==2?1:s.kind==3?2:s.kind==4?3:s.kind==5?4:t.tag==3?4:5;
        EQ(rep.ready_kind,ready,REPRESENTATION_EQUATION);
        if(s.kind==5){Ir8PacketShapeTyping a,b;TRY(row(c,8,s.argument_rep,&a));TRY(row(c,8,s.result_rep,&b));
            REQUIRE_N(a.type==t.argument&&b.type==t.result&&a.scope==N&&b.scope==N,REPRESENTATION_EQUATION,EQUATION,4);
            if(s.source_tag==2){Ir8PacketType ta,tb;uint32_t ra,rb;TRY(row(c,1,t.argument,&ta));TRY(row(c,1,t.result,&tb));
                TRY(shape_find(c,ta.tag==1?1:2,ta.tag==1?ta.atom:ta.id,N,&ra));TRY(shape_find(c,tb.tag==1?1:2,tb.tag==1?tb.atom:tb.id,N,&rb));
                REQUIRE_N(s.argument_rep==ra&&s.result_rep==rb,REPRESENTATION_EQUATION,EQUATION,2);}}
        TRY(charge(c,sizeof(s)));memcpy(&previous,&s,sizeof(s));
    }
    {uint32_t ncanonical=0,nopen=0;
    for(i=0;i<c->t.table[0].count;++i){Ir8PacketType t;uint32_t id;TRY(row(c,1,i,&t));
        if(t.tag==1){ TRY(shape_find(c,1,t.atom,N,&id)); }
        else { if(t.tag==3&&c->w->type_scope_mask[i]==0){TRY(shape_find(c,2,i,N,&id));++ncanonical;} }}
    for(i=0;i<c->t.table[11].count;++i){Ir8PacketTypeResolution r;Ir8PacketRepresentationResolution rr;Ir8PacketEnv e;Ir8PacketType t,out;uint32_t expected;
        TRY(row(c,12,i,&r));TRY(row(c,13,i,&rr));TRY(row(c,4,r.env,&e));TRY(row(c,1,r.type,&t));TRY(row(c,1,r.result,&out));
        REQUIRE_N(rr.type==r.type&&rr.env==r.env,REPRESENTATION_EQUATION,EQUATION,2);
        if(e.mode==2&&(t.tag==2||t.tag==3)){TRY(shape_find(c,3,e.scheme,t.id,&expected));++nopen;}
        else { TRY(shape_find(c,out.tag==1?1:2,out.tag==1?out.atom:out.id,N,&expected)); }
        EQ(rr.representation,expected,REPRESENTATION_EQUATION);}
    REQUIRE_N(canonical==ncanonical&&open==nopen,REPRESENTATION_EQUATION,COUNT,2);}
    return 1;
}
static int principal_env(Check *c,uint32_t scope,uint32_t *env) {
    if(scope==N){ *env=0; }else{Ir8PacketScheme s;TRY(row(c,3,scope,&s));*env=s.neutral_env;}return 1;
}
static int lawful(Check *c,uint32_t scope,uint32_t env,int *yes) {
    Ir8PacketEnv e;TRY(row(c,4,env,&e));TRY(charge(c,1));*yes=scope==N?env==0:e.scheme==scope;return 1;
}
static int check_codes(Check *c) {
    uint32_t i,execution=0,j,eid;
    for(i=0;i<c->t.table[4].count;++i){Ir8PacketCodeTyping code;at(c,5,c->t.table[4].object,i,N);TRY(row(c,5,i,&code));
        if(i){Ir8PacketCodeTyping p;int cmp;TRY(row(c,5,i-1,&p));REQUIRE(p.kind<=code.kind,ORIGIN_EQUATION,ORDER);
            if(p.kind==code.kind){TRY(string_cmp(c,p.name,code.name,&cmp));REQUIRE(cmp<0,ORIGIN_EQUATION,ORDER);}}
        TRY(scope_type(c,code.result,code.scope));
        if(code.kind==1){Ir8PacketType t;TRY(row(c,1,code.callable_type,&t));TRY(scope_type(c,code.callable_type,code.scope));
            REQUIRE_N(t.tag==3&&t.argument==code.argument&&t.result==code.result&&t.protocol==code.expected_protocol&&code.expected_identity_flag==(t.result_identity==2),ORIGIN_EQUATION,EQUATION,6);}
        for(j=0;j<code.captures.count;++j){Ir8PacketCaptureTyping capture;TRY(vector_read(c,code.captures,24,j,&capture));TRY(scope_type(c,capture.type,code.scope));}
        for(eid=0;eid<c->t.table[3].count;++eid){int yes;Ir8PacketCodeExecution ex;uint32_t result;
            TRY(lawful(c,code.scope,eid,&yes));if(!yes){ continue; }
            TRY(row(c,6,execution,&ex));REQUIRE_N(ex.code==i&&ex.env==eid&&ex.captures.count==code.captures.count,ORIGIN_EQUATION,EQUATION,3);
            TRY(resolution(c,code.result,eid,&result,0));EQ(ex.result,result,ORIGIN_EQUATION);
            if(code.kind==1){TRY(resolution(c,code.callable_type,eid,&result,0));EQ(ex.callable_type,result,ORIGIN_EQUATION);TRY(resolution(c,code.argument,eid,&result,0));EQ(ex.argument,result,ORIGIN_EQUATION);}
            else { REQUIRE_N(ex.callable_type==N&&ex.argument==N,ORIGIN_EQUATION,NULL_DOMAIN,2); }
            for(j=0;j<code.captures.count;++j){Ir8PacketCaptureTyping a;Ir8PacketResolvedCapture b;TRY(vector_read(c,code.captures,24,j,&a));TRY(vector_read(c,ex.captures,25,j,&b));TRY(resolution(c,a.type,eid,&result,0));
                REQUIRE_N(b.code==i&&b.position==j&&b.type==result,ORIGIN_EQUATION,EQUATION,3);}
            ++execution;
        }
    }
    REQUIRE_N(execution==c->t.table[5].count,ORIGIN_EQUATION,COUNT,1);return 1;
}
static int code_execution_find(Check *c,uint32_t code,uint32_t env,uint32_t *id) {
    uint32_t lo=0,hi=c->t.table[5].count;Ir8PacketCodeExecution e;
    while(lo<hi){uint32_t m=lo+(hi-lo)/2;TRY(row(c,6,m,&e));TRY(charge(c,2));if(e.code<code||(e.code==code&&e.env<env)){ lo=m+1; }else { hi=m; }}
    REQUIRE_N(lo<c->t.table[5].count,ORIGIN_EQUATION,MISSING,1);TRY(row(c,6,lo,&e));REQUIRE_N(e.code==code&&e.env==env,ORIGIN_EQUATION,MISSING,2);*id=lo;return 1;
}
static int check_intros_uses(Check *c) {
    uint32_t i,j,result;
    REQUIRE_N(c->t.table[2].count==c->t.table[17].count,ORIGIN_EQUATION,COUNT,1);
    for(i=0;i<c->t.table[17].count;++i){Ir8PacketIntro intro;Ir8PacketScheme s;Ir8PacketSiteRef sr;Ir8PacketSite site;
        at(c,18,c->t.table[17].object,i,N);TRY(row(c,18,i,&intro));TRY(row(c,3,intro.scheme,&s));
        REQUIRE_N(s.intro==i&&intro.body_type==s.body&&intro.result_sites.count==1,ORIGIN_EQUATION,EQUATION,3);
        if(intro.container_tag==2){Ir8PacketCodeTyping code;TRY(row(c,5,intro.container_code,&code));EQ(code.scope,N,ORIGIN_EQUATION);}
        TRY(vector_read(c,intro.result_sites,26,0,&sr));TRY(row(c,14,sr.row,&site));
        REQUIRE_N(site.context_tag==2&&site.context_intro==i&&site.scope==intro.scheme&&site.principal_type==s.body&&site.category!=4,ORIGIN_EQUATION,EQUATION,5);
        TRY(resolution(c,s.body,s.neutral_env,&result,0));EQ(result,s.body,ORIGIN_EQUATION);
    }
    for(i=0;i<c->t.table[18].count;++i){Ir8PacketUse u;Ir8PacketEnv e;Ir8PacketScheme s;
        at(c,19,c->t.table[18].object,i,N);TRY(row(c,19,i,&u));TRY(row(c,4,u.env,&e));TRY(row(c,3,u.scheme,&s));
        REQUIRE_N(e.mode==3&&e.scheme==u.scheme&&u.occurrences.count>0,ORIGIN_EQUATION,EQUATION,3);
        TRY(resolution(c,s.body,u.env,&result,0));EQ(u.result_type,result,ORIGIN_EQUATION);
        if(i){Ir8PacketUse p;int cmp;TRY(row(c,19,i-1,&p));TRY(string_cmp(c,p.name,u.name,&cmp));REQUIRE(cmp<0,ORIGIN_EQUATION,ORDER);}
    }
    for(i=1;i<c->t.table[3].count;++i){Ir8PacketEnv e;int found=0;TRY(row(c,4,i,&e));if(e.mode!=3){ continue; }
        for(j=0;j<c->t.table[18].count;++j){Ir8PacketUse u;TRY(row(c,19,j,&u));TRY(charge(c,1));if(u.env==i){found=1;break;}}
        REQUIRE(found,ORIGIN_EQUATION,MISSING);}
    return 1;
}
static int slice(Check *c,uint32_t object,uint32_t first,uint32_t count,uint32_t domain) {
    if(!count){REQUIRE_N(object==N&&first==0,ORIGIN_EQUATION,NULL_DOMAIN,2);return 1;}
    REQUIRE_N(domain>=1&&domain<=6&&object==c->t.descriptor[domain-1].object,ORIGIN_EQUATION,REFERENCE,3);
    REQUIRE_N(first<=c->t.descriptor[domain-1].count&&count<=c->t.descriptor[domain-1].count-first,ORIGIN_EQUATION,COUNT,2);return 1;
}
static int family_shape(Check *c,uint32_t shape,uint32_t *id) {
    uint32_t lo=0,hi=c->t.table[10].count;Ir8PacketFamilyTyping f;
    while(lo<hi){uint32_t m=lo+(hi-lo)/2;TRY(row(c,11,m,&f));TRY(charge(c,1));if(f.shape<shape){ lo=m+1; }else { hi=m; }}
    REQUIRE_N(lo<c->t.table[10].count,ORIGIN_EQUATION,MISSING,1);TRY(row(c,11,lo,&f));EQ(f.shape,shape,ORIGIN_EQUATION);*id=lo;return 1;
}
static int check_nominal_fields(Check *c) {
    uint32_t i;Ir8PacketNominalField prev={0};
    for(i=0;i<c->t.table[9].count;++i){Ir8PacketNominalField f;Ir8PacketShapeBinding s;Ir8PacketShapeTyping rep;Ir8PacketType t;int same=0;
        at(c,10,c->t.table[9].object,i,N);TRY(row(c,10,i,&f));TRY(row(c,7,f.shape,&s));TRY(row(c,8,f.declared_rep,&rep));TRY(row(c,1,f.type,&t));
        REQUIRE_N((s.kind==3&&f.variant==N)||(s.kind==4&&f.variant!=N),ORIGIN_EQUATION,NULL_DOMAIN,4);
        REQUIRE_N(c->w->type_scope_mask[f.type]==0&&rep.type==f.type&&rep.scope==N,ORIGIN_EQUATION,EQUATION,3);
        if(i){uint32_t a=prev.variant==N?0:prev.variant+1,b=f.variant==N?0:f.variant+1;
            REQUIRE_N(prev.shape<f.shape||(prev.shape==f.shape&&(a<b||(a==b&&prev.position<f.position))),ORIGIN_EQUATION,ORDER,5);
            same=prev.shape==f.shape&&prev.variant==f.variant;}
        EQ(f.position,same?prev.position+1:0,ORIGIN_EQUATION);
        if(s.kind==3&&same){int cmp;TRY(string_cmp(c,prev.name,f.name,&cmp));REQUIRE(cmp<0,ORIGIN_EQUATION,ORDER);}
        if(s.kind==4){Ir8PacketFamilyTyping fam;Ir8PacketVariantTyping v;uint32_t fid,n=0;int yes;
            TRY(family_shape(c,f.shape,&fid));TRY(row(c,11,fid,&fam));REQUIRE_N(f.variant<fam.variants.count&&t.tag==1,ORIGIN_EQUATION,EQUATION,2);
            {int ib,ii;unsigned char ch;TRY(string_is(c,t.atom,"#bool",&ib));TRY(string_is(c,t.atom,"#i64",&ii));TRY(pool_byte(c,t.atom,&ch));REQUIRE(ib||ii||ch=='%',ORIGIN_EQUATION,EQUATION);}
            TRY(vector_read(c,fam.variants,28,f.variant,&v));REQUIRE(f.position<v.fields.count,ORIGIN_EQUATION,REFERENCE);
            TRY(key_number(c,c->w->canonical_key[0],&n,f.position));TRY(string_is(c,f.name,(const char *)c->w->canonical_key[0],&yes));REQUIRE(yes,ORIGIN_EQUATION,EQUATION);}
        TRY(charge(c,sizeof(f)));memcpy(&prev,&f,sizeof(f));
    }
    return 1;
}
static int check_descriptors(Check *c) {
    uint32_t i,j,k,variant_id=0,capture_id=0,field_seen=0,data_shapes=0,sum_shapes=0,bool_shapes=0,int_shapes=0;
    REQUIRE_N(c->t.descriptor[0].count==c->t.table[6].count&&c->t.descriptor[1].count==c->t.table[4].count&&c->t.descriptor[2].count==c->t.table[10].count&&c->t.descriptor[4].count==c->t.table[9].count,ORIGIN_EQUATION,COUNT,4);
    /* Fields are a partition by exact shape and variant, verified below. */
    for(i=0;i<c->t.table[6].count;++i){Ir8PacketShapeBinding s;Ir8PacketShapeSpec spec;uint32_t first=0,count=0;
        at(c,1,c->t.descriptor[0].object,i,N);TRY(row(c,7,i,&s));TRY(descriptor(c,1,i,&spec));
        REQUIRE_N(spec.shape==i&&spec.typing==i&&spec.representation==i&&spec.kind==s.kind&&spec.argument_rep==s.argument_rep&&spec.result_rep==s.result_rep,ORIGIN_EQUATION,EQUATION,6);
        if(s.kind==1){ ++int_shapes; }if(s.kind==2){ ++bool_shapes; }if(s.kind==4){ ++sum_shapes; }
        if(s.kind==3){uint32_t object;Ir8PacketObjectDirectoryEntry d;Ir8PacketSpan v;++data_shapes;
            for(j=0;j<c->t.table[9].count;++j){Ir8PacketNominalField f;TRY(row(c,10,j,&f));TRY(charge(c,1));if(f.shape==i){if(!count){ first=j; }++count;}}
            TRY(find_object(c,5,9,i,N,&object));TRY(directory(c,object,&d));v.object=d.count?object:N;v.count=d.count;REQUIRE(v.count<=4096,COUNT_LIMIT,LIMIT);TRY(vector(c,v,9,i,N));EQ(v.count,count,ORIGIN_EQUATION);
            for(j=0;j<count;++j){Ir8PacketNominalFieldRef r;Ir8PacketNominalField f;Ir8PacketFieldSpec fs;
                TRY(vector_read(c,v,30,j,&r));EQ(r.row,first+j,ORIGIN_EQUATION);TRY(row(c,10,r.row,&f));TRY(descriptor(c,5,r.row,&fs));
                REQUIRE_N(fs.owner_kind==1&&fs.owner==i&&fs.position==j&&fs.name==f.name&&fs.type==f.type&&fs.nominal_declared_rep==f.declared_rep&&fs.code_principal_rep==N&&fs.relation==N,ORIGIN_EQUATION,EQUATION,8);++field_seen;}
        }
        TRY(slice(c,spec.fields_object,spec.field_first,spec.field_count,5));
        REQUIRE_N(spec.field_count==count&&spec.field_first==(count?first:0),ORIGIN_EQUATION,EQUATION,2);
    }
    REQUIRE_N(int_shapes==1&&bool_shapes==1&&sum_shapes==c->t.table[10].count,ORIGIN_EQUATION,COUNT,3);
    for(i=0;i<c->t.table[10].count;++i){Ir8PacketFamilyTyping f;Ir8PacketFamilySpec spec;Ir8PacketShapeBinding shape;
        at(c,3,c->t.descriptor[2].object,i,N);TRY(row(c,11,i,&f));TRY(descriptor(c,3,i,&spec));TRY(row(c,7,f.shape,&shape));
        REQUIRE_N(shape.kind==4&&shape.source_tag==1&&spec.family==i&&spec.shape==f.shape&&spec.variants.count==f.variants.count,ORIGIN_EQUATION,EQUATION,5);
        {unsigned char percent;int cmp;TRY(pool_byte(c,shape.source_reference,&percent));EQ(percent,'%',ORIGIN_EQUATION);
            /* Compare suffix without pretending it is a separate pool start. */
            uint32_t a=shape.source_reference+1,b=f.name;for(;;){unsigned char x,y;TRY(pool_byte(c,a++,&x));TRY(pool_byte(c,b++,&y));EQ(x,y,ORIGIN_EQUATION);if(!x){ break; }}
            if(i){Ir8PacketFamilyTyping prev;TRY(row(c,11,i-1,&prev));TRY(string_cmp(c,prev.name,f.name,&cmp));REQUIRE_N(cmp<0&&prev.shape<f.shape,ORIGIN_EQUATION,ORDER,2);}}
        for(j=0;j<f.variants.count;++j){Ir8PacketVariantTyping v;Ir8PacketVariantRef vr;Ir8PacketVariantSpec vs;uint32_t first=0;
            TRY(vector_read(c,f.variants,28,j,&v));TRY(vector_read(c,spec.variants,29,j,&vr));EQ(vr.row,variant_id,ORIGIN_EQUATION);TRY(descriptor(c,4,variant_id,&vs));
            REQUIRE_N(vs.family==i&&vs.index==j&&vs.name==v.name&&vs.shape==f.shape,ORIGIN_EQUATION,EQUATION,4);
            for(k=0;k<j;++k){Ir8PacketVariantTyping prior;TRY(vector_read(c,f.variants,28,k,&prior));REQUIRE(prior.name!=v.name,ORIGIN_EQUATION,DUPLICATE);}
            for(k=0;k<v.fields.count;++k){Ir8PacketNominalFieldRef nr;Ir8PacketNominalField nf;Ir8PacketFieldSpec fs;
                TRY(vector_read(c,v.fields,30,k,&nr));TRY(row(c,10,nr.row,&nf));TRY(descriptor(c,5,nr.row,&fs));if(k==0){ first=nr.row; }
                REQUIRE_N(nr.row==first+k&&nf.shape==f.shape&&nf.variant==j&&nf.position==k,ORIGIN_EQUATION,EQUATION,4);
                REQUIRE_N(fs.owner_kind==2&&fs.owner==variant_id&&fs.position==k&&fs.name==nf.name&&fs.type==nf.type&&fs.nominal_declared_rep==nf.declared_rep&&fs.code_principal_rep==N&&fs.relation==N,ORIGIN_EQUATION,EQUATION,8);++field_seen;}
            TRY(slice(c,vs.fields_object,vs.field_first,vs.field_count,5));REQUIRE_N(vs.field_first==(v.fields.count?first:0)&&vs.field_count==v.fields.count,ORIGIN_EQUATION,EQUATION,2);++variant_id;}
    }
    REQUIRE_N(variant_id==c->t.descriptor[3].count&&field_seen==c->t.table[9].count,ORIGIN_EQUATION,COUNT,2);
    for(i=0;i<c->t.table[4].count;++i){Ir8PacketCodeTyping code;Ir8PacketCodeSpec spec;uint32_t env,result,rep;
        at(c,2,c->t.descriptor[1].object,i,N);TRY(row(c,5,i,&code));TRY(descriptor(c,2,i,&spec));TRY(principal_env(c,code.scope,&env));
        TRY(resolution(c,code.kind==1?code.callable_type:code.result,env,&result,&rep));
        REQUIRE_N(spec.code==i&&spec.principal_env==env&&spec.principal_rep==rep,ORIGIN_EQUATION,EQUATION,3);
        REQUIRE(spec.body_binding==1,ORIGIN_EQUATION,BODY_BINDING);TRY(slice(c,spec.capture_object,spec.capture_first,spec.capture_count,6));
        REQUIRE_N(spec.capture_count==code.captures.count&&spec.capture_first==(code.captures.count?capture_id:0),ORIGIN_EQUATION,EQUATION,2);
        for(j=0;j<code.captures.count;++j){Ir8PacketCaptureTyping cap;Ir8PacketFieldSpec fs;TRY(vector_read(c,code.captures,24,j,&cap));TRY(descriptor(c,6,capture_id,&fs));TRY(resolution(c,cap.type,env,&result,&rep));
            REQUIRE_N(fs.owner_kind==3&&fs.owner==i&&fs.position==j&&fs.name==cap.name&&fs.type==cap.type&&fs.nominal_declared_rep==N&&fs.code_principal_rep==rep&&fs.relation==cap.relation,ORIGIN_EQUATION,EQUATION,8);++capture_id;}
    }
    EQ(capture_id,c->t.descriptor[5].count,ORIGIN_EQUATION);(void)data_shapes;return 1;
}
static int site_lawful(Check *c,const Ir8PacketSite *s,uint32_t env,int *yes) {
    if(s->context_tag==2){Ir8PacketIntro intro;Ir8PacketScheme scheme;TRY(row(c,18,s->context_intro,&intro));TRY(row(c,3,intro.scheme,&scheme));TRY(charge(c,1));*yes=env==scheme.neutral_env;return 1;}
    return lawful(c,s->scope,env,yes);
}
static int check_sites(Check *c) {
    uint32_t i,eid,execution=0;
    for(i=0;i<c->t.table[13].count;++i){Ir8PacketSite s;at(c,14,c->t.table[13].object,i,N);TRY(row(c,14,i,&s));TRY(scope_type(c,s.principal_type,s.scope));
        if(s.context_tag==1){ EQ(s.scope,N,ORIGIN_EQUATION); }
        else { if(s.context_tag==2){Ir8PacketIntro intro;TRY(row(c,18,s.context_intro,&intro));EQ(s.scope,intro.scheme,ORIGIN_EQUATION);}
        else {Ir8PacketCodeTyping code;TRY(row(c,5,s.context_code,&code));REQUIRE_N(s.scope==s.context_scheme&&code.scope==s.scope,ORIGIN_EQUATION,EQUATION,2);} }
        if(s.code!=N){Ir8PacketCodeTyping code;TRY(row(c,5,s.code,&code));
            REQUIRE_N(code.scope==s.scope&&code.kind==(s.category==2?1u:2u)&&s.principal_type==(s.category==2?code.callable_type:code.result),ORIGIN_EQUATION,EQUATION,5);}
        if(s.category==7){Ir8PacketFamilyTyping f;Ir8PacketShapeTyping st;TRY(row(c,11,s.sum_family,&f));TRY(row(c,8,f.shape,&st));
            REQUIRE_N(s.sum_variant<f.variants.count&&st.type==s.principal_type,ORIGIN_EQUATION,EQUATION,2);}
        for(eid=0;eid<c->t.table[3].count;++eid){int yes;Ir8PacketSiteExecution ex;Ir8PacketEnv env;Ir8PacketRepresentation representation;Ir8PacketShapeTyping typing;uint32_t result,rep,ce=N;
            TRY(site_lawful(c,&s,eid,&yes));if(!yes){ continue; }TRY(row(c,15,execution,&ex));TRY(row(c,4,eid,&env));
            TRY(resolution(c,s.principal_type,eid,&result,&rep));
            if(env.mode==1&&s.legacy_physical!=N){ TRY(shape_find(c,1,s.legacy_physical,N,&rep)); }
            if(s.code!=N){ TRY(code_execution_find(c,s.code,eid,&ce)); }
            REQUIRE_N(ex.site==i&&ex.env==eid&&ex.origin_kind==env.mode&&ex.principal_type==result&&ex.representation==rep&&ex.code_execution==ce,ORIGIN_EQUATION,EQUATION,6);
            TRY(row(c,9,rep,&representation));TRY(row(c,8,rep,&typing));EQ(typing.type,result,REPRESENTATION_EQUATION);
            if(s.category==1||s.category==2||s.category==6||s.category==7){uint32_t ready=s.category==1?2:s.category==2?4:s.category==6?1:3;EQ(representation.ready_kind,ready,REPRESENTATION_EQUATION);}
            ++execution;
        }
    }
    EQ(execution,c->t.table[14].count,ORIGIN_EQUATION);return 1;
}
static int expect_slot(Check *c,uint32_t *cursor,uint32_t site,uint32_t role,uint32_t name,uint32_t variant,uint32_t field,uint32_t type,uint32_t relation) {
    Ir8PacketSlot s;Ir8PacketSite owner;uint32_t e,result;int yes;
    at(c,16,c->t.table[15].object,*cursor,N);TRY(row(c,16,*cursor,&s));
    REQUIRE_N(s.site==site&&s.role_tag==role&&s.role_name==name&&s.role_variant==variant&&s.role_field==field&&s.type==type&&s.relation==relation,EDGE_EQUATION,EQUATION,7);
    TRY(row(c,14,site,&owner));TRY(scope_type(c,type,owner.scope));
    for(e=0;e<c->t.table[3].count;++e){TRY(site_lawful(c,&owner,e,&yes));if(yes){ TRY(resolution(c,type,e,&result,0)); }}
    ++*cursor;return 1;
}
static int check_slots(Check *c) {
    uint32_t site,cursor=0,j;
    for(site=0;site<c->t.table[13].count;++site){Ir8PacketSite s;TRY(row(c,14,site,&s));
        if(s.category==2||s.category==3){Ir8PacketCodeTyping code;TRY(row(c,5,s.code,&code));
            for(j=0;j<code.captures.count;++j){Ir8PacketCaptureTyping cap;TRY(vector_read(c,code.captures,24,j,&cap));TRY(expect_slot(c,&cursor,site,1,cap.name,N,N,cap.type,cap.relation));}}
        else { if(s.category==1){Ir8PacketType type;uint32_t shape;TRY(row(c,1,s.principal_type,&type));REQUIRE(type.tag==1,EDGE_EQUATION,EQUATION);TRY(shape_find(c,1,type.atom,N,&shape));
            for(j=0;j<c->t.table[9].count;++j){Ir8PacketNominalField f;TRY(row(c,10,j,&f));TRY(charge(c,1));if(f.shape==shape){REQUIRE(f.variant==N,EDGE_EQUATION,EQUATION);TRY(expect_slot(c,&cursor,site,2,N,N,j,f.type,2));}}}
        else { if(s.category==7){Ir8PacketFamilyTyping family;Ir8PacketVariantTyping variant;TRY(row(c,11,s.sum_family,&family));TRY(vector_read(c,family.variants,28,s.sum_variant,&variant));
            for(j=0;j<variant.fields.count;++j){Ir8PacketNominalFieldRef r;Ir8PacketNominalField field;TRY(vector_read(c,variant.fields,30,j,&r));TRY(row(c,10,r.row,&field));
                REQUIRE_N(field.shape==family.shape&&field.variant==s.sum_variant&&field.position==j,EDGE_EQUATION,EQUATION,3);
                TRY(expect_slot(c,&cursor,site,3,N,s.sum_variant,r.row,field.type,2));}}
        else { if(s.category==5){Ir8PacketSlot function;Ir8PacketType arrow;TRY(row(c,16,cursor,&function));TRY(row(c,1,function.type,&arrow));
            REQUIRE_N(arrow.tag==3&&arrow.result==s.principal_type,EDGE_EQUATION,EQUATION,2);
            TRY(expect_slot(c,&cursor,site,4,N,N,N,function.type,2));TRY(expect_slot(c,&cursor,site,5,N,N,N,arrow.argument,2));} } } }
        if(s.category==3||s.category==4||s.category==5){ TRY(expect_slot(c,&cursor,site,6,N,N,N,s.principal_type,2)); }
    }
    EQ(cursor,c->t.table[15].count,EDGE_EQUATION);return 1;
}
static int intro_result(Check *c,const Ir8PacketSite *site,int *yes) {
    Ir8PacketIntro intro;Ir8PacketSiteRef r;
    *yes=0;if(site->context_tag!=2){ return 1; }
    TRY(row(c,18,site->context_intro,&intro));TRY(vector_read(c,intro.result_sites,26,0,&r));TRY(charge(c,1));*yes=r.row==site->id;return 1;
}
static int expect_access(Check *c,uint32_t *cursor,uint32_t site,uint32_t origin,uint32_t mode,uint32_t env,uint32_t type,uint32_t scheme) {
    Ir8PacketAccess a;at(c,17,c->t.table[16].object,*cursor,N);TRY(row(c,17,*cursor,&a));
    REQUIRE_N(a.site==site&&a.origin_env==origin&&a.mode==mode&&a.use_env==env&&a.type==type&&a.scheme==scheme,EDGE_EQUATION,EQUATION,6);++*cursor;return 1;
}
static int check_accesses(Check *c) {
    uint32_t i,cursor=0,e,result;
    for(i=0;i<c->t.table[14].count;++i){Ir8PacketSiteExecution ex;Ir8PacketSite site;int yes;
        TRY(row(c,15,i,&ex));TRY(row(c,14,ex.site,&site));
        if(ex.origin_kind==2){
            for(e=0;e<c->t.table[3].count;++e){TRY(lawful(c,site.scope,e,&yes));if(!yes){ continue; }
                TRY(resolution(c,site.principal_type,e,&result,0));TRY(expect_access(c,&cursor,site.id,ex.env,1,e,result,N));}
            TRY(intro_result(c,&site,&yes));if(yes){Ir8PacketScheme scheme;TRY(row(c,3,site.scope,&scheme));TRY(expect_access(c,&cursor,site.id,ex.env,2,N,scheme.body,scheme.id));}
        }else{TRY(resolution(c,site.principal_type,ex.env,&result,0));TRY(expect_access(c,&cursor,site.id,ex.env,1,ex.env,result,N));}
    }
    EQ(cursor,c->t.table[16].count,EDGE_EQUATION);return 1;
}
static int access_find(Check *c,uint32_t site,uint32_t origin,uint32_t env,uint32_t *id) {
    uint32_t lo=0,hi=c->t.table[16].count;Ir8PacketAccess a;
    while(lo<hi){uint32_t m=lo+(hi-lo)/2;int cmp=0;TRY(row(c,17,m,&a));TRY(charge(c,4));
        if(a.site!=site){ cmp=a.site<site?-1:1; }
        else { if(a.origin_env!=origin){ cmp=a.origin_env<origin?-1:1; }
        else { if(a.mode!=1){ cmp=1; }
        else { cmp=a.use_env<env?-1:a.use_env>env?1:0; } } }
        if(cmp<0){ lo=m+1; }else { hi=m; }}
    REQUIRE_N(lo<c->t.table[16].count,EDGE_EQUATION,MISSING,1);TRY(row(c,17,lo,&a));
    REQUIRE_N(a.site==site&&a.origin_env==origin&&a.mode==1&&a.use_env==env&&a.scheme==N,EDGE_EQUATION,MISSING,5);*id=lo;return 1;
}
static int expect_transport(Check *c,uint32_t *cursor,uint32_t source,uint32_t projection,uint32_t result,uint32_t kind) {
    Ir8PacketTransport t;at(c,20,c->t.table[19].object,*cursor,N);TRY(row(c,20,*cursor,&t));
    REQUIRE_N(t.source_access==source&&t.projection_env==projection&&t.result_access==result&&t.kind==kind,EDGE_EQUATION,EQUATION,4);++*cursor;return 1;
}
static int check_transports(Check *c) {
    uint32_t i,e,cursor=0,target;
    for(i=0;i<c->t.table[16].count;++i){Ir8PacketAccess a;Ir8PacketEnv origin;TRY(row(c,17,i,&a));if(a.mode!=1){ continue; }
        TRY(expect_transport(c,&cursor,i,N,i,1));TRY(row(c,4,a.origin_env,&origin));
        if(origin.mode!=2||a.use_env!=a.origin_env){ continue; }
        for(e=0;e<c->t.table[3].count;++e){Ir8PacketEnv projection;TRY(row(c,4,e,&projection));TRY(charge(c,2));if(projection.mode!=3||projection.scheme!=origin.scheme){ continue; }
            TRY(access_find(c,a.site,a.origin_env,e,&target));TRY(expect_transport(c,&cursor,i,e,target,2));}
    }
    EQ(cursor,c->t.table[19].count,EDGE_EQUATION);return 1;
}
/* The pool is the exact deduplicated union of the schema's source strings.
 * Stream candidates instead of allocating an uncounted string index. */
static int pool_member(Check *c,uint32_t offset,int *found) {
    uint32_t i,j,k;*found=0;
#define STRING_MATCH(x) do { TRY(charge(c,1)); if((x)==offset){*found=1;return 1;} } while(0)
    for(i=0;i<c->t.table[0].count;++i){Ir8PacketType v;TRY(row(c,1,i,&v));if(v.tag==1){ STRING_MATCH(v.atom); }}
    for(i=0;i<c->t.table[2].count;++i){Ir8PacketScheme v;TRY(row(c,3,i,&v));STRING_MATCH(v.name);}
    for(i=0;i<c->t.table[4].count;++i){Ir8PacketCodeTyping v;TRY(row(c,5,i,&v));STRING_MATCH(v.name);STRING_MATCH(v.body_path);
        for(j=0;j<v.captures.count;++j){Ir8PacketCaptureTyping r;TRY(vector_read(c,v.captures,24,j,&r));STRING_MATCH(r.name);}}
    for(i=0;i<c->t.table[6].count;++i){Ir8PacketShapeBinding v;TRY(row(c,7,i,&v));if(v.source_tag==1){ STRING_MATCH(v.source_reference); }}
    for(i=0;i<c->t.table[9].count;++i){Ir8PacketNominalField v;TRY(row(c,10,i,&v));STRING_MATCH(v.name);}
    for(i=0;i<c->t.table[10].count;++i){Ir8PacketFamilyTyping v;TRY(row(c,11,i,&v));STRING_MATCH(v.name);
        for(j=0;j<v.variants.count;++j){Ir8PacketVariantTyping r;TRY(vector_read(c,v.variants,28,j,&r));STRING_MATCH(r.name);}}
    for(i=0;i<c->t.table[13].count;++i){Ir8PacketSite v;TRY(row(c,14,i,&v));STRING_MATCH(v.path);if(v.legacy_physical!=N){ STRING_MATCH(v.legacy_physical); }}
    for(i=0;i<c->t.table[17].count;++i){Ir8PacketIntro v;TRY(row(c,18,i,&v));STRING_MATCH(v.generalize_path);STRING_MATCH(v.seal_path);}
    for(i=0;i<c->t.table[18].count;++i){Ir8PacketUse v;TRY(row(c,19,i,&v));STRING_MATCH(v.name);
        for(k=0;k<v.occurrences.count;++k){Ir8PacketPathRef r;TRY(vector_read(c,v.occurrences,27,k,&r));STRING_MATCH(r.path);}}
#undef STRING_MATCH
    return 1;
}
static int pool_census(Check *c) {
    uint32_t off=0;while(off<c->pool.count){int found;unsigned char byte;TRY(pool_member(c,off,&found));REQUIRE(found,DIRECTORY,EXTRA);
        do {TRY(pool_byte(c,off++,&byte));}while(byte);}
    return 1;
}

static int final_census(Check *c) {
    uint32_t i;
    TRY(pool_census(c));
    for(i=0;i<c->h.directory_count;++i){at(c,N,i,N,N);TRY(charge(c,1));REQUIRE_N(c->w->directory_seen[i]==1,DIRECTORY,EXTRA,1);}
    at(c,N,N,N,N);return 1;
}
static void report_init(Ir8PacketReport *r) {
    r->status=S(ARGUMENT);r->phase=P(ARGUMENTS);r->domain=N;r->object=N;r->row=N;r->field=N;r->detail=D(NULL_ARGUMENT);
    r->packet_bytes=0;r->declared_packet_alignment=0;r->member_bytes_sum=0;r->padding_bytes=0;
    r->directory_entries=0;r->member_objects=0;r->resolution_access_transport_rows=0;r->work_used=0;
    r->workspace_bytes=0;r->graph_executed=0;r->source_admitted=0;r->runtime_admitted=0;r->runtime_guards_executed=0;
}
Ir8PacketStatus ir8_packet_validate(const void *root,size_t root_bytes,
    const Ir8PacketExpectedBindings *expected,Ir8PacketWorkspace *workspace,Ir8PacketReport *report) {
    Check c;uint32_t i;static const unsigned char magic[8]={'I','R','8','P','K','T','0','1'};
    if(!report){ return S(ARGUMENT); }report_init(report);
    if(!root){report->field=0;return S(ARGUMENT);}
    if(!expected){report->field=1;return S(ARGUMENT);}
    if(!workspace){report->field=2;return S(ARGUMENT);}
    report->phase=P(HEADER_AND_SIZE);
    if(root_bytes<sizeof(Ir8PacketProgramHeader)){report->status=S(HEADER);report->detail=D(LENGTH);return report->status;}
    if(root_bytes>IR8_PACKET_MAX_BYTES){report->status=S(SIZE_LIMIT);report->detail=D(LIMIT);return report->status;}
    c.root=(const unsigned char *)root;c.bytes=root_bytes;c.w=workspace;c.r=report;
    if(!charge(&c,sizeof(*workspace))){ return report->status; }
    memset(workspace,0,sizeof(*workspace));report->workspace_bytes=(uint32_t)sizeof(*workspace);
    if(!copy(&c,0,sizeof(c.h),&c.h)){ goto done; }
    for(i=0;i<8;++i){report->field=0;if(!charge(&c,3)){ goto done; }if(c.h.magic[i]!=magic[i]){bad(&c,S(HEADER),D(MAGIC));goto done;}}
    report->field=1;if(!charge(&c,1)){ goto done; }if(c.h.abi_revision!=1){bad(&c,S(HEADER),D(REVISION));goto done;}
    report->field=2;if(!charge(&c,1)){ goto done; }if(c.h.purpose!=1){bad(&c,S(HEADER),D(PURPOSE));goto done;}
    report->field=3;if(!charge(&c,1)){ goto done; }if(c.h.packet_bytes!=root_bytes){bad(&c,S(HEADER),D(LENGTH));goto done;}
    report->packet_bytes=(uint32_t)root_bytes;
    phase(&c,P(DIRECTORY));if(!check_directory(&c)){ goto done; }
    phase(&c,P(MEMBERSHIPS_AND_BINDINGS));if(!check_memberships(&c,expected)){ goto done; }
    phase(&c,P(ROW_DOMAINS));if(!check_row_domains(&c)||!check_payloads(&c)||!check_descriptor_domains(&c)){ goto done; }
    phase(&c,P(TYPES_AND_RESOLUTIONS));if(!check_types(&c)||!check_environments(&c)||!check_resolutions(&c)||!check_shapes(&c)){ goto done; }
    phase(&c,P(ORIGINS_AND_DESCRIPTORS));if(!check_codes(&c)||!check_intros_uses(&c)||!check_nominal_fields(&c)||!check_descriptors(&c)||!check_sites(&c)){ goto done; }
    phase(&c,P(SLOTS_ACCESS_TRANSPORTS));if(!check_slots(&c)||!check_accesses(&c)||!check_transports(&c)){ goto done; }
    phase(&c,P(FINAL_CENSUS));if(!final_census(&c)){ goto done; }
    report->status=S(OK);report->detail=D(NONE);
done:
    workspace->work_used=report->work_used;return report->status;
}
