/* Genuine Stage05B bounded metadata and dynamic guard kernel.
 * Source preparation only. No project/compiler/runtime execution receipt. */
#include "rir8_runtime_internal.h"
#include <stdlib.h>
#include <string.h>

#define N RT8_NULL
#define G(c,n,s,d,t,r,f,p) do { rt8_private_charge((c),16); \
 rt8_private_guard_seen((c),(n)); if(!(p)) \
 rt8_private_guard_fault((c),RT8_STATUS_##s,RT8_DETAIL_##d,(n),(t),(r),(f)); } while(0)

static Rt8Diagnostic diagnostic(void) {
 Rt8Diagnostic d={0}; d.phase=RT8_PHASE_LOOKUP;
 d.domain=d.object=d.row=d.field=d.guard_index=N; return d;
}
static void reader_done(Rt8Context *c,uint32_t status,const Rt8Diagnostic *d) {
 if(status==RT8_STATUS_OK)return;
 c->report.location.status=d->status;c->report.location.phase=d->phase;
 c->report.location.detail=d->detail;c->report.location.region=d->region;
 c->report.location.domain_kind=d->domain_kind;c->report.location.domain=d->domain;
 c->report.location.object=d->object;c->report.location.row=d->row;
 c->report.location.field=d->field;c->report.location.guard_index=d->guard_index;
 rt8_private_fault(c,RT8_FAULT_TYPED_GUARD);
}
void rt8_private_charge(Rt8Context *c,uint64_t n) {
 Rt8Diagnostic d=diagnostic(); Rt8ReadState s={&c->guard_work,&d};
 reader_done(c,rt8_work_reserve(&s,n),&d);
}
void rt8_private_guard_seen(Rt8Context *c,uint32_t guard) {
 if(guard>=27)rt8_private_fault(c,RT8_FAULT_INVARIANT);
 c->report.guards_checked_mask|=UINT32_C(1)<<guard;
}
_Noreturn void rt8_private_guard_fault(Rt8Context *c,uint32_t status,uint32_t detail,
 uint32_t guard,uint32_t domain,uint32_t row,uint32_t field) {
 Rt8FaultInfo *d=&c->report.location;
 d->status=status;d->phase=RT8_PHASE_DYNAMIC_GUARD;d->detail=detail;
 d->region=RT8_REGION_NONE;d->domain_kind=RT8_DOMAIN_KIND_NONE;
 d->domain=d->object=N;d->row=row;d->field=field;d->guard_index=guard;
 if(domain>=1&&domain<=20){d->region=RT8_REGION_PACKET;
  d->domain_kind=RT8_DOMAIN_KIND_PACKET_TABLE;d->domain=domain;
  d->object=c->program.typed_header.table[domain-1].object;}
 if(guard<27){c->report.guards_checked_mask|=UINT32_C(1)<<guard;
  c->report.guards_failed_mask|=UINT32_C(1)<<guard;}
 rt8_private_fault(c,RT8_FAULT_TYPED_GUARD);
}
void rt8_private_enter(Rt8Context *c,Rt8Operation op,int tick) {
 /* Outside a current boundary no old jump buffer can safely be used. Such
  * direct C calls violate the explicit ctx-helper precondition. */
 if(!c||c->api_active!=1)abort();
 if(c->report.state!=RT8_RUN_COMPLETE)rt8_private_fault(c,RT8_FAULT_INVARIANT);
 if(!c->frame||c->frame->returned||c->finished)rt8_private_fault(c,RT8_FAULT_INVARIANT);
 if(tick)rt8_private_tick(c);
 rt8_private_charge(c,32);
 if((uint32_t)op>(uint32_t)RT8_OP_ACCESSOR)rt8_private_fault(c,RT8_FAULT_INVARIANT);
 if(c->frame->active_intro||c->frame->execution.kind!=IR8_PACKET_ORIGIN_KIND_CONCRETE){
  int permitted=op==RT8_OP_NEW_BELOW||op==RT8_OP_SCALAR||op==RT8_OP_CLOSURE||
   op==RT8_OP_THUNK||op==RT8_OP_APPLICATION||op==RT8_OP_APPLICATION_BORROW||
   op==RT8_OP_RETAIN||op==RT8_OP_DROP||op==RT8_OP_BORROW||op==RT8_OP_END_BORROW||
   op==RT8_OP_ACCESSOR||(op==RT8_OP_SEAL&&c->frame->active_intro)||
   (op==RT8_OP_RETURN&&!c->frame->active_intro);
  G(c,25,STATE,APPLICABILITY,N,N,N,permitted);
 }
}
void rt8_private_table(Rt8Context *c,uint32_t domain,uint32_t row,void *out,size_t bytes) {
 Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_table_read(&c->program,domain,row,out,bytes,&s),&d);
}
void rt8_private_descriptor(Rt8Context *c,uint32_t domain,uint32_t row,void *out,size_t bytes) {
 Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_descriptor_read(&c->program,domain,row,out,bytes,&s),&d);
}
void rt8_private_vector(Rt8Context *c,uint32_t object,uint32_t element,uint32_t row,void *out,size_t bytes) {
 Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_object_read(&c->program,object,element,row,out,bytes,&s),&d);
}
uint32_t rt8_private_table_auth(Rt8Context *c,uint32_t domain,const void *ref) {
 uint32_t row=N;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_table_auth(&c->program,domain,ref,&row,&s),&d);return row;
}
uint32_t rt8_private_descriptor_auth(Rt8Context *c,uint32_t domain,const void *ref) {
 uint32_t row=N;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_descriptor_auth(&c->program,domain,ref,&row,&s),&d);return row;
}
const void *rt8_private_table_ref(Rt8Context *c,uint32_t domain,uint32_t row) {
 const void *out=NULL;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_table_ref(&c->program,domain,row,&out,&s),&d);return out;
}
const void *rt8_private_descriptor_ref(Rt8Context *c,uint32_t domain,uint32_t row) {
 const void *out=NULL;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_descriptor_ref(&c->program,domain,row,&out,&s),&d);return out;
}
static uint32_t table_count(Rt8Context *c,uint32_t domain) {
 G(c,0,REFERENCE,DOMAIN,N,N,N,domain>=1&&domain<=20);
 rt8_private_charge(c,1);return c->program.typed_header.table[domain-1].count;
}
static unsigned char pool_byte(Rt8Context *c,uint32_t offset) {
 unsigned char x=0;
 rt8_private_vector(c,c->program.packet_header.string_pool_object,
  IR8_PACKET_ELEMENT_UTF8_BYTE,offset,&x,sizeof(x));return x;
}
const char *rt8_private_string(Rt8Context *c,uint32_t offset) {
 const Ir8PacketObjectDirectoryEntry *p=&c->program.string_pool;
 uint32_t count=p->count;uintptr_t base=(uintptr_t)c->program.program.packet;
 G(c,0,REFERENCE,OFFSET,N,N,N,offset<count);
 if(offset)G(c,0,REFERENCE,OFFSET,N,N,N,pool_byte(c,offset-1)==0);
 G(c,0,REFERENCE,LENGTH,N,N,N,pool_byte(c,offset)!=0);
 uint32_t i=offset;
 for(;;){rt8_private_charge(c,3);if(i>=count)rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_LENGTH,0,N,N,N);
  if(pool_byte(c,i)==0)break;
  ++i;}
 G(c,0,REFERENCE,OVERFLOW,N,N,N,p->offset<=UINTPTR_MAX-base);
 uintptr_t start=base+p->offset;
 G(c,0,REFERENCE,OVERFLOW,N,N,N,offset<=UINTPTR_MAX-start);
 /* Root/member range and string-boundary identity were checked before forming
  * a borrowed pointer. The actual packet root has immutable session lifetime. */
 rt8_private_charge(c,sizeof(const char *)+1);
 return (const char *)(start+offset);
}
void rt8_private_label(Rt8Context *c,const char *label) {
 uint32_t id=N;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 rt8_private_guard_seen(c,0);reader_done(c,rt8_view_label_auth(&c->program,label,&id,&s),&d);
}
static size_t text_length(Rt8Context *c,const char *s) {
 const Rt8ProgramView *v=&c->program;const char *candidate;
 /* Exact starts only. Native labels and packet strings are separate pools. */
 for(uint32_t i=0;;++i){rt8_private_charge(c,3);if(i>=v->binding_header.label_count)break;
  Rt8Diagnostic d=diagnostic();Rt8ReadState rs={&c->guard_work,&d};
  reader_done(c,rt8_view_label(v,i,&candidate,&rs),&d);
  if(candidate==s){const char *next=NULL;uintptr_t end;
   rt8_private_charge(c,5);
   if(i+1<v->binding_header.label_count){
    reader_done(c,rt8_view_label(v,i+1,&next,&rs),&d);end=(uintptr_t)next;
   }else{uintptr_t root=(uintptr_t)v->program.binding;
    G(c,0,REFERENCE,OVERFLOW,N,N,N,v->binding_header.label_bytes_offset<=UINTPTR_MAX-root);
    end=root+v->binding_header.label_bytes_offset;
    G(c,0,REFERENCE,OVERFLOW,N,N,N,v->binding_header.label_bytes<=UINTPTR_MAX-end);
    end+=v->binding_header.label_bytes;
   }
   uintptr_t start=(uintptr_t)s;
   G(c,0,REFERENCE,LENGTH,N,N,N,end>start&&end-start<=SIZE_MAX);
   size_t max=(size_t)(end-start);
   for(size_t j=0;j<max;++j){rt8_private_charge(c,4);if((unsigned char)s[j]==0)return j;}
   rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_LENGTH,0,N,N,N);}}
 for(uint32_t i=0;i<v->string_pool.count;){rt8_private_charge(c,3);
  candidate=rt8_private_string(c,i);size_t length=0;
  for(;;){rt8_private_charge(c,4);if(length>=(size_t)(v->string_pool.count-i))
    rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_LENGTH,0,N,N,N);
   if(pool_byte(c,i+(uint32_t)length)==0)break;
   ++length;}
  rt8_private_charge(c,2);if(candidate==s)return length;
  i+=(uint32_t)length+1;
 }
 rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_UNREGISTERED,0,N,N,N);
}
int rt8_private_text_equal(Rt8Context *c,const char *a,const char *b) {
 size_t na=text_length(c,a),nb=text_length(c,b);rt8_private_charge(c,1);
 if(na!=nb)return 0;
 for(size_t i=0;i<na;++i){rt8_private_charge(c,4);if((unsigned char)a[i]!=(unsigned char)b[i])return 0;}return 1;
}
uint32_t rt8_private_resolve(Rt8Context *c,uint32_t type,const Rt8Env *env) {
 uint32_t eid=rt8_private_table_auth(c,4,env);Ir8PacketType t;
 rt8_private_table(c,1,type,&t,sizeof(t));
 for(uint32_t i=0,n=table_count(c,12);i<n;++i){Ir8PacketTypeResolution r;rt8_private_charge(c,3);
  rt8_private_table(c,12,i,&r,sizeof(r));if(r.type==type&&r.env==eid)return r.result;}
 rt8_private_guard_fault(c,RT8_STATUS_TYPE,RT8_DETAIL_MISSING,3,1,type,N);
}
int rt8_private_type_closed(Rt8Context *c,uint32_t type) {
 uint32_t stack[RT8_MAX_WALK_DEPTH];size_t depth=0;
 rt8_private_charge(c,sizeof(uint32_t)+1);stack[depth++]=type;
 while(depth){Ir8PacketType t;rt8_private_charge(c,3);type=stack[--depth];rt8_private_table(c,1,type,&t,sizeof(t));
  rt8_private_charge(c,3);if(t.tag==IR8_PACKET_TYPE_TAG_RIGID)return 0;
  if(t.tag==IR8_PACKET_TYPE_TAG_ARROW){
   G(c,3,TYPE,COUNT,1,type,N,depth<=RT8_MAX_WALK_DEPTH-2);
   rt8_private_charge(c,2*sizeof(uint32_t)+2);stack[depth++]=t.result;stack[depth++]=t.argument;
  }else G(c,3,TYPE,EQUATION,1,type,1,t.tag==IR8_PACKET_TYPE_TAG_CLOSED);
 }
 return 1;
}
const Rt8Access *rt8_private_access(Rt8Context *c,uint32_t site,uint32_t origin,
 uint32_t mode,uint32_t use,uint32_t scheme) {
 for(uint32_t i=0,n=table_count(c,17);i<n;++i){Ir8PacketAccess a;rt8_private_charge(c,6);
  rt8_private_table(c,17,i,&a,sizeof(a));
  if(a.site==site&&a.origin_env==origin&&a.mode==mode&&a.use_env==use&&a.scheme==scheme)
   return rt8_private_table_ref(c,17,i);}
 rt8_private_guard_fault(c,RT8_STATUS_ORIGIN,RT8_DETAIL_MISSING,1,14,site,N);
}
static void site_execution(Rt8Context *c,uint32_t sid,uint32_t eid,Ir8PacketSiteExecution *out) {
 for(uint32_t i=0,n=table_count(c,15);i<n;++i){Ir8PacketSiteExecution r;rt8_private_charge(c,3);
  rt8_private_table(c,15,i,&r,sizeof(r));if(r.site==sid&&r.env==eid){rt8_private_charge(c,sizeof(r));*out=r;return;}}
 rt8_private_guard_fault(c,RT8_STATUS_ORIGIN,RT8_DETAIL_MISSING,1,14,sid,N);
}
static void origin_check(Rt8Context *c,const Rt8Origin *o,const Ir8PacketSite *site,
 const Ir8PacketSiteExecution *execution) {
 uint32_t eid=rt8_private_table_auth(c,4,o->env);Ir8PacketEnv e;
 rt8_private_table(c,4,eid,&e,sizeof(e));
 G(c,1,ORIGIN,EQUATION,14,site->id,3,execution->env==eid&&execution->site==site->id&&execution->origin_kind==o->kind);
 if(o->kind==IR8_PACKET_ORIGIN_KIND_CONCRETE){
  G(c,1,ORIGIN,EQUATION,14,site->id,3,eid==0&&e.mode==IR8_PACKET_ENV_MODE_CONCRETE&&site->scope==N&&o->capsule_id==0&&o->creation_activation==0);
 }else{
  G(c,1,ORIGIN,EQUATION,14,site->id,3,e.scheme==site->scope&&site->scope!=N&&o->capsule_id!=0&&o->capsule_id<=c->next_capsule);
  if(o->kind==IR8_PACKET_ORIGIN_KIND_GENERIC)
   G(c,1,ORIGIN,EQUATION,14,site->id,3,e.mode==IR8_PACKET_ENV_MODE_NEUTRAL&&o->creation_activation==0);
  else G(c,1,ORIGIN,EQUATION,14,site->id,3,o->kind==IR8_PACKET_ORIGIN_KIND_INSTANCE&&e.mode==IR8_PACKET_ENV_MODE_CLOSED&&o->creation_activation!=0&&o->creation_activation<=c->next_frame);
 }
}
const Ir8PacketCodeExecution *rt8_private_code_execution(Rt8Context *c,const Rt8Code *code,
 const Rt8Env *env,Ir8PacketCodeTyping *typing,Ir8PacketCodeExecution *execution) {
 uint32_t id=N,eid=rt8_private_table_auth(c,4,env);Rt8Code binding;
 Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};
 reader_done(c,rt8_view_code_auth(&c->program,code,&id,&s),&d);
 reader_done(c,rt8_view_code_read(&c->program,id,&binding,&s),&d);
 rt8_private_table(c,5,id,typing,sizeof(*typing));
 G(c,10,ORIGIN,EQUATION,5,id,0,binding.code_id==id&&binding.body!=NULL&&typing->id==id);
 for(uint32_t i=0,n=table_count(c,6);i<n;++i){Ir8PacketCodeExecution e;rt8_private_charge(c,3);
  rt8_private_table(c,6,i,&e,sizeof(e));if(e.code==id&&e.env==eid){rt8_private_charge(c,sizeof(e));*execution=e;return rt8_private_table_ref(c,6,i);}}
 rt8_private_guard_fault(c,RT8_STATUS_ORIGIN,RT8_DETAIL_MISSING,10,5,id,N);
}
void rt8_private_site_facts(Rt8Context *c,const Rt8Site *site,uint32_t category,
 const Rt8Code *code,const Rt8Shape *shape,Rt8SiteFacts *out) {
 Rt8SiteFacts f;Ir8PacketEnv env;uint32_t sid=rt8_private_table_auth(c,14,site);
 rt8_private_table(c,14,sid,&f.site,sizeof(f.site));
 G(c,1,ORIGIN,APPLICABILITY,14,sid,5,c->frame!=NULL&&f.site.category==category);
 uint32_t eid=rt8_private_table_auth(c,4,c->frame->execution.env);
 rt8_private_table(c,4,eid,&env,sizeof(env));
 if(f.site.context_tag==IR8_PACKET_SITE_CONTEXT_INTRODUCTION){
  uint32_t iid=rt8_private_table_auth(c,18,c->frame->active_intro);Ir8PacketIntro intro;
  rt8_private_table(c,18,iid,&intro,sizeof(intro));
  G(c,1,ORIGIN,EQUATION,14,sid,9,iid==f.site.context_intro&&intro.scheme==f.site.scope&&env.mode==IR8_PACKET_ENV_MODE_NEUTRAL);
 }else if(f.site.context_tag==IR8_PACKET_SITE_CONTEXT_EXECUTION){
  Ir8PacketCodeTyping ct;Ir8PacketCodeExecution ce;
  (void)rt8_private_code_execution(c,c->frame->code,c->frame->execution.env,&ct,&ce);
  G(c,1,ORIGIN,EQUATION,14,sid,10,!c->frame->active_intro&&ct.id==f.site.context_code&&ct.scope==f.site.context_scheme&&env.scheme==ct.scope);
 }else G(c,1,ORIGIN,EQUATION,14,sid,8,f.site.context_tag==IR8_PACKET_SITE_CONTEXT_CONCRETE&&!c->frame->active_intro&&eid==0);
 site_execution(c,sid,eid,&f.execution);
 rt8_private_charge(c,sizeof(f.origin));f.origin=c->frame->execution;
 origin_check(c,&f.origin,&f.site,&f.execution);
 Ir8PacketRepresentation rep;rt8_private_table(c,9,f.execution.representation,&rep,sizeof(rep));
 rt8_private_descriptor(c,1,rep.shape,&f.shape,sizeof(f.shape));
 G(c,2,ORIGIN,EQUATION,14,sid,7,f.shape.representation==rep.id&&rep.id==f.execution.representation);
 f.shape_ref=rt8_private_descriptor_ref(c,1,rep.shape);f.site_ref=site;
 if(shape){uint32_t actual=rt8_private_descriptor_auth(c,1,shape);G(c,2,STATE,EQUATION,14,sid,7,actual==rep.shape);}
 if(f.site.code!=N){Ir8PacketCodeTyping ct;Ir8PacketCodeExecution ce;
  (void)rt8_private_code_execution(c,code,f.origin.env,&ct,&ce);
  G(c,10,ORIGIN,EQUATION,14,sid,6,ct.id==f.site.code&&ce.id==f.execution.code_execution&&
   ((category==IR8_PACKET_SITE_CATEGORY_CLOSURE&&ct.kind==IR8_PACKET_CODE_KIND_FUNCTION)||
    (category==IR8_PACKET_SITE_CATEGORY_THUNK&&ct.kind==IR8_PACKET_CODE_KIND_THUNK)));
 }else G(c,10,ORIGIN,EQUATION,14,sid,6,code==NULL&&f.execution.code_execution==N);
 f.principal_access=rt8_private_access(c,sid,eid,IR8_PACKET_ACCESS_MODE_MONO,eid,N);
 rt8_private_charge(c,sizeof(f));*out=f;
}
static size_t expected_payload(Rt8Context *c,uint32_t kind,uint32_t *storage) {
 rt8_private_charge(c,6);
 if(kind==IR8_PACKET_SHAPE_KIND_I64||kind==IR8_PACKET_SHAPE_KIND_BOOL){*storage=RT8_STORAGE_CLASS_SCALAR;return sizeof(Rt8ScalarNode);}
 if(kind==IR8_PACKET_SHAPE_KIND_SUM){*storage=RT8_STORAGE_CLASS_SUM;return sizeof(Rt8SumNode);}
 G(c,2,STATE,APPLICABILITY,N,N,N,kind==IR8_PACKET_SHAPE_KIND_DATA||kind==IR8_PACKET_SHAPE_KIND_REPEAT||kind==IR8_PACKET_SHAPE_KIND_OPEN);
 *storage=RT8_STORAGE_CLASS_BASE;return sizeof(Rt8Node);
}
void rt8_private_node_state(Rt8Context *c,Rt8Node *n,const Rt8ValueFacts *v) {
 size_t capacity=0,used=0;uint32_t category=v->site.category;int code_required=0;
 Ir8PacketCodeTyping typing;
 rt8_private_charge(c,12);
 if(category==IR8_PACKET_SITE_CATEGORY_DATA){
  G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_READY&&v->shape.kind==IR8_PACKET_SHAPE_KIND_DATA);
  capacity=used=v->shape.field_count;
  G(c,2,STATE,COUNT,14,v->site.id,5,capacity<=RT8_MAX_DATA_FIELDS);
 }else if(category==IR8_PACKET_SITE_CATEGORY_SCALAR){
  G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_READY&&(v->shape.kind==IR8_PACKET_SHAPE_KIND_I64||v->shape.kind==IR8_PACKET_SHAPE_KIND_BOOL));
  if(v->shape.kind==IR8_PACKET_SHAPE_KIND_BOOL){int64_t value;rt8_private_charge(c,sizeof(value));memcpy(&value,&((Rt8ScalarNode *)n)->value,sizeof(value));
   G(c,2,STATE,EQUATION,14,v->site.id,5,value==0||value==1);}
 }else if(category==IR8_PACKET_SITE_CATEGORY_SUM){
  const Rt8Variant *variant;Ir8PacketVariantSpec spec;
  G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_READY&&v->shape.kind==IR8_PACKET_SHAPE_KIND_SUM);
  rt8_private_charge(c,sizeof(variant));memcpy(&variant,&((Rt8SumNode *)n)->variant,sizeof(variant));
  uint32_t vid=rt8_private_descriptor_auth(c,4,variant);rt8_private_descriptor(c,4,vid,&spec,sizeof(spec));
  G(c,2,STATE,EQUATION,14,v->site.id,13,spec.family==v->site.sum_family&&spec.index==v->site.sum_variant&&spec.shape==v->shape.shape&&spec.field_count<=RT8_MAX_VARIANT_FIELDS);
  capacity=used=spec.field_count;
 }else if(category==IR8_PACKET_SITE_CATEGORY_CLOSURE||category==IR8_PACKET_SITE_CATEGORY_THUNK){
  rt8_private_table(c,5,v->site.code,&typing,sizeof(typing));
  G(c,10,ORIGIN,EQUATION,5,typing.id,1,typing.captures.count<=RT8_MAX_CAPTURES&&
   ((category==IR8_PACKET_SITE_CATEGORY_CLOSURE&&typing.kind==IR8_PACKET_CODE_KIND_FUNCTION)||
    (category==IR8_PACKET_SITE_CATEGORY_THUNK&&typing.kind==IR8_PACKET_CODE_KIND_THUNK)));
  capacity=typing.captures.count;
  if(category==IR8_PACKET_SITE_CATEGORY_CLOSURE){
   G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_CLOSURE&&(v->shape.kind==IR8_PACKET_SHAPE_KIND_REPEAT||v->shape.kind==IR8_PACKET_SHAPE_KIND_OPEN));
   used=capacity;code_required=1;
  }else{
   if(capacity<1)capacity=1;
   G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_THUNK||n->state==RT8_NS_BUSY||n->state==RT8_NS_MEMO);
   used=n->state==RT8_NS_THUNK?typing.captures.count:n->state==RT8_NS_MEMO?1:0;
   code_required=n->state!=RT8_NS_MEMO;
  }
 }else if(category==IR8_PACKET_SITE_CATEGORY_HOLE){
  capacity=1;
  G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_HOLE||n->state==RT8_NS_INDIRECT||n->state==RT8_NS_BUSY||n->state==RT8_NS_MEMO);
  used=n->state==RT8_NS_INDIRECT||n->state==RT8_NS_MEMO?1:0;
 }else if(category==IR8_PACKET_SITE_CATEGORY_APPLICATION){
  capacity=2;
  G(c,25,STATE,STATE,14,v->site.id,5,n->state==RT8_NS_APPLICATION||n->state==RT8_NS_BUSY||n->state==RT8_NS_MEMO);
  used=n->state==RT8_NS_APPLICATION?2:n->state==RT8_NS_MEMO?1:0;
 }else rt8_private_guard_fault(c,RT8_STATUS_STATE,RT8_DETAIL_APPLICABILITY,25,14,v->site.id,5);
 G(c,25,STATE,COUNT,14,v->site.id,5,n->capacity==capacity&&n->used==used);
 if(capacity){G(c,2,STATE,OVERFLOW,14,v->site.id,5,capacity<=SIZE_MAX/sizeof(Rt8Slot));
  size_t extent=rt8_private_extent(c,n->slots,RT8_MC_SLOTS);
  G(c,2,STATE,LENGTH,14,v->site.id,5,extent==capacity*sizeof(Rt8Slot));
 }else G(c,2,STATE,EQUATION,14,v->site.id,5,n->slots==NULL);
 if(code_required){Ir8PacketCodeTyping ct;Ir8PacketCodeExecution ce;
  (void)rt8_private_code_execution(c,n->code,n->origin.env,&ct,&ce);
  G(c,10,ORIGIN,EQUATION,14,v->site.id,6,ct.id==v->site.code&&ce.id==v->execution.code_execution);
  if(category==IR8_PACKET_SITE_CATEGORY_CLOSURE){Ir8PacketType arrow;
   rt8_private_table(c,1,ce.callable_type,&arrow,sizeof(arrow));
   G(c,10,TYPE,EQUATION,5,ct.id,4,arrow.tag==IR8_PACKET_TYPE_TAG_ARROW&&arrow.protocol==IR8_PACKET_PROTOCOL_REPEAT&&ce.callable_type==v->execution.principal_type&&
    arrow.result_identity==(ct.expected_identity_flag?IR8_PACKET_RESULT_IDENTITY_ARGUMENT:IR8_PACKET_RESULT_IDENTITY_UNKNOWN));}
 }else G(c,10,STATE,EQUATION,14,v->site.id,6,n->code==NULL);
}
void rt8_private_node_access(Rt8Context *c,Rt8Node *n,const Rt8Access *access,int mono,Rt8ValueFacts *out) {
 Rt8ValueFacts v;Rt8Node local;uint32_t storage=0;
 /* No read through n, including its Site, precedes a trusted matching block. */
 size_t extent=rt8_private_extent(c,n,RT8_MC_NODE);
 G(c,2,STATE,LENGTH,N,N,N,extent>=sizeof(local));
 rt8_private_charge(c,sizeof(local));memcpy(&local,n,sizeof(local));
 G(c,2,STATE,LENGTH,N,N,N,rt8_private_extent(c,local.group,RT8_MC_GROUP)==sizeof(Rt8Group));
 G(c,9,OWNERSHIP,OWNER,N,N,N,local.group->id!=0&&local.group->id<=c->next_group&&local.group->count!=0);
 uint32_t sid=rt8_private_table_auth(c,14,local.origin_site);
 uint32_t eid=rt8_private_table_auth(c,4,local.origin.env);
 uint32_t aid=rt8_private_table_auth(c,17,access);
 rt8_private_table(c,14,sid,&v.site,sizeof(v.site));
 rt8_private_table(c,17,aid,&v.row,sizeof(v.row));
 G(c,1,ORIGIN,EQUATION,17,aid,1,v.row.site==sid&&v.row.origin_env==eid);
 if(mono)G(c,12,TYPE,APPLICABILITY,17,aid,3,v.row.mode==IR8_PACKET_ACCESS_MODE_MONO);
 else G(c,1,ORIGIN,EQUATION,17,aid,3,v.row.mode==IR8_PACKET_ACCESS_MODE_MONO||v.row.mode==IR8_PACKET_ACCESS_MODE_SCHEME);
 site_execution(c,sid,eid,&v.execution);origin_check(c,&local.origin,&v.site,&v.execution);
 uint32_t shape=rt8_private_descriptor_auth(c,1,local.shape);Ir8PacketRepresentation rep;
 rt8_private_descriptor(c,1,shape,&v.shape,sizeof(v.shape));
 rt8_private_table(c,9,v.execution.representation,&rep,sizeof(rep));
 G(c,2,STATE,EQUATION,14,sid,7,rep.shape==shape&&v.shape.representation==rep.id);
 size_t exact=expected_payload(c,v.shape.kind,&storage);
 G(c,2,STATE,LENGTH,14,sid,7,extent==exact&&local.storage_class==storage);
 G(c,1,ORIGIN,EQUATION,14,sid,0,local.id!=0&&local.id<=c->next_node);
 if(v.row.mode==IR8_PACKET_ACCESS_MODE_MONO){
  const Rt8Env *use=rt8_private_table_ref(c,4,v.row.use_env);
  uint32_t type=rt8_private_resolve(c,v.site.principal_type,use);
  G(c,3,TYPE,EQUATION,17,aid,5,type==v.row.type&&v.row.scheme==N);
  if(local.origin.kind!=IR8_PACKET_ORIGIN_KIND_GENERIC)
   G(c,6,ORIGIN,EQUATION,17,aid,4,v.row.use_env==eid);
  else{Ir8PacketEnv e;rt8_private_table(c,4,v.row.use_env,&e,sizeof(e));
   G(c,1,ORIGIN,EQUATION,17,aid,4,e.scheme==v.site.scope&&(v.row.use_env==eid||e.mode==IR8_PACKET_ENV_MODE_CLOSED));}
 }else{
  Ir8PacketScheme scheme;Ir8PacketIntro intro;
  rt8_private_table(c,3,v.row.scheme,&scheme,sizeof(scheme));rt8_private_table(c,18,scheme.intro,&intro,sizeof(intro));
  G(c,21,TYPE,EQUATION,17,aid,6,local.origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&v.row.use_env==N&&v.site.context_tag==IR8_PACKET_SITE_CONTEXT_INTRODUCTION&&v.site.context_intro==intro.id&&intro.scheme==scheme.id&&v.row.type==scheme.body&&v.site.principal_type==scheme.body);
  int found=0;
  for(uint32_t i=0;i<intro.result_sites.count;++i){Ir8PacketSiteRef r;rt8_private_charge(c,3);
   rt8_private_vector(c,intro.result_sites.object,IR8_PACKET_ELEMENT_SITE_REF,i,&r,sizeof(r));if(r.row==sid)found=1;}
  G(c,21,ORIGIN,EQUATION,18,intro.id,6,found);
 }
 rt8_private_charge(c,sizeof(v.node)+sizeof(v.access));v.node=n;v.access=access;
 rt8_private_node_state(c,n,&v);rt8_private_charge(c,sizeof(v));*out=v;
}
static void anchor_check(Rt8Context *c,Rt8Handle *h) {
 rt8_private_charge(c,5);
 if(h->anchor){Rt8Handle *a=rt8_private_live(c,h->anchor);
  G(c,7,OWNERSHIP,ANCHOR,N,N,N,a!=h&&a->anchor==NULL&&a->loans!=0&&h->loans==0&&
   (a->role==RT8_RC_OWNER||a->role==RT8_RC_PIN));}
}
void rt8_private_value(Rt8Context *c,Rt8Handle *handle,uint32_t flags,Rt8ValueFacts *out) {
 Rt8Handle *h=rt8_private_live(c,handle);
 G(c,17,OWNERSHIP,OWNER,N,N,N,(flags&~UINT32_C(15))==0&&h->role==RT8_RC_OWNER&&!h->home&&h->node&&h->access);
 anchor_check(c,h);
 /* Ordinary term loans require an original value OWNER anchor. The PIN
  * exception belongs only to the exact activation-home KEY path below.
  * A field or Scheme loan need not share its anchor's Node/group/Access. */
 G(c,7,OWNERSHIP,ANCHOR,N,N,N,!h->anchor||
  (h->anchor->role==RT8_RC_OWNER&&!h->anchor->home&&h->anchor->node&&
   h->anchor->access&&h->anchor->fill_ticket<=1));
 if(flags&RT8_VALUE_OWN)G(c,17,OWNERSHIP,OWNER,N,N,N,h->anchor==NULL);
 if(flags&RT8_VALUE_TICKET_FREE)G(c,18,OWNERSHIP,TICKET,N,N,N,h->fill_ticket==0);
 if(flags&RT8_VALUE_NO_LOANS)G(c,19,OWNERSHIP,DEPENDENT_LOAN,N,N,N,h->loans==0);
 G(c,17,OWNERSHIP,EQUATION,N,N,N,h->fill_ticket<=1&&(!h->anchor||h->fill_ticket==0));
 rt8_private_node_access(c,h->node,h->access,(flags&RT8_VALUE_MONO)!=0,out);
 G(c,9,OWNERSHIP,EQUATION,14,out->site.id,N,h->group==out->node->group);
}
void rt8_private_authority(Rt8Context *c,Rt8Handle *handle) {
 Rt8Handle *h=rt8_private_live(c,handle);
 if(h->anchor){
  anchor_check(c,h);
  G(c,7,OWNERSHIP,ANCHOR,N,N,N,h->home&&h->role==RT8_RC_KEY&&c->frame&&c->frame->home==h&&h->access==NULL&&h->fill_ticket==0&&h->anchor->role==RT8_RC_PIN&&h->group==h->anchor->group);
 }else{
  G(c,17,OWNERSHIP,OWNER,N,N,N,!h->home&&(h->role==RT8_RC_OWNER||h->role==RT8_RC_BUILDER));
  if(h->role==RT8_RC_OWNER){Rt8ValueFacts v;rt8_private_value(c,h,RT8_VALUE_OWN,&v);}
  else G(c,17,OWNERSHIP,EQUATION,N,N,N,h->node==NULL&&h->access==NULL&&h->fill_ticket==0);
 }
 rt8_private_guard_seen(c,9);
}
void rt8_private_publish_check(Rt8Context *c,const Rt8Origin *host,uint32_t expected,
 const Rt8ValueFacts *target) {
 uint32_t eid=rt8_private_table_auth(c,4,host->env);Ir8PacketEnv env;
 rt8_private_table(c,4,eid,&env,sizeof(env));
 G(c,12,TYPE,APPLICABILITY,17,target->row.id,3,target->row.mode==IR8_PACKET_ACCESS_MODE_MONO);
 G(c,3,TYPE,EQUATION,17,target->row.id,5,target->row.type==expected);
 if(host->kind==IR8_PACKET_ORIGIN_KIND_GENERIC){
  G(c,4,TYPE,EQUATION,17,target->row.id,4,target->row.use_env==target->row.origin_env&&target->row.type==target->execution.principal_type);
  G(c,5,ORIGIN,EQUATION,17,target->row.id,2,env.mode==IR8_PACKET_ENV_MODE_NEUTRAL&&target->node->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&target->row.origin_env==eid&&target->node->origin.capsule_id==host->capsule_id&&host->capsule_id!=0);
 }else{
  G(c,6,ORIGIN,EQUATION,17,target->row.id,4,
   (host->kind==IR8_PACKET_ORIGIN_KIND_CONCRETE&&eid==0&&env.mode==IR8_PACKET_ENV_MODE_CONCRETE&&host->capsule_id==0&&host->creation_activation==0)||
   (host->kind==IR8_PACKET_ORIGIN_KIND_INSTANCE&&env.mode==IR8_PACKET_ENV_MODE_CLOSED&&host->capsule_id!=0&&host->capsule_id<=c->next_capsule&&host->creation_activation!=0&&host->creation_activation<=c->next_frame));
  G(c,3,TYPE,EQUATION,17,target->row.id,5,rt8_private_type_closed(c,expected));
 }
 rt8_private_guard_seen(c,9);
}
static int capture_atom_equal(Rt8Context *c,const char *actual,const char *fixed) {
 for(size_t i=0;;++i){rt8_private_charge(c,4);
  unsigned a=(unsigned char)actual[i],b=(unsigned char)fixed[i];
  if(a!=b)return 0;
  if(!a)return 1;}
}
/* A registered capture may retain a concrete intrinsic scalar without changing
 * its principal Access. This is a native safety rule, not a source-import
 * whitelist: exact source owners and Down proofs remain checked-Code authority.
 * In particular, SCALAR describes the representation, not the node's readiness.
 * All other edges, and generic-owned scalar captures, keep the old rule. */
