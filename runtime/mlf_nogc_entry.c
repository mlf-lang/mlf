/* Restricted entry arena. Production activation is disabled by default.
 * Positive ceilings are specific to a separately reviewed embedding profile. */
#include "mlf_nogc_entry.h"
#include <limits.h>
#include <setjmp.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#ifndef MLF_NG0_PROFILE_QUALIFIED
#define MLF_NG0_PROFILE_QUALIFIED 0
#endif
#ifndef MLF_NG0_CAPACITY_CEILING
#define MLF_NG0_CAPACITY_CEILING 0
#endif
#ifndef MLF_NG0_DEPTH_CEILING
#define MLF_NG0_DEPTH_CEILING 0
#endif

typedef enum { HOLE=0, BUSY=1, INDIRECT=2, THUNK=3, APPLICATION=4,
    CLOSURE=5, INTEGER=6, BOOLEAN=7, CONSTRUCTOR=9, PRIMITIVE=10,
    CONSTRUCTOR_1=12, CONSTRUCTOR_2=13 } Tag;
struct MlfNg0Env { size_t count; MlfNg0Value *slots[]; };
struct MlfNg0Value {
    Tag tag;
    union {
        MlfNg0Value *indirect;
        struct { MlfNg0Code code; MlfNg0Env *env; } closure;
        struct { MlfNg0Value *function, *argument; } application;
        int64_t integer;
        struct { int64_t identity, arity; MlfNg0Env *fields; } constructor;
        struct { int64_t identity; MlfNg0Value *fields[2]; } packed;
        struct { int32_t identity; MlfNg0Env *arguments; } primitive;
    } as;
};
_Static_assert(sizeof(void *)==8 && sizeof(size_t)==8 && CHAR_BIT==8, "64-bit ABI");
_Static_assert(sizeof(Tag)==4 && sizeof(MlfNg0Value)==32 && _Alignof(MlfNg0Value)==8, "value layout");
_Static_assert(offsetof(MlfNg0Value,tag)==0 && offsetof(MlfNg0Value,as.indirect)==8, "force layout");
_Static_assert(offsetof(MlfNg0Value,as.closure.code)==8 && offsetof(MlfNg0Value,as.closure.env)==16, "closure layout");
_Static_assert(offsetof(MlfNg0Value,as.packed.identity)==8 && offsetof(MlfNg0Value,as.packed.fields)==16, "packed layout");
_Static_assert(offsetof(MlfNg0Value,as.constructor.fields)==24, "constructor layout");
_Static_assert(offsetof(MlfNg0Env,slots)==8 && sizeof(MlfNg0Env)==8, "environment layout");
_Static_assert(HOLE<CLOSURE && BUSY<CLOSURE && INDIRECT<CLOSURE && THUNK<CLOSURE && APPLICATION<CLOSURE, "WHNF ordering");

typedef struct {
    jmp_buf escape;
    unsigned char *slab;
    size_t used, capacity;
    uint64_t depth, limit;
    MlfNg0Result result;
} Context;
static atomic_flag gate = ATOMIC_FLAG_INIT;
/* Accessed only by the gate owner. Internal helpers are not host-callable. */
static Context *active;

