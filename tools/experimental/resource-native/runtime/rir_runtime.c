#include "rir_runtime.h"
#include <inttypes.h>
#include <limits.h>
#include <setjmp.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(size_t)<=sizeof(uint64_t), "terminal receipt requires size_t no wider than uint64_t");

/* All language/runtime dynamic storage passes through mem_alloc/mem_free.
 * Ordinary reclamation uses ownership. The opt-in terminal-domain operation
 * retires every registered raw block after exclusive surrender, never reachability. */
enum { MC_CONTEXT, MC_GROUP, MC_NODE, MC_SLOTS, MC_HANDLE, MC_CAPTURES, MC_PENDING };
enum { RC_OWNER, RC_BUILDER, RC_PIN, RC_KEY, RC_SLOT };
typedef enum { NS_READY, NS_HOLE, NS_INDIRECT, NS_THUNK, NS_CLOSURE, NS_APPLICATION, NS_BUSY, NS_MEMO } State;
typedef struct RtGroup Group;
typedef struct RtNode Node;
typedef struct { const char *name; Node *target; } Slot;
typedef union MemHeader MemHeader;
union MemHeader {
    max_align_t alignment;
    struct { MemHeader *previous, *next; size_t requested; unsigned category; } info;
};
struct RtGroup { uint64_t id, count, members; Node *first, *last; Group *queue_next; };
struct RtNode {
    uint64_t id;
    Group *group;
    const RtShape *shape;
    const RtCode *code;
    State state;
    size_t used, capacity;
    Slot *slots;
    Node *next;
};
typedef struct { Node base; int64_t value; } ScalarNode;
typedef struct { Node base; const RtVariant *variant; } SumNode;
typedef struct Frame { uint64_t id; struct Frame *parent; RtHandle *home; int returned; } Frame;
typedef struct Pending { Node *node; RtHandle *pin; struct Pending *next; } Pending;
struct RtContext {
    const RtProgram *program;
    RtOptions options;
    RtReport report;
    FILE *output;
    jmp_buf failure;
    MemHeader *ledger;
    RtHandle *handles;
    Group *close_first, *close_last;
    int closing, finished;
    unsigned api_active; /* independent of possibly abandoned C frame pointers */
    uint64_t next_group, next_node, next_handle, next_frame;
    uint64_t live_groups, live_nodes, live_owners, force_depth, activation_depth;
    uint64_t rc_inc_total, rc_dec_total;
    uint64_t fuel_remaining;
    Frame *frame;
};
static const char *const states[] = {"READY","HOLE","INDIRECT","THUNK","CLOSURE","APPLICATION","BUSY","MEMO"};
static const char *const memory_names[] = {"context","groups","nodes","slots","handles","captures","pending"};
static const char *const rc_names[] = {"owner","builder","pin","key","slot"};
static _Noreturn void fault(RtContext *c, const char *code) { c->report.status="fault"; c->report.fault=code; longjmp(c->failure,1); }
static void add(RtContext *c, uint64_t *x, uint64_t n) { if (UINT64_MAX-*x<n) fault(c,"OVERFLOW"); *x+=n; }
static void bump(RtContext *c, uint64_t *x) { add(c,x,1); }
static uint64_t identity(RtContext *c,uint64_t *x) { bump(c,x); return *x; }
static void tick(RtContext *c) {
    if(c->frame && c->frame->returned)fault(c,"INVARIANT");
    bump(c,&c->report.steps);
    if(!c->fuel_remaining)fault(c,"FUEL");
    --c->fuel_remaining;
}
static void peak(uint64_t *p,uint64_t n) { if(n>*p)*p=n; }
static void account_alloc(RtContext *c,RtMemory *m,size_t n) {
    add(c,&m->allocated_bytes,(uint64_t)n); add(c,&m->live_bytes,(uint64_t)n);
    bump(c,&m->allocations); bump(c,&m->live_blocks); peak(&m->peak_bytes,m->live_bytes); peak(&m->peak_blocks,m->live_blocks);
}
/* Both aggregate/category copies are prepared while the raw block stays linked.
 * No context metric mutates before every free-side guard has passed. */