void rt8_private_capture_publish(Rt8Context *c,const Rt8Origin *host,
 const Rt8SlotFacts *slot,const Rt8ValueFacts *target) {
 if(host->kind!=IR8_PACKET_ORIGIN_KIND_GENERIC||
    target->node->origin.kind!=IR8_PACKET_ORIGIN_KIND_CONCRETE){
  rt8_private_publish_check(c,host,slot->resolved_type,target);return;
 }
 Ir8PacketEnv env;Ir8PacketType type;Ir8PacketShapeBinding shape;
 Ir8PacketShapeTyping typing;Ir8PacketRepresentation rep;
 uint32_t eid=rt8_private_table_auth(c,4,host->env);
 rt8_private_table(c,4,eid,&env,sizeof(env));
 G(c,10,ORIGIN,EQUATION,16,slot->row.id,2,slot->row.role_tag==IR8_PACKET_SLOT_ROLE_CAPTURE);
 G(c,5,ORIGIN,EQUATION,4,eid,1,env.mode==IR8_PACKET_ENV_MODE_NEUTRAL&&env.scheme!=N&&
  host->capsule_id!=0&&host->capsule_id<=c->next_capsule&&host->creation_activation==0);
 G(c,12,TYPE,APPLICABILITY,17,target->row.id,3,target->row.mode==IR8_PACKET_ACCESS_MODE_MONO);
 G(c,6,ORIGIN,EQUATION,17,target->row.id,2,target->row.origin_env==0&&target->row.use_env==0&&
  target->row.scheme==N&&target->site.scope==N&&target->node->origin.capsule_id==0&&
  target->node->origin.creation_activation==0);
 G(c,3,TYPE,EQUATION,16,slot->row.id,6,slot->row.type==slot->resolved_type&&
  target->row.type==slot->resolved_type&&target->execution.principal_type==slot->resolved_type);
 rt8_private_table(c,1,slot->resolved_type,&type,sizeof(type));
 G(c,3,TYPE,EQUATION,1,type.id,1,type.tag==IR8_PACKET_TYPE_TAG_CLOSED&&type.scheme==N&&
  type.index==N&&type.argument==N&&type.result==N&&type.protocol==N&&type.result_identity==N);
 const char *atom=rt8_private_string(c,type.atom);
 int is_bool=capture_atom_equal(c,atom,"#bool"),is_i64=capture_atom_equal(c,atom,"#i64");
 G(c,3,TYPE,EQUATION,1,type.id,2,is_bool||is_i64);
 rt8_private_table(c,9,target->execution.representation,&rep,sizeof(rep));
 rt8_private_table(c,7,rep.shape,&shape,sizeof(shape));
 rt8_private_table(c,8,rep.typing,&typing,sizeof(typing));
 G(c,2,TYPE,EQUATION,7,shape.id,1,shape.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&
  shape.source_reference==type.atom&&shape.source_type==N&&shape.source_scheme==N&&
  shape.kind==(is_bool?IR8_PACKET_SHAPE_KIND_BOOL:IR8_PACKET_SHAPE_KIND_I64)&&
  shape.argument_rep==N&&shape.result_rep==N);
 G(c,2,TYPE,EQUATION,8,typing.id,2,typing.shape==shape.id&&typing.type==type.id&&
  typing.scope==N&&typing.contract==N&&rep.shape==shape.id&&rep.ready_kind==IR8_PACKET_READY_KIND_SCALAR);
 G(c,2,STATE,EQUATION,14,target->site.id,7,target->shape.shape==shape.id&&
  target->shape.typing==typing.id&&target->shape.representation==rep.id&&target->shape.kind==shape.kind&&
  target->shape.argument_rep==N&&target->shape.result_rep==N&&target->shape.fields_object==N&&
  target->shape.field_first==0&&target->shape.field_count==0);
 rt8_private_guard_seen(c,9);
}
void rt8_private_slot_spec(Rt8Context *c,const Rt8Site *site,const Rt8Env *env,
 uint32_t role,size_t index,Rt8SlotFacts *out) {
 uint32_t sid=rt8_private_table_auth(c,14,site);Ir8PacketSite host;
 rt8_private_table(c,14,sid,&host,sizeof(host));(void)rt8_private_table_auth(c,4,env);
 G(c,0,REFERENCE,COUNT,14,sid,0,index<=UINT32_MAX);
 uint32_t name=N;
 if(role==IR8_PACKET_SLOT_ROLE_CAPTURE){Ir8PacketCodeTyping code;Ir8PacketCaptureTyping capture;
  rt8_private_table(c,5,host.code,&code,sizeof(code));
  G(c,10,ORIGIN,COUNT,5,code.id,7,index<code.captures.count&&code.captures.count<=RT8_MAX_CAPTURES);
  rt8_private_vector(c,code.captures.object,IR8_PACKET_ELEMENT_CAPTURE_TYPING,(uint32_t)index,&capture,sizeof(capture));name=capture.name;
 }else if(role==IR8_PACKET_SLOT_ROLE_FUNCTION||role==IR8_PACKET_SLOT_ROLE_ARGUMENT||role==IR8_PACKET_SLOT_ROLE_MEMO)
  G(c,26,STATE,COUNT,14,sid,5,index==0);
 else G(c,0,REFERENCE,APPLICABILITY,14,sid,5,role==IR8_PACKET_SLOT_ROLE_FIELD||role==IR8_PACKET_SLOT_ROLE_VARIANT_FIELD);
 for(uint32_t i=0,n=table_count(c,16);i<n;++i){Rt8SlotFacts f;int match=0;rt8_private_charge(c,8);
  rt8_private_table(c,16,i,&f.row,sizeof(f.row));if(f.row.site!=sid||f.row.role_tag!=role)continue;
  if(role==IR8_PACKET_SLOT_ROLE_CAPTURE)match=f.row.role_name==name;
  else if(role==IR8_PACKET_SLOT_ROLE_FIELD||role==IR8_PACKET_SLOT_ROLE_VARIANT_FIELD){Ir8PacketNominalField field;
   rt8_private_table(c,10,f.row.role_field,&field,sizeof(field));rt8_private_charge(c,4);
   match=field.position==(uint32_t)index&&(role==IR8_PACKET_SLOT_ROLE_FIELD?field.variant==N:field.variant==host.sum_variant);
   if(match)name=field.name;
  }else match=1;
  if(!match)continue;
  f.resolved_type=rt8_private_resolve(c,f.row.type,env);
  if(role==IR8_PACKET_SLOT_ROLE_MEMO)f.name="$target";
  else if(role==IR8_PACKET_SLOT_ROLE_FUNCTION)f.name="$function";
  else if(role==IR8_PACKET_SLOT_ROLE_ARGUMENT)f.name="$argument";
  else f.name=rt8_private_string(c,name);
  rt8_private_charge(c,sizeof(f));*out=f;return;
 }
 rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_MISSING,0,14,sid,5);
}
static void principal_facts(Rt8Context *c,Rt8Node *host,Rt8ValueFacts *out) {
 Rt8Node n;size_t bytes=rt8_private_extent(c,host,RT8_MC_NODE);
 G(c,2,STATE,LENGTH,N,N,N,bytes>=sizeof(n));rt8_private_charge(c,sizeof(n));memcpy(&n,host,sizeof(n));
 uint32_t sid=rt8_private_table_auth(c,14,n.origin_site),eid=rt8_private_table_auth(c,4,n.origin.env);
 const Rt8Access *access=rt8_private_access(c,sid,eid,IR8_PACKET_ACCESS_MODE_MONO,eid,N);
 rt8_private_node_access(c,host,access,1,out);
}
void rt8_private_slot_check(Rt8Context *c,Rt8Node *host,uint32_t role,size_t index,
 const Rt8Slot *slot,Rt8ValueFacts *value,Rt8SlotFacts *spec) {
 Rt8ValueFacts h;Rt8Slot actual;size_t position=index;
 principal_facts(c,host,&h);
 if(role==IR8_PACKET_SLOT_ROLE_FUNCTION)position=0;
 else if(role==IR8_PACKET_SLOT_ROLE_ARGUMENT)position=1;
 else if(role==IR8_PACKET_SLOT_ROLE_MEMO)position=0;
 G(c,25,STATE,COUNT,14,h.site.id,5,position<host->used&&position<host->capacity);
 G(c,0,REFERENCE,UNREGISTERED,14,h.site.id,5,slot==&host->slots[position]);
 rt8_private_slot_spec(c,host->origin_site,host->origin.env,role,index,spec);
 rt8_private_charge(c,sizeof(actual));memcpy(&actual,slot,sizeof(actual));
 G(c,25,STATE,EQUATION,16,spec->row.id,2,actual.name==spec->name&&actual.target!=NULL&&actual.access!=NULL);
 rt8_private_node_access(c,actual.target,actual.access,1,value);
 if(role==IR8_PACKET_SLOT_ROLE_CAPTURE)rt8_private_capture_publish(c,&host->origin,spec,value);
 else rt8_private_publish_check(c,&host->origin,spec->resolved_type,value);
 if(spec->row.relation==IR8_PACKET_RELATION_SAME)
  G(c,9,OWNERSHIP,EQUATION,16,spec->row.id,7,host->group==value->node->group);
 /* DOWN/BELOW proof remains checked-source authority; distinct group IDs alone
  * are never treated as a proof of strict ordering. */
 rt8_private_guard_seen(c,9);
}
const Rt8Access *rt8_private_transport(Rt8Context *c,Rt8Node *host,uint32_t expected,
 const Rt8Access *request,Rt8Node *target,const Rt8Access *actual) {
 Rt8ValueFacts h,v;rt8_private_node_access(c,host,request,1,&h);
 rt8_private_node_access(c,target,actual,1,&v);
 /* Exact principal equation and neutral capsule precede a closed projection. */
 rt8_private_publish_check(c,&host->origin,expected,&v);
 uint32_t projection=N;
 if(host->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC){
  rt8_private_charge(c,2);
  if(h.row.use_env!=h.row.origin_env){Ir8PacketEnv env;rt8_private_table(c,4,h.row.use_env,&env,sizeof(env));
   G(c,15,TYPE,EQUATION,4,env.id,1,env.mode==IR8_PACKET_ENV_MODE_CLOSED&&env.scheme==h.site.scope);
   projection=env.id;}
 }
 for(uint32_t i=0,n=table_count(c,20);i<n;++i){Ir8PacketTransport t;rt8_private_charge(c,3);
  rt8_private_table(c,20,i,&t,sizeof(t));
  if(t.source_access!=v.row.id||t.projection_env!=projection)continue;
  if(projection==N){G(c,6,ORIGIN,EQUATION,20,i,3,t.kind==IR8_PACKET_TRANSPORT_KIND_IDENTITY&&t.result_access==v.row.id);return actual;}
  G(c,4,TYPE,EQUATION,20,i,3,t.kind==IR8_PACKET_TRANSPORT_KIND_PROJECT);
  const Rt8Access *result=rt8_private_table_ref(c,17,t.result_access);Ir8PacketAccess a;
  rt8_private_table(c,17,t.result_access,&a,sizeof(a));
  const Rt8Env *env=rt8_private_table_ref(c,4,projection);uint32_t type=rt8_private_resolve(c,expected,env);
  G(c,4,TYPE,EQUATION,17,a.id,4,a.site==v.row.site&&a.origin_env==v.row.origin_env&&a.mode==IR8_PACKET_ACCESS_MODE_MONO&&a.use_env==projection&&a.type==type&&a.scheme==N);
  return result;
 }
 rt8_private_guard_fault(c,RT8_STATUS_ORIGIN,RT8_DETAIL_MISSING,4,17,v.row.id,4);
}
/* Only capture_plan's already observed concrete-target branch enters here.
 * Reauthenticate the actual registered slot and closed host request before
 * selecting its existing null-projection identity row. No Access is rewritten. */