_Noreturn void mlf_ng0_fault(int32_t status) {
    /* Outside-entry helper use violates the closed-link ABI. No target exists. */
    if (!active) abort();
    active->result.status = status >= MLF_NG0_HOST_ALLOCATION && status <= MLF_NG0_INTERNAL_CONTRACT
        ? (MlfNg0Status)status : MLF_NG0_INTERNAL_CONTRACT;
    longjmp(active->escape,1);
}
void mlf_ng0_require_entry_region_v0(void) { if (!active) abort(); }
void mlf_ng0_depth_enter(void) {
    mlf_ng0_require_entry_region_v0();
    if (active->depth >= active->limit) mlf_ng0_fault(MLF_NG0_DEPTH_LIMIT);
    ++active->depth;
    if (active->depth > active->result.depth_high_water) active->result.depth_high_water=active->depth;
}
void mlf_ng0_depth_leave(void) {
    if (!active || !active->depth) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    --active->depth;
}
static void *allocate(size_t n) {
    mlf_ng0_require_entry_region_v0();
    size_t padding=(8-(active->used & 7)) & 7;
    if (padding > active->capacity-active->used || n > active->capacity-active->used-padding)
        mlf_ng0_fault(MLF_NG0_ARENA_LIMIT);
    size_t start=active->used+padding;
    active->used=start+n;
    active->result.padding_bytes+=padding;
    active->result.used_high_water=active->used;
    void *p=active->slab+start;
    memset(p,0,n);
    return p;
}
static MlfNg0Value *node(Tag tag) { MlfNg0Value *p=allocate(sizeof(*p)); p->tag=tag; return p; }
static int immediate(const MlfNg0Value *p) { return ((uintptr_t)p & 7)!=0; }
static int small(const MlfNg0Value *p) { return ((uintptr_t)p & 1)!=0; }
static int boolean(const MlfNg0Value *p) { return (uintptr_t)p==2 || (uintptr_t)p==6; }
static int nullary(const MlfNg0Value *p) { return ((uintptr_t)p & 7)==4; }
static int64_t signed_bits(uint64_t n) { return n<=INT64_MAX ? (int64_t)n : -1-(int64_t)(UINT64_MAX-n); }
static int64_t small_bits(const MlfNg0Value *p) {
    uint64_t b=(uint64_t)(uintptr_t)p;
    return signed_bits((b>>1) | (b & (UINT64_C(1)<<63)));
}
static MlfNg0Value *fixed(int64_t n) {
    if (n>=-(INT64_C(1)<<62) && n<=(INT64_C(1)<<62)-1)
        return (MlfNg0Value *)(uintptr_t)(((uint64_t)n<<1)|1);
    MlfNg0Value *p=node(INTEGER); p->as.integer=n; return p;
}
MlfNg0Env *mlf_ng0_env_new(uint64_t count) {
    if (count>(SIZE_MAX-sizeof(MlfNg0Env))/sizeof(MlfNg0Value *)) mlf_ng0_fault(MLF_NG0_ARENA_LIMIT);
    MlfNg0Env *e=allocate(sizeof(*e)+(size_t)count*sizeof(MlfNg0Value *)); e->count=(size_t)count; return e;
}
void mlf_ng0_env_set(MlfNg0Env *e,uint64_t i,MlfNg0Value *v) {
    if (!e || i>=e->count || !v) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    e->slots[i]=v;
}
MlfNg0Value *mlf_ng0_env_get(MlfNg0Env *e,uint64_t i) {
    if (!e || i>=e->count || !e->slots[i]) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    return e->slots[i];
}
static MlfNg0Env *append(MlfNg0Env *e,MlfNg0Value *v) {
    if (!e || !v) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    if (e->count==SIZE_MAX) mlf_ng0_fault(MLF_NG0_ARENA_LIMIT);
    MlfNg0Env *r=mlf_ng0_env_new(e->count+1);
    memcpy(r->slots,e->slots,e->count*sizeof(*e->slots)); r->slots[e->count]=v; return r;
}
static MlfNg0Value *code_value(Tag t,MlfNg0Code code,MlfNg0Env *env) {
    if (!code) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    MlfNg0Value *p=node(t); p->as.closure.code=code; p->as.closure.env=env; return p;
}
MlfNg0Value *mlf_ng0_closure(MlfNg0Code c,MlfNg0Env *e) { return code_value(CLOSURE,c,e); }
MlfNg0Value *mlf_ng0_thunk(MlfNg0Code c,MlfNg0Env *e) { return code_value(THUNK,c,e); }
MlfNg0Value *mlf_ng0_thunk_new(MlfNg0Code c,uint64_t count) {
    if (!c) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    if (!count) return code_value(THUNK,c,NULL);
    if (count>(SIZE_MAX-32)/8) mlf_ng0_fault(MLF_NG0_ARENA_LIMIT);
    /* Generated captures expect count at byte24 and slots at byte32. */
    MlfNg0Value *p=allocate(32+(size_t)count*8);
    MlfNg0Env *e=(MlfNg0Env *)((unsigned char *)p+24);
    p->tag=THUNK; p->as.closure.code=c; p->as.closure.env=e; e->count=(size_t)count; return p;
}
MlfNg0Value *mlf_ng0_hole(void) { return node(HOLE); }
void mlf_ng0_fill(MlfNg0Value *p,MlfNg0Value *v) {
    if (!p || immediate(p) || p->tag!=HOLE || !v) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    p->tag=INDIRECT; p->as.indirect=v;
}
MlfNg0Value *mlf_ng0_application(MlfNg0Value *f,MlfNg0Value *a) {
    if (!f || !a) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    MlfNg0Value *p=node(APPLICATION); p->as.application.function=f; p->as.application.argument=a; return p;
}
MlfNg0Value *mlf_ng0_integer(const char *s) {
    if (!s) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    int negative=*s=='-'; if (*s=='-' || *s=='+') ++s;
    if (!*s) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    uint64_t bits=0;
    for (;*s;++s) { if (*s<'0' || *s>'9') mlf_ng0_fault(MLF_NG0_INVALID_VALUE); bits=bits*10+(unsigned)(*s-'0'); }
    return fixed(signed_bits(negative ? UINT64_C(0)-bits : bits));
}
MlfNg0Value *mlf_ng0_boolean(int64_t b) { return (MlfNg0Value *)(uintptr_t)(b ? 6 : 2); }
void *mlf_ng0_constructor_allocate(int64_t id,uint64_t n) {
    if (id<0 || n<1 || n>2) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    return allocate(16+(size_t)n*8);
}
MlfNg0Value *mlf_ng0_constructor(int64_t id,int64_t arity) {
    if (id<0 || arity<0 || arity>2) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    if (!arity && id<(INT64_C(1)<<60)) return (MlfNg0Value *)(uintptr_t)(((uint64_t)id<<3)|4);
    MlfNg0Value *p=node(CONSTRUCTOR); p->as.constructor.identity=id; p->as.constructor.arity=arity;
    p->as.constructor.fields=mlf_ng0_env_new(0); return p;
}
MlfNg0Value *mlf_ng0_constructor1(int64_t id,MlfNg0Value *a) {
    if (id<0 || !a) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    MlfNg0Value *p=node(CONSTRUCTOR_1); p->as.packed.identity=id; p->as.packed.fields[0]=a; return p;
}
MlfNg0Value *mlf_ng0_constructor2(int64_t id,MlfNg0Value *a,MlfNg0Value *b) {
    if (id<0 || !a || !b) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    MlfNg0Value *p=node(CONSTRUCTOR_2); p->as.packed.identity=id; p->as.packed.fields[0]=a; p->as.packed.fields[1]=b; return p;
}
MlfNg0Value *mlf_ng0_constructor_fields(int64_t id,MlfNg0Env *e) {
    if (!e || e->count>2) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    if (!e->count) return mlf_ng0_constructor(id,0);
    if (e->count==1) return mlf_ng0_constructor1(id,mlf_ng0_env_get(e,0));
    return mlf_ng0_constructor2(id,mlf_ng0_env_get(e,0),mlf_ng0_env_get(e,1));
}
static size_t arity(int64_t id) {
    if (id==8) return 2;
    if (id==13) return 3;
    mlf_ng0_fault(MLF_NG0_INVALID_PRIMITIVE);
}
MlfNg0Value *mlf_ng0_primitive(int64_t id) {
    (void)arity(id); MlfNg0Value *p=node(PRIMITIVE); p->as.primitive.identity=(int32_t)id;
    p->as.primitive.arguments=mlf_ng0_env_new(0); return p;
}
static int whnf(MlfNg0Value *p) {
    if (!p) return 0;
    if (immediate(p)) return small(p) || boolean(p) || nullary(p);
    return p->tag==CLOSURE || p->tag==INTEGER || p->tag==CONSTRUCTOR || p->tag==PRIMITIVE || p->tag==CONSTRUCTOR_1 || p->tag==CONSTRUCTOR_2;
}
MlfNg0Value *mlf_ng0_peek(MlfNg0Value *p) {
    if (whnf(p)) return p;
    if (p && !immediate(p) && p->tag==INDIRECT && whnf(p->as.indirect)) return p->as.indirect;
    return NULL;
}
static int64_t integer(MlfNg0Value *p) {
    p=mlf_ng0_force(p);
    if (small(p)) return small_bits(p);
    if (immediate(p) || p->tag!=INTEGER) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    return p->as.integer;
}
MlfNg0Value *mlf_ng0_add_int(MlfNg0Value *a,MlfNg0Value *b) {
    int64_t x=integer(a); int64_t y=integer(b); return fixed(signed_bits((uint64_t)x+(uint64_t)y));
}
int64_t mlf_ng0_truth(MlfNg0Value *p) {
    p=mlf_ng0_force(p); if (!boolean(p)) mlf_ng0_fault(MLF_NG0_INVALID_VALUE); return (uintptr_t)p==6;
}
MlfNg0Value *mlf_ng0_prim2(int64_t id,MlfNg0Value *a,MlfNg0Value *b) {
    if (id!=8) mlf_ng0_fault(MLF_NG0_INVALID_PRIMITIVE);
    return mlf_ng0_add_int(a,b);
}
MlfNg0Value *mlf_ng0_prim3(int64_t id,MlfNg0Value *a,MlfNg0Value *b,MlfNg0Value *c) {
    if (id!=13) mlf_ng0_fault(MLF_NG0_INVALID_PRIMITIVE);
    return mlf_ng0_truth(a) ? b : c;
}
static MlfNg0Value *invoke(MlfNg0Code c,MlfNg0Env *e,MlfNg0Value *a) {
    if (!c) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
    mlf_ng0_depth_enter(); MlfNg0Value *r=c(e,a); mlf_ng0_depth_leave(); return r;
}
static MlfNg0Value *apply(MlfNg0Value *f,MlfNg0Value *a) {
    mlf_ng0_depth_enter(); f=mlf_ng0_force(f); MlfNg0Value *r=NULL;
    if (immediate(f)) mlf_ng0_fault(MLF_NG0_INVALID_APPLICATION);
    if (f->tag==CLOSURE) r=invoke(f->as.closure.code,f->as.closure.env,a);
    else if (f->tag==PRIMITIVE) {
        int32_t id=f->as.primitive.identity; size_t n=arity(id);
        MlfNg0Env *e=append(f->as.primitive.arguments,a);
        if (e->count>n) mlf_ng0_fault(MLF_NG0_INVALID_PRIMITIVE);
        if (e->count<n) { r=node(PRIMITIVE); r->as.primitive.identity=id; r->as.primitive.arguments=e; }
        else if (id==8) r=mlf_ng0_prim2(id,e->slots[0],e->slots[1]);
        else r=mlf_ng0_prim3(id,e->slots[0],e->slots[1],e->slots[2]);
    } else if (f->tag==CONSTRUCTOR) {
        MlfNg0Env *e=f->as.constructor.fields; int64_t n=f->as.constructor.arity;
        if (!e || n<1 || n>2 || e->count>=(uint64_t)n) mlf_ng0_fault(MLF_NG0_INVALID_APPLICATION);
        e=append(e,a);
        if (e->count==(uint64_t)n) r=mlf_ng0_constructor_fields(f->as.constructor.identity,e);
        else { r=node(CONSTRUCTOR); r->as.constructor=f->as.constructor; r->as.constructor.fields=e; }
    } else mlf_ng0_fault(MLF_NG0_INVALID_APPLICATION);
    mlf_ng0_depth_leave(); return r;
}
static void memo(MlfNg0Value *p,MlfNg0Value *v) {
    /* Compact thunk captures begin at24; never clear beyond the two payload words. */
    memset(&p->as,0,16); p->tag=INDIRECT; p->as.indirect=v;
}
MlfNg0Value *mlf_ng0_force(MlfNg0Value *p) {
    mlf_ng0_depth_enter();
    MlfNg0Value *first=NULL, **updates=NULL; size_t count=0,capacity=0;
    for (;;) {
        if (!p) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
        if (whnf(p)) break;
        if (immediate(p)) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
        Tag t=p->tag;
        if (t==HOLE || t==BUSY) mlf_ng0_fault(MLF_NG0_BLACKHOLE);
        if (t!=INDIRECT && t!=THUNK && t!=APPLICATION) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
        MlfNg0Value *ready=mlf_ng0_peek(p); if (ready) { p=ready; break; }
        MlfNg0Value *old=p;
        if (!first) first=old;
        else {
            if (count==capacity) {
                if (capacity>SIZE_MAX/2/sizeof(*updates)) mlf_ng0_fault(MLF_NG0_ARENA_LIMIT);
                size_t next=capacity ? capacity*2 : 4;
                MlfNg0Value **q=allocate(next*sizeof(*q));
                if (count) memcpy(q,updates,count*sizeof(*q));
                updates=q; capacity=next;
            }
            updates[count++]=old;
        }
        old->tag=BUSY;
        if (t==THUNK) { MlfNg0Code c=old->as.closure.code; MlfNg0Env *e=old->as.closure.env;
            memset(&old->as,0,16); p=invoke(c,e,NULL); }
        else if (t==APPLICATION) { MlfNg0Value *f=old->as.application.function,*a=old->as.application.argument;
            memset(&old->as,0,16); p=apply(f,a); }
        else { p=old->as.indirect; memset(&old->as,0,16); }
    }
    if (first) memo(first,p);
    for (size_t i=0;i<count;++i) memo(updates[i],p);
    mlf_ng0_depth_leave(); return p;
}
int64_t mlf_ng0_tag(MlfNg0Value *p) {
    p=mlf_ng0_force(p);
    if (nullary(p)) return (int64_t)((uintptr_t)p>>3);
    if (immediate(p)) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    if (p->tag==CONSTRUCTOR_1 || p->tag==CONSTRUCTOR_2) return p->as.packed.identity;
    if (p->tag!=CONSTRUCTOR || !p->as.constructor.fields || p->as.constructor.arity!=(int64_t)p->as.constructor.fields->count)
        mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    return p->as.constructor.identity;
}
MlfNg0Value *mlf_ng0_field(MlfNg0Value *p,uint64_t i) {
    p=mlf_ng0_force(p);
    if (immediate(p)) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
    if (p->tag==CONSTRUCTOR_1 || p->tag==CONSTRUCTOR_2) {
        if (i>=(uint64_t)(p->tag==CONSTRUCTOR_1 ? 1 : 2) || !p->as.packed.fields[i]) mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
        return p->as.packed.fields[i];
    }
    mlf_ng0_fault(MLF_NG0_INVALID_VALUE);
}
_Noreturn void mlf_ng0_match_failure(void) { mlf_ng0_fault(MLF_NG0_MATCH_FAILURE); }
MlfNg0Status mlf_ng0_eval(const MlfNg0Limits *limits,MlfNg0Result *out) {
    if (!out) return MLF_NG0_INVALID_CONFIG;
    /* Copy before publishing output, including callers with overlapping storage. */
    MlfNg0Limits requested={0,0,0}; if (limits) requested=*limits;
    MlfNg0Result report={0}; report.abi=MLF_NG0_ABI;
    report.status=MLF_NG0_INVALID_CONFIG; report.requested_capacity=requested.capacity;
    if (atomic_flag_test_and_set_explicit(&gate,memory_order_acquire)) {
        report.status=MLF_NG0_BUSY; *out=report; return report.status;
    }
    if (MLF_NG0_PROFILE_QUALIFIED!=1 || MLF_NG0_CAPACITY_CEILING<=0 || MLF_NG0_DEPTH_CEILING<=0 ||
        requested.abi!=MLF_NG0_ABI || !requested.capacity || !requested.depth_limit ||
        requested.capacity>(uint64_t)MLF_NG0_CAPACITY_CEILING || requested.depth_limit>(uint64_t)MLF_NG0_DEPTH_CEILING ||
        requested.capacity>SIZE_MAX-sizeof(Context)) goto finish;
    report.context_bytes=sizeof(Context); report.host_allocation_calls=1;
    report.host_requested_bytes=sizeof(Context);
    Context *const ctx=malloc(sizeof(Context));
    if (!ctx) { report.status=MLF_NG0_HOST_ALLOCATION; goto finish; }
    memset(ctx,0,sizeof(*ctx)); ctx->result=report;
    ctx->capacity=(size_t)requested.capacity; ctx->limit=requested.depth_limit;
    ctx->result.host_allocation_calls=2; ctx->result.host_requested_bytes+=requested.capacity;
    ctx->slab=malloc(ctx->capacity);
    if (!ctx->slab) { report=ctx->result; report.status=MLF_NG0_HOST_ALLOCATION; free(ctx); goto finish; }
    active=ctx;
    if (setjmp(ctx->escape)==0) {
        mlf_ng0_depth_enter();
        MlfNg0Value *root=mlf_ng0_guest_entry();
        ctx->result.value=integer(root);
        mlf_ng0_depth_leave();
        if (ctx->depth) mlf_ng0_fault(MLF_NG0_INTERNAL_CONTRACT);
        ctx->result.status=MLF_NG0_OK;
    }
    /* ctx is never modified across setjmp; mutable recovery state is heap-owned.
     * No cleanup follows stack records or calls guest code. Publish after frees. */
    report=ctx->result; if (report.status!=MLF_NG0_OK) report.value=0;
    active=NULL; free(ctx->slab); free(ctx);
finish:
    atomic_flag_clear_explicit(&gate,memory_order_release);
    *out=report; return report.status;
}