static RtMemory account_free_preflight(RtContext *c,const RtMemory *m,size_t n) {
    if(m->live_bytes<n||!m->live_blocks)fault(c,"INVARIANT");
    if(UINT64_MAX-m->freed_bytes<n||m->frees==UINT64_MAX)fault(c,"OVERFLOW");
    RtMemory result=*m;
    result.freed_bytes+=(uint64_t)n;result.live_bytes-=(uint64_t)n;
    ++result.frees;--result.live_blocks;
    return result;
}
static void *mem_alloc(RtContext *c,size_t size,unsigned category) {
    if(size>SIZE_MAX-sizeof(MemHeader)||category>=RT_MEMORY_CATEGORIES)fault(c,"OVERFLOW");
    size_t requested=sizeof(MemHeader)+size;
    MemHeader *h=malloc(requested); if(!h)fault(c,"OOM");
    h->info.previous=NULL; h->info.next=c->ledger; h->info.requested=requested; h->info.category=category;
    if(c->ledger)c->ledger->info.previous=h;
    c->ledger=h;
    account_alloc(c,&c->report.memory,requested); account_alloc(c,&c->report.categories[category],requested);
    void *result=h+1; memset(result,0,size); return result;
}
static void mem_free(RtContext *c,void *p) {
    if(!p)return;
    MemHeader *h=(MemHeader *)p-1;
    if(h->info.category>=RT_MEMORY_CATEGORIES)fault(c,"INVARIANT");
    RtMemory total=account_free_preflight(c,&c->report.memory,h->info.requested);
    RtMemory category=account_free_preflight(c,&c->report.categories[h->info.category],h->info.requested);
    /* Transaction commit/unlink/free suffix: no callback, event, allocation or fault. */
    c->report.memory=total;c->report.categories[h->info.category]=category;
    if(h->info.previous)h->info.previous->info.next=h->info.next;else c->ledger=h->info.next;
    if(h->info.next)h->info.next->info.previous=h->info.previous;
    free(h);
}
static void *array(RtContext *c,size_t n,size_t size,unsigned category) {
    if(!n)return NULL;
    if(n>SIZE_MAX/size)fault(c,"OVERFLOW");
    return mem_alloc(c,n*size,category);
}
static void quoted(FILE *f,const char *s) {
    if(!s){ fputs("null",f); return; } fputc('"',f);
    for(const unsigned char *p=(const unsigned char *)s;*p;++p) {
        if(*p=='"'||*p=='\\'){fputc('\\',f);fputc(*p,f);}
        else if(*p<32)fprintf(f,"\\u%04x",(unsigned)*p); else fputc(*p,f);
    } fputc('"',f);
}
static int event(RtContext *c,const char *kind) {
    if(!c->options.event_limit)return 0;
    if(c->report.events_emitted>=c->options.event_limit){bump(c,&c->report.events_omitted);return 0;}
    if(c->output){if(c->report.events_emitted)fputc(',',c->output);fputs("{\"event\":",c->output);quoted(c->output,kind);}
    bump(c,&c->report.events_emitted); return c->output!=NULL;
}
static void num(RtContext *c,const char *key,uint64_t n){fputc(',',c->output);quoted(c->output,key);fprintf(c->output,":%"PRIu64,n);}
static void str(RtContext *c,const char *key,const char *s){fputc(',',c->output);quoted(c->output,key);fputc(':',c->output);quoted(c->output,s);}
static void boolean(RtContext *c,const char *key,int value){fputc(',',c->output);quoted(c->output,key);fputs(value?":true":":false",c->output);}
static void end_event(RtContext *c){fputc('}',c->output);}
static uint64_t frame_id(RtContext *c){return c->frame?c->frame->id:0;}
static void slot_event(RtContext *c,const char *kind,Node *host,const char *name,Node *target,const char *reason) {
    if(event(c,kind)){num(c,"host",host->id);num(c,"host_group",host->group->id);str(c,"host_layout",host->shape->name);str(c,"field",name);num(c,"target",target->id);num(c,"target_group",target->group->id);str(c,"target_layout",target->shape->name);str(c,"target_state",states[target->state]);boolean(c,"internal",host->group==target->group);str(c,"reason",reason);end_event(c);}
}
static RtHandle *live(RtContext *c,RtHandle *h) {
    /* Exact-address live registry, not heap reachability or a collector. */
    for(RtHandle *p=c->handles;p;p=p->next)if(p==h)return p;
    fault(c,"INVARIANT");
}
static Node *node(RtContext *c,RtHandle *h){live(c,h);if(!h->node)fault(c,"INVARIANT");return h->node;}
static void owned(RtContext *c,RtHandle *h){live(c,h);if(h->anchor)fault(c,"INVARIANT");}
static void authority(RtContext *c,RtHandle *h){live(c,h);if(h->anchor&&!h->home)fault(c,"INVARIANT");}
static void inc(RtContext *c,Group *g,unsigned role){bump(c,&c->rc_inc_total);bump(c,&g->count);bump(c,&c->report.rc_inc[role]);}
static void dec(RtContext *,Group *,unsigned);
static void dead_storage(RtContext *c,RtHandle *out) {
    if(!out)fault(c,"INVARIANT");
    /* Compare addresses only: never inspect potentially uninitialized bytes. */
    for(RtHandle *p=c->handles;p;p=p->next)if(p==out)fault(c,"INVARIANT");
}
static RtHandle *handle_at(RtContext *c,Group *g,Node *n,RtHandle *anchor,
                           unsigned role,RtHandle *storage) {
    if(storage)dead_storage(c,storage);
    if(anchor){owned(c,anchor);bump(c,&anchor->loans);}
    RtHandle *h=storage?storage:mem_alloc(c,sizeof(*h),MC_HANDLE);
    if(storage)memset(h,0,sizeof(*h));
    h->storage_kind=storage?RT_STORAGE_LOCAL:RT_STORAGE_HEAP;
    h->id=identity(c,&c->next_handle);h->group=g;h->node=n;h->anchor=anchor;h->role=role;
    h->next=c->handles;if(c->handles)c->handles->previous=h;c->handles=h;
    if(anchor)bump(c,&c->report.loan_handle_acquisitions);
    else {inc(c,g,role);bump(c,&c->live_owners);bump(c,&c->report.owner_handle_acquisitions);peak(&c->report.peak_owner_handles,c->live_owners);}
    return h;
}
static RtHandle *handle(RtContext *c,Group *g,Node *n,RtHandle *anchor,unsigned role) {
    return handle_at(c,g,n,anchor,role,NULL);
}
static RtHandle *acquire_at(RtContext *c,Node *n,RtHandle *storage) {
    return handle_at(c,n->group,n,NULL,RC_OWNER,storage);
}
static RtHandle *acquire(RtContext *c,Node *n){return acquire_at(c,n,NULL);}
/* Physical storage retirement is NOT a logical owner release. */
static void retire_storage(RtContext *c,RtHandle *h,RtStorageKind kind) {
    if(kind==RT_STORAGE_HEAP)mem_free(c,h);
    else if(kind==RT_STORAGE_LOCAL)memset(h,0,sizeof(*h));
    else fault(c,"INVARIANT");
}
static RtHandle *move_owner(RtContext *c,RtHandle *source,RtHandle *destination,
                            RtStorageKind destination_kind) {
    owned(c,source);
    if(source->loans || source==destination)fault(c,"INVARIANT");
    dead_storage(c,destination);
    RtStorageKind original_kind=source->storage_kind;
    if(original_kind!=RT_STORAGE_HEAP && original_kind!=RT_STORAGE_LOCAL)fault(c,"INVARIANT");
    /* Same logical id/scope/role/home/count, new address. No acquisition/drop. */
    *destination=*source;destination->storage_kind=destination_kind;
    if(destination->previous)destination->previous->next=destination;
    else c->handles=destination;
    if(destination->next)destination->next->previous=destination;
    retire_storage(c,source,original_kind);
    return destination;
}
static RtHandle *escaping_owner(RtContext *c,RtHandle *source) {
    owned(c,source);
    if(source->loans)fault(c,"INVARIANT");
    if(source->storage_kind==RT_STORAGE_HEAP)return source;
    if(source->storage_kind!=RT_STORAGE_LOCAL)fault(c,"INVARIANT");
    /* Allocate BEFORE unregistering the local owner. OOM never drops its root. */
    RtHandle *destination=mem_alloc(c,sizeof(*destination),MC_HANDLE);
    return move_owner(c,source,destination,RT_STORAGE_HEAP);
}
static RtHandle *local(RtContext *c,RtHandle *h){h->scope=frame_id(c);return h;}
static void drop(RtContext *c,RtHandle *h) {
    live(c,h);if(h->loans)fault(c,"INVARIANT");
    RtStorageKind kind=h->storage_kind;
    if(kind!=RT_STORAGE_HEAP && kind!=RT_STORAGE_LOCAL)fault(c,"INVARIANT");
    Group *g=h->group; unsigned role=h->role; int own=h->anchor==NULL;
    if(h->anchor){live(c,h->anchor);if(!h->anchor->loans)fault(c,"INVARIANT");--h->anchor->loans;bump(c,&c->report.loan_handle_releases);}
    else {--c->live_owners;bump(c,&c->report.owner_handle_releases);}
    if(h->previous)h->previous->next=h->next;else c->handles=h->next;
    if(h->next)h->next->previous=h->previous;
    retire_storage(c,h,kind); /* cached group/role; final decrement can free nodes */
    if(own)dec(c,g,role);
}
static void dec(RtContext *c,Group *g,unsigned role) {
    if(!g->count)fault(c,"INVARIANT");
    --g->count;bump(c,&c->rc_dec_total);bump(c,&c->report.rc_dec[role]);
    if(!g->count){if(c->close_last)c->close_last->queue_next=g;else c->close_first=g;c->close_last=g;}
    if(c->closing)return;
    c->closing=1;
    while(c->close_first){
        Group *dead=c->close_first;c->close_first=dead->queue_next;if(!c->close_first)c->close_last=NULL;
        if(dead->count)fault(c,"INVARIANT");
        if(event(c,"close_group")){
            uint64_t internal=0,cross=0;
            for(Node *n=dead->first;n;n=n->next)for(size_t i=0;i<n->used;++i){if(n->slots[i].target->group==dead)++internal;else ++cross;}
            num(c,"group",dead->id);num(c,"members",dead->members);num(c,"force_depth",c->force_depth);num(c,"live_groups_before",c->live_groups);num(c,"internal_slots",internal);num(c,"cross_slots",cross);end_event(c);
        }
        if(c->force_depth)bump(c,&c->report.groups_closed_during_force);
        /* Pass 1: ALL member nodes and queued target groups remain live. */
        for(Node *n=dead->first;n;n=n->next){for(size_t i=0;i<n->used;++i){Node *t=n->slots[i].target;slot_event(c,"slot_remove",n,n->slots[i].name,t,"group_close");if(t->group!=dead)dec(c,t->group,RC_SLOT);}n->used=0;}
        /* Pass 2: only after no later internal slot can dereference a member. */
        for(Node *n=dead->first;n;){Node *next=n->next;mem_free(c,n->slots);mem_free(c,n);bump(c,&c->report.nodes_freed);--c->live_nodes;n=next;}
        mem_free(c,dead);bump(c,&c->report.groups_closed);--c->live_groups;
    } c->closing=0;
}
static void slot(RtContext *c,Node *host,const char *name,Node *target) {
    if(host->used>=host->capacity)fault(c,"INVARIANT");
    for(size_t i=0;i<host->used;++i)if(strcmp(host->slots[i].name,name)==0)fault(c,"INVARIANT");
    if(host->group!=target->group)inc(c,target->group,RC_SLOT);
    host->slots[host->used++]=(Slot){name,target};slot_event(c,"slot_install",host,name,target,"publication");
}
static void clear_slots(RtContext *c,Node *n){
    /* Acquired operands or still-live host support keep later targets live. */
    size_t count=n->used;n->used=0;
    for(size_t i=0;i<count;++i){Node *t=n->slots[i].target;slot_event(c,"slot_remove",n,n->slots[i].name,t,"payload_clear");if(t->group!=n->group)dec(c,t->group,RC_SLOT);}
}
static int registered_shape(RtContext *c,const RtShape *s){for(size_t i=0;i<c->program->shape_count;++i)if(c->program->shapes[i]==s)return 1;return 0;}
static void shape(RtContext *c,const RtShape *s){if(!registered_shape(c,s)||s->kind==RT_ONCE_UNSUPPORTED)fault(c,"UNSUPPORTED");}
static const RtFamily *sum_family(RtContext *c,const RtFamily *family) {
    for(size_t i=0;i<c->program->family_count;++i)if(c->program->families[i]==family)return family;
    fault(c,"UNSUPPORTED");
}
static const RtFamily *sum_family_for_shape(RtContext *c,const RtShape *s) {
    for(size_t i=0;i<c->program->family_count;++i)if(c->program->families[i]->shape==s)return c->program->families[i];
    fault(c,"UNSUPPORTED");
}
static const RtVariant *sum_variant(RtContext *c,const RtFamily *family,const RtVariant *variant) {
    sum_family(c,family);
    for(size_t i=0;i<family->variant_count;++i)if(family->variants[i]==variant)return variant;
    fault(c,"INVARIANT");
}
static void code(RtContext *c,const RtCode *v,RtCodeKind kind){
    int found=0;for(size_t i=0;i<c->program->code_count;++i)if(c->program->codes[i]==v)found=1;
    if(!found||v->kind!=kind||!v->body)fault(c,"UNSUPPORTED");
    shape(c,v->shape);
}
static RtHandle *allocate(RtContext *c,RtHandle *a,const RtShape *s,State state,const RtCode *v,size_t count,const RtField *fields,RtHandle *const *values,const char *out,const char *opcode,int loans,RtHandle *storage) {
    authority(c,a);shape(c,s);if(count&&!values)fault(c,"INVARIANT");
    for(size_t i=0;i<count;++i){Node *t=node(c,values[i]);if(!loans)owned(c,values[i]);if(fields&&t->shape!=fields[i].shape)fault(c,"INVARIANT");}
    if(s->kind==RT_SUM)(void)sum_family_for_shape(c,s);
    size_t bytes=(s->kind==RT_I64||s->kind==RT_BOOL)?sizeof(ScalarNode):s->kind==RT_SUM?sizeof(SumNode):sizeof(Node);
    Node *n=mem_alloc(c,bytes,MC_NODE);n->id=identity(c,&c->next_node);n->group=a->group;n->shape=s;n->state=state;n->code=v;
    n->capacity=count;if(state==NS_HOLE||state==NS_THUNK){if(n->capacity<1)n->capacity=1;}
    n->slots=array(c,n->capacity,sizeof(Slot),MC_SLOTS);
    if(n->group->last)n->group->last->next=n;else n->group->first=n;n->group->last=n;bump(c,&n->group->members);
    for(size_t i=0;i<count;++i)slot(c,n,fields[i].name,node(c,values[i]));
    bump(c,&c->report.nodes_allocated);bump(c,&c->live_nodes);peak(&c->report.peak_nodes,c->live_nodes);
    RtHandle *result=acquire_at(c,n,storage);
    if(event(c,"allocate")){num(c,"node",n->id);num(c,"group",n->group->id);str(c,"state",states[state]);str(c,"code",v?v->name:NULL);str(c,"layout",s->name);str(c,"out",out);num(c,"frame",frame_id(c));str(c,"opcode",opcode);fputs(",\"slots\":{",c->output);for(size_t i=0;i<n->used;++i){if(i)fputc(',',c->output);quoted(c->output,n->slots[i].name);fprintf(c->output,":%"PRIu64,n->slots[i].target->id);}fputc('}',c->output);end_event(c);}
    return result;
}
static RtHandle *new_group(RtContext *c,size_t count,RtHandle *const *imports,RtHandle *storage){
    if(count&&!imports)fault(c,"INVARIANT");
    for(size_t i=0;i<count;++i)authority(c,imports[i]);
    Group *g=mem_alloc(c,sizeof(*g),MC_GROUP);g->id=identity(c,&c->next_group);bump(c,&c->live_groups);bump(c,&c->report.groups_allocated);peak(&c->report.peak_groups,c->live_groups);
    RtHandle *h=handle_at(c,g,NULL,NULL,RC_BUILDER,storage);if(event(c,"new_group")){num(c,"group",g->id);end_event(c);}return local(c,h);
}
RtHandle *rt_new_root(RtContext *c,size_t n,RtHandle *const *imports){tick(c);return new_group(c,n,imports,NULL);}
RtHandle *rt_new_below(RtContext *c,RtHandle *ceiling,size_t n,RtHandle *const *imports){tick(c);authority(c,ceiling);return new_group(c,n,imports,NULL);}
RtHandle *rt_alloc(RtContext *c,RtHandle *a,const RtShape *s,RtHandle *const *fields,const char *out){tick(c);shape(c,s);if(s->kind!=RT_DATA)fault(c,"INVARIANT");return local(c,allocate(c,a,s,NS_READY,NULL,s->field_count,s->fields,fields,out,"alloc",0,NULL));}
static int64_t integer_bits(uint64_t bits) {
    return bits<=INT64_MAX?(int64_t)bits:-1-(int64_t)(UINT64_MAX-bits);
}
static ScalarNode *ready_scalar(RtContext *c,RtHandle *h,RtShapeKind expected) {
    owned(c,h);Node *n=node(c,h);shape(c,n->shape);
    if(n->state!=NS_READY||n->shape->kind!=expected||n->code||n->used||n->capacity||n->slots)
        fault(c,"INVARIANT");
    ScalarNode *s=(ScalarNode *)n;
    if(expected==RT_BOOL&&s->value!=0&&s->value!=1)fault(c,"INVARIANT");
    return s;
}
/* Tag/arity only: factory must validate the entire arm table before reading
 * any selected payload cursor. Force/return do not impose the factory HOLE bar. */