const Rt8Access *rt8_private_capture_transport(Rt8Context *c,Rt8Node *host,
 const Rt8Access *request,size_t index) {
 Rt8ValueFacts h,v;Rt8SlotFacts slot;Ir8PacketEnv env;
 rt8_private_node_access(c,host,request,1,&h);
 G(c,10,ORIGIN,COUNT,14,h.site.id,5,index<host->used&&index<host->capacity);
 rt8_private_slot_check(c,host,IR8_PACKET_SLOT_ROLE_CAPTURE,index,&host->slots[index],&v,&slot);
 G(c,6,ORIGIN,EQUATION,17,v.row.id,2,host->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&
  v.node->origin.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE);
 rt8_private_table(c,4,h.row.use_env,&env,sizeof(env));
 G(c,15,TYPE,EQUATION,4,env.id,1,h.row.use_env!=h.row.origin_env&&
  env.mode==IR8_PACKET_ENV_MODE_CLOSED&&env.scheme==h.site.scope);
 uint32_t resolved=rt8_private_resolve(c,slot.row.type,rt8_private_table_ref(c,4,env.id));
 G(c,3,TYPE,EQUATION,16,slot.row.id,6,resolved==v.row.type&&resolved==slot.resolved_type);
 for(uint32_t i=0,n=table_count(c,20);i<n;++i){Ir8PacketTransport t;rt8_private_charge(c,3);
  rt8_private_table(c,20,i,&t,sizeof(t));
  if(t.source_access!=v.row.id||t.projection_env!=N)continue;
  G(c,6,ORIGIN,EQUATION,20,i,3,t.kind==IR8_PACKET_TRANSPORT_KIND_IDENTITY&&t.result_access==v.row.id);
  return v.access;
 }
 rt8_private_guard_fault(c,RT8_STATUS_ORIGIN,RT8_DETAIL_MISSING,6,17,v.row.id,4);
}
void rt8_private_result_check(Rt8Context *c,const Rt8Frame *f,const Rt8ValueFacts *v) {
 G(c,23,OWNERSHIP,EQUATION,N,N,N,f&&c->frame==f&&f->kind!=RT8_FRAME_ENTRY&&!f->returned&&f->home&&!f->active_intro);
 Ir8PacketCodeTyping code;Ir8PacketCodeExecution execution;
 const Ir8PacketCodeExecution *ref=rt8_private_code_execution(c,f->code,f->execution.env,&code,&execution);
 G(c,10,ORIGIN,EQUATION,5,code.id,1,ref==f->code_execution&&execution.result==f->expected_result_type&&
  ((f->kind==RT8_FRAME_FUNCTION&&code.kind==IR8_PACKET_CODE_KIND_FUNCTION)||(f->kind==RT8_FRAME_THUNK&&code.kind==IR8_PACKET_CODE_KIND_THUNK)));
 rt8_private_publish_check(c,&f->execution,f->expected_result_type,v);
 if(f->kind==RT8_FRAME_FUNCTION){uint32_t identity=code.expected_identity_flag?IR8_PACKET_RESULT_IDENTITY_ARGUMENT:IR8_PACKET_RESULT_IDENTITY_UNKNOWN;
  G(c,11,TYPE,EQUATION,5,code.id,10,f->result_identity==identity);
  if(identity==IR8_PACKET_RESULT_IDENTITY_ARGUMENT)
   G(c,11,TYPE,EQUATION,5,code.id,10,v->node->id==f->argument_node_id&&v->node->group==f->argument_group);
 }
}

const Rt8Site *rt8_site(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_table_ref(c,14,id);}
const Rt8Intro *rt8_intro(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_table_ref(c,18,id);}
const Rt8Instantiation *rt8_instantiation(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_table_ref(c,19,id);}
const Rt8Env *rt8_env(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_table_ref(c,4,id);}
const Rt8Shape *rt8_shape(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_descriptor_ref(c,1,id);}
const Rt8Family *rt8_family(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_descriptor_ref(c,3,id);}
const Rt8Variant *rt8_variant(Rt8Context *c,uint32_t id){rt8_private_enter(c,RT8_OP_ACCESSOR,0);return rt8_private_descriptor_ref(c,4,id);}
const Rt8Code *rt8_code(Rt8Context *c,uint32_t id) {
 rt8_private_enter(c,RT8_OP_ACCESSOR,0);
 const Rt8Code *out=NULL;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};rt8_private_guard_seen(c,0);rt8_private_guard_seen(c,10);
 reader_done(c,rt8_view_code_ref(&c->program,id,&out,&s),&d);return out;
}
const char *rt8_label(Rt8Context *c,uint32_t id) {
 rt8_private_enter(c,RT8_OP_ACCESSOR,0);
 const char *out=NULL;Rt8Diagnostic d=diagnostic();Rt8ReadState s={&c->guard_work,&d};rt8_private_guard_seen(c,0);
 reader_done(c,rt8_view_label(&c->program,id,&out,&s),&d);return out;
}
const Rt8Shape *rt8_site_shape(Rt8Context *c,const Rt8Site *site) {
 rt8_private_enter(c,RT8_OP_ACCESSOR,0);Ir8PacketSite row;Rt8SiteFacts facts;const Rt8Code *code=NULL;
 uint32_t id=rt8_private_table_auth(c,14,site);rt8_private_table(c,14,id,&row,sizeof(row));
 if(row.code!=N){Rt8Diagnostic d=diagnostic();Rt8ReadState state={&c->guard_work,&d};reader_done(c,rt8_view_code_ref(&c->program,row.code,&code,&state),&d);}
 rt8_private_site_facts(c,site,row.category,code,NULL,&facts);return facts.shape_ref;
}