static const RtVariant *ready_sum(RtContext *c,RtHandle *h,const RtFamily *family) {
    sum_family(c,family);owned(c,h);Node *n=node(c,h);shape(c,n->shape);
    if(n->state!=NS_READY||n->shape!=family->shape||n->shape->kind!=RT_SUM||n->code)
        fault(c,"INVARIANT");
    const RtVariant *v=sum_variant(c,family,((SumNode *)n)->variant);
    if(n->used!=v->field_count||n->capacity!=v->field_count||
       (v->field_count?!n->slots:n->slots!=NULL))fault(c,"INVARIANT");
    return v;
}
static void sum_payload(RtContext *c,Node *n,const RtVariant *v) {
    for(size_t i=0;i<v->field_count;++i){
        Slot *s=&n->slots[i];
        if(!s->name||strcmp(s->name,v->fields[i].name)||!s->target||
           s->target->shape!=v->fields[i].shape||s->target->state==NS_HOLE)
            fault(c,"INVARIANT");
    }
}
static void validate_sum_cursor(RtContext *c,RtHandle *h) {
    Node *n=node(c,h);shape(c,n->shape);
    if(n->shape->kind==RT_SUM){
        const RtFamily *family=sum_family_for_shape(c,n->shape);
        if(n->state==NS_READY)(void)ready_sum(c,h,family);
        else if(n->state==NS_CLOSURE)fault(c,"INVARIANT");
    }
}
static RtHandle *scalar_value(RtContext *c,RtHandle *a,const RtShape *s,int64_t value,
                              const char *out,const char *opcode,const char *primitive) {
    RtHandle *h=local(c,allocate(c,a,s,NS_READY,NULL,0,NULL,NULL,out,opcode,0,NULL));
    ((ScalarNode *)h->node)->value=value;
    if(event(c,"scalar_value")){
        num(c,"node",h->node->id);str(c,"kind",s->kind==RT_I64?"i64":"bool");
        if(s->kind==RT_I64)fprintf(c->output,",\"value\":%"PRId64,value);
        else boolean(c,"value",value!=0);
        str(c,"opcode",opcode);str(c,"primitive",primitive);end_event(c);
    }
    return h;
}
RtHandle *rt_scalar_i64(RtContext *c,RtHandle *a,const RtShape *s,int64_t value,const char *out) {
    tick(c);shape(c,s);if(s->kind!=RT_I64)fault(c,"INVARIANT");
    return scalar_value(c,a,s,value,out,"scalar",NULL);
}
RtHandle *rt_scalar_bool(RtContext *c,RtHandle *a,const RtShape *s,int value,const char *out) {
    tick(c);shape(c,s);if(s->kind!=RT_BOOL||(value!=0&&value!=1))fault(c,"INVARIANT");
    return scalar_value(c,a,s,value,out,"scalar",NULL);
}
RtHandle *rt_prim2(RtContext *c,RtHandle *a,RtScalarPrimitive primitive,const RtShape *result,
                   RtHandle *left,RtHandle *right,const char *out) {
    tick(c);const char *name=NULL;RtShapeKind kind=RT_I64;
    switch(primitive){
        case RT_PRIM_ADD_INT:name="addInt";break;case RT_PRIM_SUB_INT:name="subInt";break;
        case RT_PRIM_MUL_INT:name="mulInt";break;
        case RT_PRIM_EQ_INT:name="eqInt";kind=RT_BOOL;break;
        case RT_PRIM_LT_INT:name="ltInt";kind=RT_BOOL;break;
        default:fault(c,"UNSUPPORTED");
    }
    authority(c,a);shape(c,result);if(result->kind!=kind)fault(c,"INVARIANT");
    int64_t x=ready_scalar(c,left,RT_I64)->value;
    int64_t y=ready_scalar(c,right,RT_I64)->value;
    uint64_t u=(uint64_t)x,v=(uint64_t)y;int64_t value;
    switch(primitive){
        case RT_PRIM_ADD_INT:value=integer_bits(u+v);break;
        case RT_PRIM_SUB_INT:value=integer_bits(u-v);break;
        case RT_PRIM_MUL_INT:value=integer_bits(u*v);break;
        case RT_PRIM_EQ_INT:value=x==y;break;case RT_PRIM_LT_INT:value=x<y;break;
        default:fault(c,"UNSUPPORTED");
    }
    return scalar_value(c,a,result,value,out,"prim2",name);
}
RtHandle *rt_select_i64(RtContext *c,RtHandle *a,RtHandle *condition,
                        RtHandle *left,RtHandle *right,const char *out) {
    tick(c);authority(c,a);
    int decision=ready_scalar(c,condition,RT_BOOL)->value!=0;
    if(left==right||a==left||a==right)fault(c,"INVARIANT");
    owned(c,left);owned(c,right);
    Node *l=node(c,left),*r=node(c,right);shape(c,l->shape);shape(c,r->shape);
    if(left->loans||right->loans||l->shape->kind!=RT_I64||r->shape->kind!=RT_I64||
       l->state==NS_HOLE||r->state==NS_HOLE)fault(c,"INVARIANT");
    RtHandle *selected=decision?left:right,*unselected=decision?right:left;
    Node *n=node(c,selected);
    if(event(c,"select_i64")){
        num(c,"condition_node",condition->node->id);boolean(c,"condition_value",decision);
        num(c,"then_node",l->id);num(c,"else_node",r->id);num(c,"result",n->id);
        num(c,"owner",selected->id);num(c,"group",n->group->id);str(c,"layout",n->shape->name);
        num(c,"frame",frame_id(c));str(c,"out",out);end_event(c);
    }
    /* Independent selected owner remains registered across unselected release,
     * even when both own the same node or closing drops its supporting slots. */
    drop(c,unselected);
    return selected;
}
RtHandle *rt_construct_nullary(RtContext *c,RtHandle *a,const RtFamily *family,
                               const RtVariant *variant,const char *out) {
    tick(c);sum_family(c,family);sum_variant(c,family,variant);
    if(variant->field_count)fault(c,"INVARIANT");
    RtHandle *h=local(c,allocate(c,a,family->shape,NS_READY,NULL,0,NULL,NULL,out,"construct_nullary",0,NULL));
    ((SumNode *)h->node)->variant=variant;
    if(event(c,"sum_value")){num(c,"node",h->node->id);str(c,"family",family->shape->name);
        str(c,"variant",variant->name);num(c,"variant_index",variant->index);end_event(c);}
    return h;
}
RtHandle *rt_construct_sum(RtContext *c,RtHandle *a,const RtFamily *family,
                           const RtVariant *variant,size_t count,
                           RtHandle *const *fields,const char *out) {
    tick(c);sum_family(c,family);sum_variant(c,family,variant);
    if(count!=variant->field_count||(count&&!fields)||(!count&&fields))fault(c,"INVARIANT");
    RtHandle *h=local(c,allocate(c,a,family->shape,NS_READY,NULL,count,variant->fields,fields,out,"construct_sum",0,NULL));
    ((SumNode *)h->node)->variant=variant;
    if(event(c,"sum_value")){num(c,"node",h->node->id);str(c,"family",family->shape->name);
        str(c,"variant",variant->name);num(c,"variant_index",variant->index);end_event(c);}
    return h;
}
RtHandle *rt_case_fields_i64(RtContext *c,RtHandle *a,const RtFamily *family,
                            RtHandle *scrutinee,size_t count,
                            const RtFactoryArm *arms,const char *out) {
    tick(c);authority(c,a);sum_family(c,family);
    const RtVariant *v=ready_sum(c,scrutinee,family);
    if(count!=family->variant_count||!arms)fault(c,"INVARIANT");
    /* Every arm, including unselected callbacks/external owners, is authenticated
     * before selected payload access, temporary allocation or acquisition. */
    for(size_t i=0;i<count;++i){
        const RtFactoryArm *arm=&arms[i];
        if(arm->variant!=family->variants[i])fault(c,"INVARIANT");
        code(c,arm->code,RT_THUNK);
        if(arm->code->shape->kind!=RT_I64||arm->capture_count>RT_MAX_FACTORY_CAPTURES||
           arm->capture_count!=arm->code->capture_count||
           (arm->capture_count?!arm->captures:arm->captures!=NULL))fault(c,"INVARIANT");
        size_t field_count=0,external_count=0;
        for(size_t j=0;j<arm->capture_count;++j){
            const RtFactoryCapture *binding=&arm->captures[j];
            const RtField *expected=&arm->code->captures[j];
            if(!binding->name||strcmp(binding->name,expected->name))fault(c,"INVARIANT");
            if(binding->kind==RT_FACTORY_FIELD){
                if(++field_count>RT_MAX_FACTORY_FIELD_CAPTURES||binding->external||
                   binding->field_index>=arm->variant->field_count||
                   arm->variant->fields[binding->field_index].shape!=expected->shape)
                    fault(c,"INVARIANT");
            }else if(binding->kind==RT_FACTORY_EXTERNAL){
                if(++external_count>RT_MAX_FACTORY_EXTERNAL_CAPTURES||binding->field_index)
                    fault(c,"INVARIANT");
                owned(c,binding->external);
                if(node(c,binding->external)->shape!=expected->shape)fault(c,"INVARIANT");
            }else fault(c,"INVARIANT");
        }
    }
    Node *parent=node(c,scrutinee);sum_payload(c,parent,v);
    const RtFactoryArm *chosen=&arms[v->index];
    RtHandle **values=array(c,chosen->capture_count,sizeof(*values),MC_CAPTURES);
    uint32_t field_mask=0;
    for(size_t j=0;j<chosen->capture_count;++j){
        const RtFactoryCapture *binding=&chosen->captures[j];
        if(binding->kind==RT_FACTORY_FIELD){
            Node *child=parent->slots[binding->field_index].target;
            values[j]=acquire(c,child);field_mask|=UINT32_C(1)<<binding->field_index;
            if(event(c,"sum_field_capture")){
                num(c,"scrutinee",parent->id);str(c,"family",family->shape->name);
                str(c,"variant",v->name);num(c,"variant_index",v->index);
                str(c,"capture",binding->name);num(c,"field_index",binding->field_index);
                num(c,"node",child->id);num(c,"owner",values[j]->id);
                str(c,"layout",child->shape->name);num(c,"frame",frame_id(c));end_event(c);
            }
        }else values[j]=binding->external;
    }
    RtHandle *result=local(c,allocate(c,a,chosen->code->shape,NS_THUNK,chosen->code,
        chosen->capture_count,chosen->code->captures,values,out,"case_fields_i64",0,NULL));
    for(size_t j=0;j<chosen->capture_count;++j)
        if(chosen->captures[j].kind==RT_FACTORY_FIELD)drop(c,values[j]);
    mem_free(c,values);
    Node *n=node(c,result);
    if(event(c,"case_fields_i64")){
        num(c,"scrutinee",parent->id);str(c,"family",family->shape->name);
        str(c,"variant",v->name);num(c,"variant_index",v->index);str(c,"code",chosen->code->name);
        num(c,"result",n->id);num(c,"owner",result->id);num(c,"group",n->group->id);
        str(c,"layout",n->shape->name);num(c,"frame",frame_id(c));str(c,"out",out);
        num(c,"field_mask",field_mask);fputs(",\"captures\":{",c->output);
        for(size_t j=0;j<n->used;++j){if(j)fputc(',',c->output);quoted(c->output,n->slots[j].name);fprintf(c->output,":%"PRIu64,n->slots[j].target->id);}
        fputs("},\"field_indices\":{",c->output);int first=1;
        for(size_t j=0;j<chosen->capture_count;++j)if(chosen->captures[j].kind==RT_FACTORY_FIELD){
            if(!first)fputc(',',c->output);
            first=0;quoted(c->output,chosen->captures[j].name);fprintf(c->output,":%zu",chosen->captures[j].field_index);
        }
        fputc('}',c->output);end_event(c);
    }
    return result;
}
RtHandle *rt_case_i64(RtContext *c,RtHandle *a,const RtFamily *family,RtHandle *scrutinee,
                      size_t count,const RtCaseArm *arms,const char *out) {
    tick(c);authority(c,a);sum_family(c,family);
    for(size_t i=0;i<family->variant_count;++i)if(family->variants[i]->field_count)fault(c,"INVARIANT");
    const RtVariant *selected_variant=ready_sum(c,scrutinee,family);
    if(count!=family->variant_count||!arms)fault(c,"INVARIANT");
    for(size_t i=0;i<count;++i){
        if(arms[i].variant!=family->variants[i]||arms[i].value==a)fault(c,"INVARIANT");
        for(size_t j=0;j<i;++j)if(arms[j].value==arms[i].value)fault(c,"INVARIANT");
        owned(c,arms[i].value);Node *n=node(c,arms[i].value);shape(c,n->shape);
        if(arms[i].value->loans||n->shape->kind!=RT_I64||n->state==NS_HOLE)fault(c,"INVARIANT");
    }
    size_t index=selected_variant->index;RtHandle *selected=arms[index].value;Node *n=node(c,selected);
    if(event(c,"case_i64")){
        num(c,"scrutinee",scrutinee->node->id);str(c,"family",family->shape->name);
        str(c,"variant",selected_variant->name);num(c,"variant_index",index);num(c,"result",n->id);
        num(c,"owner",selected->id);num(c,"group",n->group->id);str(c,"layout",n->shape->name);
        num(c,"frame",frame_id(c));str(c,"out",out);fputs(",\"alternatives\":{",c->output);
        for(size_t i=0;i<count;++i){if(i)fputc(',',c->output);quoted(c->output,arms[i].variant->name);fprintf(c->output,":%"PRIu64,arms[i].value->node->id);}
        fputc('}',c->output);end_event(c);
    }
    for(size_t i=0;i<count;++i)if(i!=index)drop(c,arms[i].value);
    return selected;
}
RtHandle *rt_closure(RtContext *c,RtHandle *a,const RtCode *v,RtHandle *const *captures,const char *out){tick(c);code(c,v,RT_FUNCTION);if(v->shape->kind!=RT_REPEAT)fault(c,"UNSUPPORTED");return local(c,allocate(c,a,v->shape,NS_CLOSURE,v,v->capture_count,v->captures,captures,out,"closure",0,NULL));}
RtHandle *rt_thunk(RtContext *c,RtHandle *a,const RtCode *v,RtHandle *const *captures,const char *out){tick(c);code(c,v,RT_THUNK);return local(c,allocate(c,a,v->shape,NS_THUNK,v,v->capture_count,v->captures,captures,out,"thunk",0,NULL));}
static RtHandle *application(RtContext *c,RtHandle *a,RtHandle *fn,RtHandle *arg,const char *out,int loans,RtHandle *storage){
    Node *f=node(c,fn),*x=node(c,arg);if(f->shape->kind!=RT_REPEAT||f->shape->argument!=x->shape)fault(c,"INVARIANT");
    RtHandle *values[]={fn,arg};RtField fields[]={{"$function",f->shape},{"$argument",x->shape}};
    bump(c,&c->report.applications_allocated);RtHandle *h=allocate(c,a,f->shape->result,NS_APPLICATION,NULL,2,fields,values,out,loans?"application_borrow":"application",loans,storage);
    /* Slot labels must outlive the stack-local descriptor; they are literals. */
    if(loans){for(size_t i=0;i<2;++i)if(values[i]->anchor)bump(c,&c->report.borrowed_slot_publications);
        if(event(c,"borrowed_slots_published")){num(c,"node",h->node->id);fputs(",\"anchors\":{",c->output);int first=1;for(size_t i=0;i<2;++i)if(values[i]->anchor){if(!first)fputc(',',c->output);first=0;quoted(c->output,fields[i].name);fprintf(c->output,":%"PRIu64,values[i]->anchor->id);}fputc('}',c->output);end_event(c);}}
    return local(c,h);
}
RtHandle *rt_application(RtContext *c,RtHandle *a,RtHandle *fn,RtHandle *arg,const char *out){tick(c);return application(c,a,fn,arg,out,0,NULL);}
RtHandle *rt_application_borrow(RtContext *c,RtHandle *a,RtHandle *fn,RtHandle *arg,const char *out){tick(c);bump(c,&c->report.ir_application_borrow_ops);return application(c,a,fn,arg,out,1,NULL);}
RtHandle *rt_hole(RtContext *c,RtHandle *a,const RtShape *s,const char *out){tick(c);return local(c,allocate(c,a,s,NS_HOLE,NULL,0,NULL,NULL,out,"hole",0,NULL));}
void rt_fill(RtContext *c,RtHandle *h,RtHandle *value,const char *hv,const char *vv){tick(c);owned(c,h);owned(c,value);Node *n=node(c,h),*t=node(c,value);if(n->state!=NS_HOLE||n->shape!=t->shape)fault(c,"INVARIANT");slot(c,n,"$target",t);n->state=NS_INDIRECT;if(event(c,"fill")){num(c,"hole",n->id);num(c,"target",t->id);num(c,"frame",frame_id(c));str(c,"hole_variable",hv);str(c,"value_variable",vv);end_event(c);}}
RtHandle *rt_retain(RtContext *c,RtHandle *h){tick(c);bump(c,&c->report.ir_retain_ops);return local(c,acquire(c,node(c,h)));}
void rt_drop(RtContext *c,RtHandle *h){tick(c);bump(c,&c->report.ir_drop_ops);owned(c,h);drop(c,h);}
RtHandle *rt_borrow(RtContext *c,RtHandle *h){tick(c);bump(c,&c->report.ir_borrow_ops);owned(c,h);return local(c,handle(c,h->group,h->node,h,RC_OWNER));}
void rt_end_borrow(RtContext *c,RtHandle *h){tick(c);bump(c,&c->report.ir_end_borrow_ops);live(c,h);if(!h->anchor||h->home)fault(c,"INVARIANT");drop(c,h);}
static RtHandle *field_at(RtContext *c,RtHandle *h,size_t index,const char *out,
                          const char *source,RtHandle *storage) {
    owned(c,h);Node *n=node(c,h);if(n->state!=NS_READY||n->shape->kind!=RT_DATA||index>=n->used)fault(c,"INVARIANT");
    Node *t=n->slots[index].target;
    RtHandle *loan=local(c,handle_at(c,t->group,t,h,RC_OWNER,storage));
    if(event(c,"field_project")){num(c,"host",n->id);num(c,"host_group",n->group->id);str(c,"field",n->slots[index].name);num(c,"target",t->id);num(c,"target_group",t->group->id);str(c,"target_layout",t->shape->name);num(c,"anchor",h->id);num(c,"loan",loan->id);str(c,"out",out);str(c,"source_variable",source);num(c,"frame",frame_id(c));end_event(c);}return loan;
}
RtHandle *rt_field(RtContext *c,RtHandle *h,size_t index,const char *out,const char *source) {
    tick(c);return field_at(c,h,index,out,source,NULL);
}
static void frame_enter(RtContext *c,Frame *f,RtHandle *home,const char *kind,const RtCode *v,Node *n,Group *g){
    if(c->activation_depth>=RT_MAX_ACTIVATION_DEPTH)fault(c,"STACK_LIMIT");
    *f=(Frame){identity(c,&c->next_frame),c->frame,home,0};c->frame=f;
    bump(c,&c->activation_depth);peak(&c->report.max_activation_depth,c->activation_depth);
    if(home){home->home=1;home->scope=f->id;}
    if(event(c,"frame_enter")){num(c,"frame",f->id);if(f->parent)num(c,"parent_frame",f->parent->id);else str(c,"parent_frame",NULL);
        fputs(",\"context\":{\"kind\":",c->output);quoted(c->output,kind);
        if(v){str(c,"name",v->name);num(c,"node",n->id);num(c,"home_group",g->id);}fputc('}',c->output);end_event(c);}
}
static void frame_leave(RtContext *c,Frame *f){if(c->frame!=f)fault(c,"INVARIANT");c->frame=f->parent;--c->activation_depth;}
static RtHandle **capture_owners(RtContext *c,Node *n){
    RtHandle **caps=array(c,n->used,sizeof(*caps),MC_CAPTURES);
    for(size_t i=0;i<n->used;++i)caps[i]=acquire(c,n->slots[i].target);
    return caps;
}
static void handoff_event(RtContext *c,const char *kind,Node *n,RtHandle **caps,int repeat){
    if(event(c,kind)){num(c,"node",n->id);if(repeat)str(c,"protocol","repeat");fputs(",\"owners\":{",c->output);
        for(size_t i=0;i<n->used;++i){if(i)fputc(',',c->output);quoted(c->output,n->slots[i].name);fprintf(c->output,":%"PRIu64,caps[i]->id);}fputc('}',c->output);end_event(c);}
}
static RtHandle *invoke(RtContext *c,RtHandle *callee,RtHandle *arg,RtHandle *ceiling){
    owned(c,callee);owned(c,arg);authority(c,ceiling);Node *n=node(c,callee);
    if(n->state!=NS_CLOSURE||n->shape->kind!=RT_REPEAT||node(c,arg)->shape!=n->shape->argument)fault(c,"INVARIANT");
    const RtCode *v=n->code;const RtShape *result_shape=n->shape->result;uint64_t input=arg->node->id;
    RtHandle *pin=handle(c,ceiling->group,NULL,NULL,RC_PIN),*home=handle(c,ceiling->group,NULL,pin,RC_KEY);
    bump(c,&c->report.ordinary_calls);
    RtHandle **captures=capture_owners(c,n);handoff_event(c,"closure_capture_handoff",n,captures,1);
    if(event(c,"invoke_enter")){num(c,"closure",n->id);num(c,"closure_group",n->group->id);num(c,"home",ceiling->group->id);num(c,"argument",input);str(c,"protocol","repeat");end_event(c);}
    Frame frame;frame_enter(c,&frame,home,"function",v,n,ceiling->group);
    for(size_t i=0;i<v->capture_count;++i)captures[i]->scope=frame.id;
    arg->scope=frame.id;
    RtHandle *result=v->body(c,home,captures,arg);
    if(!frame.returned)fault(c,"INVARIANT");
    owned(c,result);Node *r=node(c,result);
    if(!frame.returned||r->shape!=result_shape||(v->result_identity_argument&&r->id!=input))fault(c,"INVARIANT");
    if(event(c,"invoke_raw_return")){num(c,"closure",n->id);num(c,"argument",input);num(c,"result",r->id);str(c,"token",NULL);num(c,"owner",result->id);num(c,"home",pin->group->id);end_event(c);}
    frame_leave(c,&frame);mem_free(c,captures);drop(c,home);drop(c,callee);drop(c,pin);return result;
}
static RtHandle *callback(RtContext *c,Node *n,RtHandle *pin,RtHandle **captures){
    const RtCode *v=n->code;RtHandle *home=handle(c,n->group,NULL,pin,RC_KEY);
    bump(c,&c->report.callback_calls);if(event(c,"callback_enter")){num(c,"node",n->id);num(c,"pin",pin->id);end_event(c);}
    Frame frame;frame_enter(c,&frame,home,"thunk",v,n,n->group);
    for(size_t i=0;i<v->capture_count;++i)captures[i]->scope=frame.id;
    RtHandle *result=v->body(c,home,captures,NULL);
    if(!frame.returned)fault(c,"INVARIANT");
    owned(c,result);Node *r=node(c,result);
    if(!frame.returned||r->shape!=v->shape)fault(c,"INVARIANT");
    if(event(c,"raw_return")){num(c,"source",n->id);num(c,"result",r->id);str(c,"result_state",states[r->state]);num(c,"owner",result->id);num(c,"home_pin",pin->id);end_event(c);}
    if(r->state!=NS_READY&&r->state!=NS_CLOSURE)bump(c,&c->report.raw_deferred_returns);
    frame_leave(c,&frame);mem_free(c,captures);drop(c,home);return result;
}
static RtHandle *force(RtContext *c,RtHandle *cursor){
    if(c->force_depth>=RT_MAX_FORCE_DEPTH)fault(c,"STACK_LIMIT");
    owned(c,cursor);const RtShape *expected_shape=node(c,cursor)->shape;validate_sum_cursor(c,cursor);cursor->scope=0;bump(c,&c->report.force_calls);bump(c,&c->force_depth);peak(&c->report.max_force_depth,c->force_depth);
    Pending *first=NULL,*last=NULL;
    if(event(c,"force_enter")){num(c,"depth",c->force_depth);num(c,"cursor",node(c,cursor)->id);end_event(c);}
    for(;;){
        tick(c);Node *n=node(c,cursor);
        if(expected_shape->kind==RT_SUM&&n->shape!=expected_shape)fault(c,"INVARIANT");
        validate_sum_cursor(c,cursor);
        if(n->state==NS_READY||n->state==NS_CLOSURE)break;
        if(n->state==NS_HOLE)fault(c,"HOLE");
        if(n->state==NS_BUSY)fault(c,"BUSY");
        if(n->state==NS_MEMO){RtHandle *next=acquire(c,n->slots[0].target);bump(c,&c->report.memo_fast_paths);drop(c,cursor);cursor=next;continue;}
        RtHandle *pin=handle(c,n->group,n,NULL,RC_PIN);Pending *p=mem_alloc(c,sizeof(*p),MC_PENDING);p->node=n;p->pin=pin;if(last)last->next=p;else first=p;last=p;
        if(event(c,"update_pin")){num(c,"node",n->id);num(c,"pin",pin->id);num(c,"depth",c->force_depth);end_event(c);}
        if(n->state==NS_INDIRECT){RtHandle *next=acquire(c,n->slots[0].target);clear_slots(c,n);n->state=NS_BUSY;drop(c,cursor);cursor=next;}
        else if(n->state==NS_THUNK){RtHandle **captures=capture_owners(c,n);handoff_event(c,"capture_handoff",n,captures,0);clear_slots(c,n);n->state=NS_BUSY;
            if(event(c,"payload_cleared")){num(c,"node",n->id);end_event(c);}drop(c,cursor);cursor=callback(c,n,pin,captures);}
        else if(n->state==NS_APPLICATION){RtHandle **operands=capture_owners(c,n);handoff_event(c,"capture_handoff",n,operands,0);clear_slots(c,n);n->state=NS_BUSY;
            if(event(c,"payload_cleared")){num(c,"node",n->id);end_event(c);}drop(c,cursor);
            RtHandle *fn=operands[0],*arg=operands[1];mem_free(c,operands);fn=force(c,fn);cursor=invoke(c,fn,arg,pin);}
        else fault(c,"INVARIANT");
    }
    Node *final=node(c,cursor);
    for(Pending *p=first;p;p=p->next){Node *n=p->node;slot(c,n,"$target",final);n->state=NS_MEMO;n->code=NULL;bump(c,&c->report.memo_writes);
        if(n->group==final->group)bump(c,&c->report.internal_memo_slots);else bump(c,&c->report.cross_group_memo_slots);
        if(event(c,"memo_publish")){num(c,"destination",n->id);num(c,"result",final->id);num(c,"pin",p->pin->id);num(c,"depth",c->force_depth);boolean(c,"internal",n->group==final->group);end_event(c);}}
    for(Pending *p=first;p;){Pending *next=p->next;if(event(c,"update_unpin")){num(c,"node",p->node->id);num(c,"pin",p->pin->id);num(c,"depth",c->force_depth);end_event(c);}drop(c,p->pin);mem_free(c,p);p=next;}
    if(event(c,"force_return")){num(c,"depth",c->force_depth);num(c,"result",final->id);num(c,"owner",cursor->id);num(c,"group",final->group->id);str(c,"layout",final->shape->name);end_event(c);}
    --c->force_depth;return cursor;
}
static RtHandle *force_at(RtContext *c,RtHandle *h,const char *out,
                          const char *source,RtHandle *storage) {
    RtHandle *result=force(c,h);
    if(storage)result=move_owner(c,result,storage,RT_STORAGE_LOCAL);
    local(c,result);
    if(event(c,"ir_force_result")){num(c,"result",result->node->id);num(c,"group",result->group->id);str(c,"layout",result->node->shape->name);num(c,"owner",result->id);num(c,"frame",frame_id(c));str(c,"out",out);str(c,"source_variable",source);end_event(c);}return result;
}
RtHandle *rt_force(RtContext *c,RtHandle *h,const char *out,const char *source) {
    tick(c);return force_at(c,h,out,source,NULL);
}
RtHandle *rt_return(RtContext *c,RtHandle *h){
    tick(c);owned(c,h);validate_sum_cursor(c,h);
    if(h->loans || !c->frame || !c->frame->home || c->frame->returned || h->scope!=frame_id(c))fault(c,"INVARIANT");
    for(RtHandle *p=c->handles;p;p=p->next)if(p->scope==frame_id(c)&&p!=h&&p!=c->frame->home)fault(c,"INVARIANT");
    if(c->frame->home->loans)fault(c,"INVARIANT");
    RtHandle *result=escaping_owner(c,h);
    c->frame->returned=1;result->scope=0;return result;
}
/* Deadness is checked BEFORE the operation can consume any input storage. */
RtHandle *rt_new_root_into(RtContext *c,RtHandle *out,size_t n,RtHandle *const *imports) {
    tick(c);dead_storage(c,out);return new_group(c,n,imports,out);
}
RtHandle *rt_new_below_into(RtContext *c,RtHandle *out,RtHandle *ceiling,size_t n,RtHandle *const *imports) {
    tick(c);dead_storage(c,out);authority(c,ceiling);return new_group(c,n,imports,out);
}
RtHandle *rt_alloc_into(RtContext *c,RtHandle *out,RtHandle *a,const RtShape *s,RtHandle *const *fields,const char *name) {
    tick(c);dead_storage(c,out);shape(c,s);if(s->kind!=RT_DATA)fault(c,"INVARIANT");
    return local(c,allocate(c,a,s,NS_READY,NULL,s->field_count,s->fields,fields,name,"alloc",0,out));
}
RtHandle *rt_closure_into(RtContext *c,RtHandle *out,RtHandle *a,const RtCode *v,RtHandle *const *captures,const char *name) {
    tick(c);dead_storage(c,out);code(c,v,RT_FUNCTION);if(v->shape->kind!=RT_REPEAT)fault(c,"UNSUPPORTED");
    return local(c,allocate(c,a,v->shape,NS_CLOSURE,v,v->capture_count,v->captures,captures,name,"closure",0,out));
}
RtHandle *rt_thunk_into(RtContext *c,RtHandle *out,RtHandle *a,const RtCode *v,RtHandle *const *captures,const char *name) {
    tick(c);dead_storage(c,out);code(c,v,RT_THUNK);
    return local(c,allocate(c,a,v->shape,NS_THUNK,v,v->capture_count,v->captures,captures,name,"thunk",0,out));
}
RtHandle *rt_application_into(RtContext *c,RtHandle *out,RtHandle *a,RtHandle *fn,RtHandle *arg,const char *name) {
    tick(c);dead_storage(c,out);return application(c,a,fn,arg,name,0,out);
}
RtHandle *rt_application_borrow_into(RtContext *c,RtHandle *out,RtHandle *a,RtHandle *fn,RtHandle *arg,const char *name) {
    tick(c);dead_storage(c,out);bump(c,&c->report.ir_application_borrow_ops);return application(c,a,fn,arg,name,1,out);
}
RtHandle *rt_hole_into(RtContext *c,RtHandle *out,RtHandle *a,const RtShape *s,const char *name) {
    tick(c);dead_storage(c,out);return local(c,allocate(c,a,s,NS_HOLE,NULL,0,NULL,NULL,name,"hole",0,out));
}
RtHandle *rt_retain_into(RtContext *c,RtHandle *out,RtHandle *source) {
    tick(c);dead_storage(c,out);bump(c,&c->report.ir_retain_ops);return local(c,acquire_at(c,node(c,source),out));
}
RtHandle *rt_borrow_into(RtContext *c,RtHandle *out,RtHandle *source) {
    tick(c);dead_storage(c,out);bump(c,&c->report.ir_borrow_ops);owned(c,source);
    return local(c,handle_at(c,source->group,source->node,source,RC_OWNER,out));
}
RtHandle *rt_field_into(RtContext *c,RtHandle *out,RtHandle *source,size_t index,const char *name,const char *variable) {
    tick(c);dead_storage(c,out);return field_at(c,source,index,name,variable,out);
}
RtHandle *rt_force_into(RtContext *c,RtHandle *out,RtHandle *source,const char *name,const char *variable) {
    tick(c);dead_storage(c,out);owned(c,source);
    if(source->loans)fault(c,"INVARIANT");
    return force_at(c,source,name,variable,out);
}
void rt_finish_entry(RtContext *c){tick(c);if(!c->frame||c->frame->parent||c->frame->home||c->finished||c->handles||c->live_groups||c->live_nodes)fault(c,"INVARIANT");c->finished=1;}
void rt_finish_scalar(RtContext *c,RtHandle *h) {
    tick(c);owned(c,h);Node *n=node(c,h);RtShapeKind kind=n->shape->kind;
    if(kind!=RT_I64&&kind!=RT_BOOL)fault(c,"INVARIANT");
    int64_t value=ready_scalar(c,h,kind)->value;
    if(!c->frame||c->frame->parent||c->frame->home||c->finished||
       c->handles!=h||h->next||h->previous||h->loans)fault(c,"INVARIANT");
    drop(c,h);
    if(c->handles||c->live_groups||c->live_nodes)fault(c,"INVARIANT");
    c->report.scalar_result_kind=(unsigned)kind;c->report.scalar_result=value;c->finished=1;
}
static void validate_program(RtContext *c){
    const RtProgram *p=c->program;
    if(!p||!p->artifact_sha256||!p->shapes||(p->code_count&&!p->codes))fault(c,"UNSUPPORTED");
    if(p->family_count>RT_MAX_SUM_FAMILIES||(p->family_count&&!p->families)||(!p->family_count&&p->families))fault(c,"UNSUPPORTED");
    for(size_t i=0;i<p->shape_count;++i){const RtShape *s=p->shapes[i];if(!s||!s->name)fault(c,"UNSUPPORTED");
        if(s->kind==RT_DATA){if((s->name[0]=='#'||s->name[0]=='%'))fault(c,"UNSUPPORTED");if(s->field_count&&!s->fields)fault(c,"UNSUPPORTED");for(size_t j=0;j<s->field_count;++j){if(!s->fields[j].name||!registered_shape(c,s->fields[j].shape))fault(c,"UNSUPPORTED");if(j&&strcmp(s->fields[j-1].name,s->fields[j].name)>=0)fault(c,"UNSUPPORTED");}}
        else if(s->kind==RT_REPEAT){if((s->name[0]=='#'||s->name[0]=='%')||s->field_count||!registered_shape(c,s->argument)||!registered_shape(c,s->result))fault(c,"UNSUPPORTED");}
        else if(s->kind==RT_I64||s->kind==RT_BOOL){
            if(strcmp(s->name,s->kind==RT_I64?"#i64":"#bool")||s->field_count||s->fields||s->argument||s->result)fault(c,"UNSUPPORTED");
            for(size_t j=0;j<i;++j)if(p->shapes[j]->kind==s->kind)fault(c,"UNSUPPORTED");
        }
        else if(s->kind==RT_SUM){
            if(s->name[0]!='%'||!s->name[1]||s->name[1]=='%'||s->name[1]=='#'||s->name[1]=='@'||s->field_count||s->fields||s->argument||s->result)fault(c,"UNSUPPORTED");
            for(size_t j=0;j<i;++j)if(p->shapes[j]->kind==RT_SUM&&strcmp(p->shapes[j]->name,s->name)==0)fault(c,"UNSUPPORTED");
        }
        else fault(c,"UNSUPPORTED");
    }
    for(size_t i=0;i<p->family_count;++i){
        const RtFamily *f=p->families[i];
        if(!f||!registered_shape(c,f->shape)||f->shape->kind!=RT_SUM||!f->variant_count||f->variant_count>RT_MAX_SUM_VARIANTS||!f->variants)fault(c,"UNSUPPORTED");
        for(size_t j=0;j<i;++j)if(p->families[j]==f||p->families[j]->shape==f->shape)fault(c,"UNSUPPORTED");
        for(size_t j=0;j<f->variant_count;++j){
            const RtVariant *v=f->variants[j];
            if(!v||!v->name||!v->name[0]||v->family!=f->shape||v->index!=j||v->field_count>RT_MAX_SUM_FIELDS||
               (v->field_count?!v->fields:v->fields!=NULL))fault(c,"UNSUPPORTED");
            for(size_t k=0;k<v->field_count;++k){
                const RtField *field=&v->fields[k];char position[32];
                (void)snprintf(position,sizeof(position),"%zu",k);
                if(!field->name||strcmp(field->name,position)||!registered_shape(c,field->shape))fault(c,"UNSUPPORTED");
                if(field->shape->kind!=RT_I64&&field->shape->kind!=RT_BOOL&&field->shape->kind!=RT_SUM)fault(c,"UNSUPPORTED");
            }
            for(size_t k=0;k<j;++k)if(f->variants[k]==v||strcmp(f->variants[k]->name,v->name)==0)fault(c,"UNSUPPORTED");
        }
    }
    for(size_t i=0;i<p->shape_count;++i)if(p->shapes[i]->kind==RT_SUM){
        size_t matches=0;for(size_t j=0;j<p->family_count;++j)if(p->families[j]->shape==p->shapes[i])++matches;
        if(matches!=1)fault(c,"UNSUPPORTED");
    }
    for(size_t i=0;i<p->code_count;++i){const RtCode *v=p->codes[i];if(!v||!v->name||!v->body||!registered_shape(c,v->shape)||(v->capture_count&&!v->captures))fault(c,"UNSUPPORTED");
        if(v->kind!=RT_FUNCTION&&v->kind!=RT_THUNK)fault(c,"UNSUPPORTED");
        if(v->kind==RT_FUNCTION&&v->shape->kind!=RT_REPEAT)fault(c,"UNSUPPORTED");
        for(size_t j=0;j<v->capture_count;++j){if(!v->captures[j].name||!registered_shape(c,v->captures[j].shape))fault(c,"UNSUPPORTED");if(j&&strcmp(v->captures[j-1].name,v->captures[j].name)>=0)fault(c,"UNSUPPORTED");}
    }
}
static void memory_json(FILE *f,const RtMemory *m){
    fprintf(f,"{\"allocated_bytes\":%"PRIu64",\"freed_bytes\":%"PRIu64",\"live_bytes\":%"PRIu64",\"peak_bytes\":%"PRIu64",\"allocations\":%"PRIu64",\"frees\":%"PRIu64",\"live_blocks\":%"PRIu64",\"peak_blocks\":%"PRIu64"}",m->allocated_bytes,m->freed_bytes,m->live_bytes,m->peak_bytes,m->allocations,m->frees,m->live_blocks,m->peak_blocks);
}
static void report_json(FILE *f,const RtProgram *p,const RtReport *r){
    fputs("],\"status\":",f);quoted(f,r->status);fputs(",\"fault\":",f);quoted(f,r->fault);fputs(",\"artifact_sha256\":",f);quoted(f,p?p->artifact_sha256:NULL);
    fputs(",\"result\":",f);
    if(strcmp(r->status,"complete")==0&&(r->scalar_result_kind==RT_I64||r->scalar_result_kind==RT_BOOL)){
        fprintf(f,"{\"kind\":\"%s\",\"value\":",r->scalar_result_kind==RT_I64?"i64":"bool");
        if(r->scalar_result_kind==RT_I64)fprintf(f,"%"PRId64,r->scalar_result);
        else fputs(r->scalar_result?"true":"false",f);
        fputc('}',f);
    }else fputs("null",f);
    fputs(",\"observation_schema\":\"resource-ir-native/1\",\"memory\":",f);memory_json(f,&r->memory);fputs(",\"memory_categories\":{",f);
    for(size_t i=0;i<RT_MEMORY_CATEGORIES;++i){if(i)fputc(',',f);quoted(f,memory_names[i]);fputc(':',f);memory_json(f,&r->categories[i]);}fputs("},\"metrics\":{",f);
#define METRIC(k) fprintf(f,"\"" #k "\":%"PRIu64",",r->k)
    METRIC(entries_completed);METRIC(steps);METRIC(groups_allocated);METRIC(groups_closed);METRIC(nodes_allocated);METRIC(nodes_freed);METRIC(peak_groups);METRIC(peak_nodes);METRIC(peak_owner_handles);
    METRIC(owner_handle_acquisitions);METRIC(owner_handle_releases);METRIC(loan_handle_acquisitions);METRIC(loan_handle_releases);
    METRIC(force_calls);METRIC(max_force_depth);METRIC(callback_calls);METRIC(ordinary_calls);METRIC(applications_allocated);METRIC(raw_deferred_returns);METRIC(memo_writes);METRIC(internal_memo_slots);METRIC(cross_group_memo_slots);METRIC(memo_fast_paths);
    METRIC(groups_closed_during_force);METRIC(borrowed_slot_publications);METRIC(ir_retain_ops);METRIC(ir_drop_ops);METRIC(ir_borrow_ops);METRIC(ir_end_borrow_ops);METRIC(ir_application_borrow_ops);METRIC(max_activation_depth);
#undef METRIC
    uint64_t incs=0,decs=0;
    for(size_t i=0;i<RT_RC_CATEGORIES;++i){incs+=r->rc_inc[i];decs+=r->rc_dec[i];fprintf(f,"\"rc_inc_%s\":%"PRIu64",\"rc_dec_%s\":%"PRIu64",",rc_names[i],r->rc_inc[i],rc_names[i],r->rc_dec[i]);}
    fprintf(f,"\"rc_inc_total\":%"PRIu64",\"rc_dec_total\":%"PRIu64",\"repeat_calls\":%"PRIu64"},\"events_emitted\":%"PRIu64",\"events_omitted\":%"PRIu64",\"static_descriptor_bytes\":%zu,\"cleanup_claim\":",incs,decs,r->ordinary_calls,r->events_emitted,r->events_omitted,p?p->static_descriptor_bytes:0);
    quoted(f,strcmp(r->status,"complete")==0?"all runtime-owned requested blocks freed":"terminal fault; cleanup unsupported");fputs("}\n",f);
}
/* This check observes successful custody; it never clears or sweeps storage. */
static void session_checkpoint(RtContext *c) {
    MemHeader *context_header=(MemHeader *)c-1;
    if(c->handles || c->live_groups || c->live_nodes || c->live_owners ||
       c->close_first || c->close_last || c->closing || c->force_depth ||
       c->activation_depth || c->frame || c->ledger!=context_header ||
       context_header->info.previous || context_header->info.next ||
       c->report.memory.live_blocks!=1 ||
       c->report.memory.live_bytes!=context_header->info.requested)
        fault(c,"INVARIANT");
}
static int invalid_session(RtReport *report) {
    if(report){*report=(RtReport){0};report->status="fault";report->fault="INVARIANT";}
    return 2;
}
int rt_session_snapshot(const RtContext *c,RtReport *report) {
    if(!c)return invalid_session(report);
    if(report)*report=c->report;
    return strcmp(c->report.status,"complete")==0?0:2;
}
int rt_session_open(const RtProgram *program,const RtOptions *options,
                    RtContext **session,RtReport *report) {
    if(!session || *session)return invalid_session(report);
    size_t requested=sizeof(MemHeader)+sizeof(RtContext);
    MemHeader *h=malloc(requested);
    if(!h){
        if(report){*report=(RtReport){0};report->status="fault";report->fault="OOM";}
        return 2;
    }
    memset(h,0,requested);
    RtContext *c=(RtContext *)(h+1);
    h->info.requested=requested;h->info.category=MC_CONTEXT;
    c->ledger=h;c->program=program;
    c->options=options?*options:(RtOptions){1000000,0};
    c->fuel_remaining=c->options.fuel;
    c->report.status="complete";
    c->report.memory=(RtMemory){requested,0,requested,requested,1,0,1,1};
    c->report.categories[MC_CONTEXT]=c->report.memory;
    *session=c;
    /* Every potentially faulting checkpoint uses a CURRENT setjmp boundary. */
    c->api_active=1;
    if(setjmp(c->failure)==0){validate_program(c);session_checkpoint(c);}
    c->api_active=0;
    return rt_session_snapshot(c,report);
}
int rt_session_step(RtContext *c,RtEntry entry,RtReport *report) {
    if(!c || c->api_active)return invalid_session(report);
    /* A poisoned frame pointer may refer to expired C stack storage. Never
     * inspect it, the heap, or an old jump buffer before this poison guard. */
    if(strcmp(c->report.status,"complete")!=0)return rt_session_snapshot(c,report);
    c->api_active=1;
    if(setjmp(c->failure)==0){
        session_checkpoint(c);
        if(!entry)fault(c,"UNSUPPORTED");
        /* Reset entry bookkeeping ONLY AFTER proving prior resource emptiness. */
        c->finished=0;c->fuel_remaining=c->options.fuel;
        c->report.scalar_result_kind=0;c->report.scalar_result=0;
        Frame frame;
        frame_enter(c,&frame,NULL,"entry",NULL,NULL,NULL);
        entry(c);
        if(!c->finished)fault(c,"INVARIANT");
        frame_leave(c,&frame);
        session_checkpoint(c);
        bump(c,&c->report.entries_completed);
    }
    c->api_active=0;
    return rt_session_snapshot(c,report);
}
int rt_session_close(RtContext **session,RtReport *report) {
    if(!session || !*session)return invalid_session(report);
    RtContext *c=*session;
    if(c->api_active)return invalid_session(report);
    /* Diagnostic close does not reclaim poison or inspect stale semantic lists. */
    if(strcmp(c->report.status,"complete")!=0)return rt_session_snapshot(c,report);
    c->api_active=1;
    if(setjmp(c->failure)!=0){c->api_active=0;return rt_session_snapshot(c,report);}
    session_checkpoint(c);
    MemHeader *h=(MemHeader *)c-1;
    size_t requested=h->info.requested;
    RtMemory total=account_free_preflight(c,&c->report.memory,requested);
    RtMemory category=account_free_preflight(c,&c->report.categories[MC_CONTEXT],requested);
    c->report.memory=total;c->report.categories[MC_CONTEXT]=category;
    RtReport snapshot=c->report;
    *session=NULL;
    free(h);
    if(report)*report=snapshot;
    return 0;
}
static void destroy_add(uint64_t *value,uint64_t amount,unsigned *overflow) {
    if(UINT64_MAX-*value<amount){*value=UINT64_MAX;*overflow=1;}else *value+=amount;
}
static void destroy_record(RtDestroyReport *r,const MemHeader *h) {
    destroy_add(&r->retired_blocks,1,&r->totals_overflow);
    destroy_add(&r->retired_bytes,(uint64_t)h->info.requested,&r->totals_overflow);
    destroy_add(&r->category_blocks[h->info.category],1,&r->totals_overflow);
    destroy_add(&r->category_bytes[h->info.category],(uint64_t)h->info.requested,&r->totals_overflow);
}
int rt_session_destroy_terminal(RtContext **session,RtReport *before,RtDestroyReport *destroyed) {
    if(!destroyed)return 2;
    *destroyed=(RtDestroyReport){0};
    if(!session){destroyed->status=RT_DESTROY_INVALID;return 2;}
    RtContext *c=*session;
    if(!c){destroyed->status=RT_DESTROY_EMPTY;return 0;}
    if(c->api_active){destroyed->status=RT_DESTROY_ACTIVE;return 2;}
    if(before)*before=c->report;
    c->api_active=2;
    MemHeader *context=(MemHeader *)c-1;
    destroyed->status=RT_DESTROY_DONE;
    /* Header-only traversal: interrupted payloads and stack aliases are irrelevant.
     * Ledger completeness/header validity and exclusive domain surrender are required. */
    for(MemHeader *h=c->ledger;h;){
        MemHeader *next=h->info.next;
        if(h!=context){destroy_record(destroyed,h);free(h);}
        h=next;
    }
    destroy_record(destroyed,context);
    *session=NULL;
    free(context);
    return 0;
}
static void destroy_json(FILE *f,const RtDestroyReport *r) {
    fprintf(f,"{\"status\":%u,\"retired_blocks\":%"PRIu64",\"retired_bytes\":%"PRIu64
              ",\"totals_overflow\":%s,\"categories\":{",(unsigned)r->status,r->retired_blocks,
              r->retired_bytes,r->totals_overflow?"true":"false");
    for(size_t i=0;i<RT_MEMORY_CATEGORIES;++i){if(i)fputc(',',f);quoted(f,memory_names[i]);
        fprintf(f,":{\"blocks\":%"PRIu64",\"bytes\":%"PRIu64"}",r->category_blocks[i],r->category_bytes[i]);}
    fputs("}}",f);
}
int rt_run_repeat_destroy_fault(const RtProgram *program,RtEntry entry,const RtOptions *options,
                               uint64_t repetitions,FILE *output,RtReport *report,RtDestroyReport *destroyed) {
    if(output)fputs("{\"schema\":\"resource-ir-terminal-run/1\",\"evaluation\":{\"events\":[",output);
    RtContext *c=NULL;RtReport snapshot;
    RtDestroyReport release={0};release.status=RT_DESTROY_EMPTY;
    int result=rt_session_open(program,options,&c,&snapshot);
    if(c && result==0)c->output=output;
    if(result==0 && !entry)result=rt_session_step(c,entry,NULL);
    if(result==0){for(uint64_t i=0;i<repetitions;++i){result=rt_session_step(c,entry,NULL);if(result)break;}}
    if(c)result=rt_session_close(&c,&snapshot);
    if(result && c){
        /* The failing API has unwound. No callback/ordinary helper remains active. */
        (void)rt_session_destroy_terminal(&c,NULL,&release);
    }
    if(report)*report=snapshot;
    if(destroyed)*destroyed=release;
    if(output){report_json(output,program,&snapshot);fputs(",\"destruction\":",output);destroy_json(output,&release);fputs("}\n",output);}
    return result;
}
int rt_run_repeat(const RtProgram *program,RtEntry entry,const RtOptions *options,
                  uint64_t repetitions,FILE *output,RtReport *report) {
    if(output)fputs("{\"events\":[",output);
    RtContext *c=NULL;
    RtReport snapshot;
    int result=rt_session_open(program,options,&c,&snapshot);
    if(c && result==0)c->output=output;
    if(result==0 && !entry)result=rt_session_step(c,entry,NULL);
    if(result==0){
        for(uint64_t i=0;i<repetitions;++i){
            result=rt_session_step(c,entry,NULL);
            if(result)break;
        }
    }
    if(c)result=rt_session_close(&c,&snapshot);
    if(report)*report=snapshot;
    if(output)report_json(output,program,&snapshot);
    return result;
}
int rt_run(const RtProgram *program,RtEntry entry,const RtOptions *options,
           FILE *output,RtReport *report) {
    return rt_run_repeat(program,entry,options,1,output,report);
}
