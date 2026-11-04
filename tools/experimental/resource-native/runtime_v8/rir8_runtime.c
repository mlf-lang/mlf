/* Stage05B value helpers. Source preparation only, not an execution receipt.
 * Metadata is consulted only during preflight. Prepared publication uses actual
 * capabilities and immutable authenticated spans, never desired-type retyping. */
#include "rir8_runtime_internal.h"
#include <inttypes.h>
#include <string.h>
#define N RT8_NULL
#define G(c,n,s,d,t,r,f,p) do { rt8_private_charge((c),16); \
 rt8_private_guard_seen((c),(n)); if(!(p)) \
 rt8_private_guard_fault((c),RT8_STATUS_##s,RT8_DETAIL_##d,(n),(t),(r),(f)); } while(0)
#define MONO_OWN (RT8_VALUE_OWN|RT8_VALUE_MONO)
#define MOVE_VALUE (MONO_OWN|RT8_VALUE_TICKET_FREE|RT8_VALUE_NO_LOANS)

typedef struct Trace { const char *layout,*code; uint32_t shape,type,scheme; } Trace;
typedef struct FieldSpan { const unsigned char *first; const unsigned char *pool; size_t count; } FieldSpan;

static void reserve_rows(Rt8Context *c,size_t count,uint64_t unit) {
 G(c,0,OVERFLOW,OVERFLOW,N,N,N,unit!=0&&count<=UINT64_MAX/unit);
 rt8_private_charge(c,(uint64_t)count*unit);
}
static const char *state_name(uint32_t state) {
 switch(state){case RT8_NS_READY:return "READY";case RT8_NS_HOLE:return "HOLE";
 case RT8_NS_INDIRECT:return "INDIRECT";case RT8_NS_THUNK:return "THUNK";
 case RT8_NS_CLOSURE:return "CLOSURE";case RT8_NS_APPLICATION:return "APPLICATION";
 case RT8_NS_BUSY:return "BUSY";case RT8_NS_MEMO:return "MEMO";default:return NULL;}
}
/* Only prevalidated text reaches these operational trace writers. */
static void quoted(FILE *out,const char *s) {
 if(!s){fputs("null",out);return;} fputc('"',out);
 for(const unsigned char *p=(const unsigned char *)s;*p;++p){unsigned x=*p;
  if(x=='"'||x=='\\'){fputc('\\',out);fputc((int)x,out);}
  else if(x<32)fprintf(out,"\\u%04x",x);else fputc((int)x,out);}
 fputc('"',out);
}
static void trace_shape(Rt8Context *c,const Ir8PacketShapeSpec *shape,Trace *out) {
 Ir8PacketShapeBinding binding;rt8_private_table(c,7,shape->shape,&binding,sizeof(binding));
 rt8_private_charge(c,sizeof(*out));out->layout=NULL;out->code=NULL;
 out->shape=binding.id;out->type=binding.source_type;out->scheme=binding.source_scheme;
 if(binding.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY)
  out->layout=rt8_private_string(c,binding.source_reference);
}
static void trace_code(Rt8Context *c,uint32_t id,Trace *out) {
 rt8_private_charge(c,16);if(id!=N){Ir8PacketCodeTyping code;rt8_private_table(c,5,id,&code,sizeof(code));out->code=rt8_private_string(c,code.name);}
}
static void typed_trace(Rt8Context *c,const Trace *t) {
 rt8_private_str(c,"layout",t->layout);rt8_private_num(c,"shape_id",t->shape);
 if(t->type!=N)rt8_private_num(c,"type_id",t->type);
 if(t->scheme!=N)rt8_private_num(c,"scheme_id",t->scheme);
}
static void slots_trace(Rt8Context *c,Rt8Node *n,const char *key) {
 fputc(',',c->output);quoted(c->output,key);fputs(":{",c->output);
 for(size_t i=0;i<n->used;++i){if(i)fputc(',',c->output);quoted(c->output,n->slots[i].name);fprintf(c->output,":%"PRIu64,n->slots[i].target->id);}
 fputc('}',c->output);
}
static void relation(Rt8Context *c,Rt8Group *host,const Rt8SlotFacts *slot,const Rt8ValueFacts *v) {
 if(slot->row.relation==IR8_PACKET_RELATION_SAME)
  G(c,9,OWNERSHIP,EQUATION,16,slot->row.id,7,host==v->node->group);
 rt8_private_guard_seen(c,8);rt8_private_guard_seen(c,9);
}
static void operand(Rt8Context *c,Rt8Group *group,const Rt8SiteFacts *site,
 uint32_t role,size_t index,Rt8Handle *value,int loans,Rt8SlotFacts *slot) {
 Rt8ValueFacts v;rt8_private_value(c,value,RT8_VALUE_MONO|(loans?0:RT8_VALUE_OWN),&v);
 rt8_private_slot_spec(c,site->site_ref,site->origin.env,role,index,slot);
 rt8_private_publish_check(c,&site->origin,slot->resolved_type,&v);relation(c,group,slot,&v);
}
/* Each descriptor identity, pool string boundary, Slot equation and capability
 * is authenticated in this first pass. No retained per-field heap/stack cache.
 * A final conservative reservation covers every later row/Handle/Node read,
 * pointer arithmetic, loop predicate and Slot write in the prepared suffix. */
static FieldSpan field_span(Rt8Context *c,Rt8Group *group,const Rt8SiteFacts *site,
 uint32_t domain,uint32_t object,uint32_t first,size_t count,uint32_t role,
 Rt8Handle *const *values,uint32_t owner_kind,uint32_t owner) {
 FieldSpan span;Ir8PacketSpan registry;
 rt8_private_charge(c,sizeof(span)*2+sizeof(registry));
 span.first=NULL;span.pool=NULL;span.count=count;registry=c->program.typed_header.descriptor[domain-1];
 G(c,0,REFERENCE,COUNT,14,site->site.id,5,count<=RT8_MAX_DATA_FIELDS&&((count!=0)==(values!=NULL)));
 if(count==0){G(c,0,REFERENCE,EQUATION,14,site->site.id,5,object==N&&first==0);return span;}
 G(c,0,REFERENCE,COUNT,14,site->site.id,5,object==registry.object&&first<=registry.count&&count<=registry.count-first&&count<=SIZE_MAX/sizeof(Ir8PacketFieldSpec));
 for(size_t i=0;i<count;++i){Ir8PacketFieldSpec field;Rt8SlotFacts slot;
  reserve_rows(c,1,32);rt8_private_descriptor(c,domain,first+(uint32_t)i,&field,sizeof(field));
  const Ir8PacketFieldSpec *ref=rt8_private_descriptor_ref(c,domain,first+(uint32_t)i);
  const char *name=rt8_private_string(c,field.name);
  if(i==0)span.first=(const unsigned char *)ref;
  G(c,0,REFERENCE,EQUATION,14,site->site.id,5,(const unsigned char *)ref==span.first+i*sizeof(Ir8PacketFieldSpec)&&field.owner_kind==owner_kind&&field.owner==owner&&field.position==i);
  operand(c,group,site,role,i,values[i],0,&slot);
  G(c,3,TYPE,EQUATION,16,slot.row.id,6,field.type==slot.row.type&&(domain==6?field.relation==slot.row.relation:field.relation==N)&&name==slot.name);
 }
 /* ProgramView pool is admitted, with uintptr arithmetic checked by binding;
  * every offset actually used above was independently string-authenticated. */
 span.pool=(const unsigned char *)c->program.program.packet+c->program.string_pool.offset;
 reserve_rows(c,count,UINT64_C(256)+2*sizeof(Ir8PacketFieldSpec)+sizeof(Rt8Handle)+sizeof(Rt8Slot));
 return span;
}
static Rt8Handle *expose(Rt8Context *c,Rt8Node *n,const Rt8SiteFacts *site,
 const Trace *trace,const char *out,const char *opcode) {
 rt8_private_bump(c,&c->report.nodes_allocated);rt8_private_bump(c,&c->live_nodes);
 rt8_private_peak(&c->report.peak_nodes,c->live_nodes);
 Rt8Handle *result=rt8_private_local(c,rt8_private_acquire(c,n,site->principal_access));
 if(rt8_private_event(c,"allocate")){rt8_private_num(c,"node",n->id);rt8_private_num(c,"group",n->group->id);
  rt8_private_str(c,"state",state_name(n->state));rt8_private_str(c,"code",trace->code);typed_trace(c,trace);
  rt8_private_str(c,"out",out);rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"opcode",opcode);
  rt8_private_num(c,"site_id",site->site.id);rt8_private_num(c,"env_id",site->execution.env);
  slots_trace(c,n,"slots");rt8_private_end_event(c);}
 return result;
}
static Rt8Handle *publish_span(Rt8Context *c,Rt8Handle *authority,const Rt8SiteFacts *site,
 uint32_t state,const Rt8Code *code,const FieldSpan *fields,Rt8Handle *const *values,
 const Trace *trace,const char *out,const char *opcode) {
 size_t capacity=fields->count;if(state==RT8_NS_THUNK&&capacity==0)capacity=1;
 Rt8Node *n=rt8_private_new_node(c,authority->group,site,state,code,capacity);
 for(size_t i=0;i<fields->count;++i){Ir8PacketFieldSpec field;
  memcpy(&field,fields->first+i*sizeof(field),sizeof(field));
  rt8_private_publish_prepared(c,n,(const char *)fields->pool+field.name,values[i]->node,values[i]->access);
 }
 return expose(c,n,site,trace,out,opcode);
}
static void imports_check(Rt8Context *c,size_t count,Rt8Handle *const *imports) {
 G(c,0,REFERENCE,COUNT,N,N,N,count<=RT8_MAX_IMPORTS&&((count!=0)==(imports!=NULL)));
 reserve_rows(c,count,16);for(size_t i=0;i<count;++i)rt8_private_authority(c,imports[i]);
}
Rt8Handle *rt8_new_root(Rt8Context *c,size_t count,Rt8Handle *const *imports) {
 rt8_private_enter(c,RT8_OP_NEW_ROOT,1);imports_check(c,count,imports);return rt8_private_new_group(c);
}
Rt8Handle *rt8_new_below(Rt8Context *c,Rt8Handle *ceiling,size_t count,Rt8Handle *const *imports) {
 rt8_private_enter(c,RT8_OP_NEW_BELOW,1);rt8_private_authority(c,ceiling);imports_check(c,count,imports);return rt8_private_new_group(c);
}
Rt8Handle *rt8_alloc(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Shape *shape,Rt8Handle *const *values,const char *out) {
 Rt8SiteFacts s;Trace t;rt8_private_enter(c,RT8_OP_ALLOC,1);rt8_private_label(c,out);rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_DATA,NULL,shape,&s);
 G(c,25,STATE,STATE,14,s.site.id,5,s.shape.kind==IR8_PACKET_SHAPE_KIND_DATA);
 trace_shape(c,&s.shape,&t);
 FieldSpan fields=field_span(c,a->group,&s,5,s.shape.fields_object,s.shape.field_first,s.shape.field_count,
  IR8_PACKET_SLOT_ROLE_FIELD,values,IR8_PACKET_FIELD_OWNER_DATA,s.shape.shape);
 return publish_span(c,a,&s,RT8_NS_READY,NULL,&fields,values,&t,out,"alloc");
}
static Rt8Handle *callable(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Code *code,
 Rt8Handle *const *values,const char *out,int thunk) {
 Rt8SiteFacts s;Trace t;Ir8PacketCodeSpec spec;rt8_private_label(c,out);rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,thunk?IR8_PACKET_SITE_CATEGORY_THUNK:IR8_PACKET_SITE_CATEGORY_CLOSURE,code,NULL,&s);
 rt8_private_descriptor(c,2,s.site.code,&spec,sizeof(spec));
 Ir8PacketCodeTyping typing;Ir8PacketCodeExecution execution;
 (void)rt8_private_code_execution(c,code,s.origin.env,&typing,&execution);
 G(c,10,ORIGIN,COUNT,5,s.site.code,7,spec.code==s.site.code&&spec.capture_count<=RT8_MAX_CAPTURES&&spec.capture_count==typing.captures.count&&spec.capture_count==execution.captures.count);
 if(thunk){G(c,3,TYPE,EQUATION,6,execution.id,4,execution.result==s.execution.principal_type);}
 else{Ir8PacketType arrow;rt8_private_table(c,1,execution.callable_type,&arrow,sizeof(arrow));
  G(c,10,TYPE,EQUATION,5,typing.id,4,execution.callable_type==s.execution.principal_type&&arrow.tag==IR8_PACKET_TYPE_TAG_ARROW&&arrow.protocol==IR8_PACKET_PROTOCOL_REPEAT&&arrow.argument==execution.argument&&arrow.result==execution.result&&arrow.result_identity==(typing.expected_identity_flag?IR8_PACKET_RESULT_IDENTITY_ARGUMENT:IR8_PACKET_RESULT_IDENTITY_UNKNOWN));
  G(c,25,STATE,STATE,14,s.site.id,5,s.shape.kind==IR8_PACKET_SHAPE_KIND_REPEAT||s.shape.kind==IR8_PACKET_SHAPE_KIND_OPEN);}

 trace_shape(c,&s.shape,&t);trace_code(c,s.site.code,&t);
 FieldSpan fields=field_span(c,a->group,&s,6,spec.capture_object,spec.capture_first,spec.capture_count,
  IR8_PACKET_SLOT_ROLE_CAPTURE,values,IR8_PACKET_FIELD_OWNER_CODE,s.site.code);
 return publish_span(c,a,&s,thunk?RT8_NS_THUNK:RT8_NS_CLOSURE,code,&fields,values,&t,out,thunk?"thunk":"closure");
}
Rt8Handle *rt8_closure(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Code *code,Rt8Handle *const *v,const char *out) {
 rt8_private_enter(c,RT8_OP_CLOSURE,1);return callable(c,a,site,code,v,out,0);
}
Rt8Handle *rt8_thunk(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Code *code,Rt8Handle *const *v,const char *out) {
 rt8_private_enter(c,RT8_OP_THUNK,1);return callable(c,a,site,code,v,out,1);
}
static Rt8Handle *application(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,
 Rt8Handle *fn,Rt8Handle *arg,const char *out,int loans) {
 Rt8SiteFacts s;Rt8ValueFacts f,x;Rt8SlotFacts fs,as;Ir8PacketType arrow;Trace t;
 rt8_private_label(c,out);rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_APPLICATION,NULL,NULL,&s);
 rt8_private_value(c,fn,RT8_VALUE_MONO|(loans?0:RT8_VALUE_OWN),&f);
 rt8_private_value(c,arg,RT8_VALUE_MONO|(loans?0:RT8_VALUE_OWN),&x);
 rt8_private_table(c,1,f.row.type,&arrow,sizeof(arrow));
 G(c,26,TYPE,EQUATION,14,s.site.id,5,arrow.tag==IR8_PACKET_TYPE_TAG_ARROW&&arrow.protocol==IR8_PACKET_PROTOCOL_REPEAT&&
  arrow.argument==x.row.type&&arrow.result==s.execution.principal_type);
 operand(c,a->group,&s,IR8_PACKET_SLOT_ROLE_FUNCTION,0,fn,loans,&fs);
 operand(c,a->group,&s,IR8_PACKET_SLOT_ROLE_ARGUMENT,0,arg,loans,&as);
 trace_shape(c,&s.shape,&t);reserve_rows(c,2,256);
 if(loans)rt8_private_bump(c,&c->report.ir_application_borrow_ops);
 rt8_private_bump(c,&c->report.applications_allocated);
 Rt8Node *n=rt8_private_new_node(c,a->group,&s,RT8_NS_APPLICATION,NULL,2);
 rt8_private_publish_prepared(c,n,fs.name,f.node,f.access);rt8_private_publish_prepared(c,n,as.name,x.node,x.access);
 Rt8Handle *h=expose(c,n,&s,&t,out,loans?"application_borrow":"application");
 if(loans){if(fn->anchor)rt8_private_bump(c,&c->report.borrowed_slot_publications);
  if(arg->anchor)rt8_private_bump(c,&c->report.borrowed_slot_publications);
  if(rt8_private_event(c,"borrowed_slots_published")){rt8_private_num(c,"node",n->id);fputs(",\"anchors\":{",c->output);
   if(fn->anchor){quoted(c->output,fs.name);fprintf(c->output,":%"PRIu64,fn->anchor->id);}
   if(arg->anchor){if(fn->anchor)fputc(',',c->output);quoted(c->output,as.name);fprintf(c->output,":%"PRIu64,arg->anchor->id);}
   fputc('}',c->output);rt8_private_end_event(c);}}
 return h;
}
Rt8Handle *rt8_application(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,Rt8Handle *f,Rt8Handle *x,const char *out) {
 rt8_private_enter(c,RT8_OP_APPLICATION,1);return application(c,a,s,f,x,out,0);
}
Rt8Handle *rt8_application_borrow(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,Rt8Handle *f,Rt8Handle *x,const char *out) {
 rt8_private_enter(c,RT8_OP_APPLICATION_BORROW,1);return application(c,a,s,f,x,out,1);
}
Rt8Handle *rt8_hole(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Shape *shape,const char *out) {
 Rt8SiteFacts s;Rt8SlotFacts slot;Trace t;rt8_private_enter(c,RT8_OP_HOLE,1);rt8_private_label(c,out);rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_HOLE,NULL,shape,&s);
 rt8_private_slot_spec(c,site,s.origin.env,IR8_PACKET_SLOT_ROLE_MEMO,0,&slot);
 G(c,3,TYPE,EQUATION,16,slot.row.id,6,slot.resolved_type==s.execution.principal_type);
 trace_shape(c,&s.shape,&t);rt8_private_charge(c,256);
 Rt8Node *n=rt8_private_new_node(c,a->group,&s,RT8_NS_HOLE,NULL,1);
 Rt8Handle *h=expose(c,n,&s,&t,out,"hole");h->fill_ticket=1;return h;
}
void rt8_fill(Rt8Context *c,Rt8Handle *hole,Rt8Handle *value,const char *hv,const char *vv) {
 Rt8ValueFacts h,v;Rt8SlotFacts slot;rt8_private_enter(c,RT8_OP_FILL,1);rt8_private_label(c,hv);rt8_private_label(c,vv);
 rt8_private_value(c,hole,MONO_OWN,&h);rt8_private_value(c,value,MONO_OWN,&v);
 G(c,24,OWNERSHIP,TICKET,14,h.site.id,5,hole->fill_ticket==1&&h.node->state==RT8_NS_HOLE&&h.node->used==0&&h.node->capacity==1);
 rt8_private_slot_spec(c,h.node->origin_site,h.node->origin.env,IR8_PACKET_SLOT_ROLE_MEMO,0,&slot);
 rt8_private_publish_check(c,&h.node->origin,slot.resolved_type,&v);relation(c,h.node->group,&slot,&v);rt8_private_charge(c,256);
 rt8_private_publish_prepared(c,h.node,slot.name,v.node,v.access);h.node->state=RT8_NS_INDIRECT;hole->fill_ticket=0;
 if(rt8_private_event(c,"fill")){rt8_private_num(c,"hole",h.node->id);rt8_private_num(c,"target",v.node->id);
  rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"hole_variable",hv);rt8_private_str(c,"value_variable",vv);rt8_private_end_event(c);}
}
Rt8Handle *rt8_retain(Rt8Context *c,Rt8Handle *h) {
 Rt8ValueFacts v;rt8_private_enter(c,RT8_OP_RETAIN,1);rt8_private_value(c,h,0,&v);rt8_private_charge(c,64);
 rt8_private_bump(c,&c->report.ir_retain_ops);return rt8_private_local(c,rt8_private_acquire(c,v.node,v.access));
}
void rt8_drop(Rt8Context *c,Rt8Handle *h) {
 rt8_private_enter(c,RT8_OP_DROP,1);rt8_private_live(c,h);
 G(c,17,OWNERSHIP,OWNER,N,N,N,!h->anchor&&!h->home&&(h->role==RT8_RC_OWNER||h->role==RT8_RC_BUILDER));
 if(h->role==RT8_RC_OWNER){Rt8ValueFacts v;rt8_private_value(c,h,RT8_VALUE_OWN|RT8_VALUE_TICKET_FREE|RT8_VALUE_NO_LOANS,&v);}
 else G(c,18,OWNERSHIP,TICKET,N,N,N,!h->node&&!h->access&&!h->fill_ticket&&!h->loans);
 rt8_private_charge(c,64);rt8_private_bump(c,&c->report.ir_drop_ops);rt8_private_drop_prepared(c,h);
}
Rt8Handle *rt8_borrow(Rt8Context *c,Rt8Handle *h) {
 Rt8ValueFacts v;rt8_private_enter(c,RT8_OP_BORROW,1);rt8_private_value(c,h,RT8_VALUE_OWN,&v);rt8_private_charge(c,64);
 rt8_private_bump(c,&c->report.ir_borrow_ops);return rt8_private_local(c,rt8_private_handle(c,v.node->group,v.node,v.access,h,RT8_RC_OWNER));
}
void rt8_end_borrow(Rt8Context *c,Rt8Handle *h) {
 Rt8ValueFacts v;rt8_private_enter(c,RT8_OP_END_BORROW,1);rt8_private_value(c,h,RT8_VALUE_TICKET_FREE|RT8_VALUE_NO_LOANS,&v);
 G(c,7,OWNERSHIP,ANCHOR,N,N,N,h->anchor&&!h->home&&h->scope==c->frame->id);
 rt8_private_charge(c,64);rt8_private_bump(c,&c->report.ir_end_borrow_ops);rt8_private_drop_prepared(c,h);
}
Rt8Handle *rt8_field(Rt8Context *c,Rt8Handle *source,size_t index,const char *out,const char *sv) {
 Rt8ValueFacts h,v;Rt8SlotFacts slot;Trace t;rt8_private_enter(c,RT8_OP_FIELD,1);rt8_private_label(c,out);rt8_private_label(c,sv);
 rt8_private_value(c,source,MONO_OWN,&h);
 G(c,25,STATE,STATE,14,h.site.id,5,h.node->state==RT8_NS_READY&&h.shape.kind==IR8_PACKET_SHAPE_KIND_DATA&&index<h.node->used);
 rt8_private_slot_check(c,h.node,IR8_PACKET_SLOT_ROLE_FIELD,index,&h.node->slots[index],&v,&slot);
 trace_shape(c,&v.shape,&t);rt8_private_charge(c,256);
 Rt8Handle *loan=rt8_private_local(c,rt8_private_handle(c,v.node->group,v.node,v.access,source,RT8_RC_OWNER));
 if(rt8_private_event(c,"field_project")){rt8_private_num(c,"host",h.node->id);rt8_private_num(c,"host_group",h.node->group->id);
  rt8_private_str(c,"field",slot.name);rt8_private_num(c,"target",v.node->id);rt8_private_num(c,"target_group",v.node->group->id);
  rt8_private_str(c,"target_layout",t.layout);rt8_private_num(c,"anchor",source->id);rt8_private_num(c,"loan",loan->id);
  rt8_private_str(c,"out",out);rt8_private_str(c,"source_variable",sv);rt8_private_num(c,"frame",c->frame->id);rt8_private_end_event(c);}
 return loan;
}
static int literal_equal(Rt8Context *c,const char *actual,const char *fixed) {
 for(size_t i=0;;++i){rt8_private_charge(c,4);unsigned a=(unsigned char)actual[i],b=(unsigned char)fixed[i];if(a!=b)return 0;if(!a)return 1;}
}
static void intrinsic(Rt8Context *c,uint32_t type,uint32_t kind) {
 Ir8PacketType t;rt8_private_table(c,1,type,&t,sizeof(t));
 G(c,3,TYPE,EQUATION,1,type,1,t.tag==IR8_PACKET_TYPE_TAG_CLOSED&&(kind==IR8_PACKET_SHAPE_KIND_I64||kind==IR8_PACKET_SHAPE_KIND_BOOL));
 const char *atom=rt8_private_string(c,t.atom);
 G(c,3,TYPE,EQUATION,1,type,2,literal_equal(c,atom,kind==IR8_PACKET_SHAPE_KIND_I64?"#i64":"#bool"));
}
static int64_t ready_scalar(Rt8Context *c,Rt8Handle *h,uint32_t kind,Rt8ValueFacts *v) {
 rt8_private_value(c,h,MONO_OWN,v);intrinsic(c,v->row.type,kind);
 G(c,25,STATE,STATE,14,v->site.id,5,v->node->state==RT8_NS_READY&&v->shape.kind==kind&&v->node->storage_class==RT8_STORAGE_CLASS_SCALAR);
 rt8_private_charge(c,sizeof(int64_t));int64_t value=((Rt8ScalarNode *)v->node)->value;
 if(kind==IR8_PACKET_SHAPE_KIND_BOOL)G(c,25,STATE,EQUATION,14,v->site.id,5,value==0||value==1);
 return value;
}
static Rt8Handle *scalar_commit(Rt8Context *c,Rt8Handle *a,const Rt8SiteFacts *s,
 const Trace *t,uint32_t kind,int64_t value,const char *out,const char *op,const char *primitive) {
 Rt8Node *n=rt8_private_new_node(c,a->group,s,RT8_NS_READY,NULL,0);((Rt8ScalarNode *)n)->value=value;
 Rt8Handle *h=expose(c,n,s,t,out,op);
 if(rt8_private_event(c,"scalar_value")){rt8_private_num(c,"node",n->id);rt8_private_str(c,"kind",kind==IR8_PACKET_SHAPE_KIND_I64?"i64":"bool");
  if(kind==IR8_PACKET_SHAPE_KIND_I64)fprintf(c->output,",\"value\":%"PRId64,value);else rt8_private_bool(c,"value",value!=0);
  rt8_private_str(c,"opcode",op);rt8_private_str(c,"primitive",primitive);rt8_private_end_event(c);}
 return h;
}
static Rt8Handle *scalar(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Shape *shape,
 uint32_t kind,int64_t value,const char *out,const char *op,const char *primitive) {
 Rt8SiteFacts s;Trace t;rt8_private_label(c,out);rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_SCALAR,NULL,shape,&s);
 G(c,25,STATE,EQUATION,14,s.site.id,5,s.shape.kind==kind);
 if(kind==IR8_PACKET_SHAPE_KIND_BOOL)G(c,25,STATE,EQUATION,14,s.site.id,5,value==0||value==1);
 intrinsic(c,s.execution.principal_type,kind);trace_shape(c,&s.shape,&t);rt8_private_charge(c,256);
 return scalar_commit(c,a,&s,&t,kind,value,out,op,primitive);
}
Rt8Handle *rt8_scalar_i64(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,const Rt8Shape *shape,int64_t v,const char *out) {
 rt8_private_enter(c,RT8_OP_SCALAR,1);return scalar(c,a,s,shape,IR8_PACKET_SHAPE_KIND_I64,v,out,"scalar",NULL);
}
Rt8Handle *rt8_scalar_bool(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,const Rt8Shape *shape,int v,const char *out) {
 rt8_private_enter(c,RT8_OP_SCALAR,1);return scalar(c,a,s,shape,IR8_PACKET_SHAPE_KIND_BOOL,v,out,"scalar",NULL);
}
static int64_t integer_bits(uint64_t v){return v<=INT64_MAX?(int64_t)v:-1-(int64_t)(UINT64_MAX-v);}
Rt8Handle *rt8_prim2(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,Rt8ScalarPrimitive primitive,
 const Rt8Shape *shape,Rt8Handle *left,Rt8Handle *right,const char *out) {
 Rt8ValueFacts x,y;uint32_t kind=IR8_PACKET_SHAPE_KIND_I64;const char *name=NULL;int64_t value=0;
 rt8_private_enter(c,RT8_OP_PRIM2,1);rt8_private_label(c,out);
 switch(primitive){case RT8_PRIM_ADD_INT:name="addInt";break;case RT8_PRIM_SUB_INT:name="subInt";break;
  case RT8_PRIM_MUL_INT:name="mulInt";break;case RT8_PRIM_EQ_INT:name="eqInt";kind=IR8_PACKET_SHAPE_KIND_BOOL;break;
  case RT8_PRIM_LT_INT:name="ltInt";kind=IR8_PACKET_SHAPE_KIND_BOOL;break;
  default:rt8_private_guard_fault(c,RT8_STATUS_STATE,RT8_DETAIL_APPLICABILITY,25,N,N,N);}
 Rt8SiteFacts result_site;Trace result_trace;rt8_private_authority(c,a);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_SCALAR,NULL,shape,&result_site);
 G(c,25,STATE,EQUATION,14,result_site.site.id,5,result_site.shape.kind==kind);
 intrinsic(c,result_site.execution.principal_type,kind);trace_shape(c,&result_site.shape,&result_trace);
 int64_t lhs=ready_scalar(c,left,IR8_PACKET_SHAPE_KIND_I64,&x);
 int64_t rhs=ready_scalar(c,right,IR8_PACKET_SHAPE_KIND_I64,&y);
 rt8_private_charge(c,16);
 switch(primitive){case RT8_PRIM_ADD_INT:value=integer_bits((uint64_t)lhs+(uint64_t)rhs);break;
 case RT8_PRIM_SUB_INT:value=integer_bits((uint64_t)lhs-(uint64_t)rhs);break;
 case RT8_PRIM_MUL_INT:value=integer_bits((uint64_t)lhs*(uint64_t)rhs);break;
 case RT8_PRIM_EQ_INT:value=lhs==rhs;break;case RT8_PRIM_LT_INT:value=lhs<rhs;break;default:break;}
 rt8_private_charge(c,256);return scalar_commit(c,a,&result_site,&result_trace,kind,value,out,"prim2",name);
}
static void selectable(Rt8Context *c,Rt8Handle *h,Rt8ValueFacts *v) {
 rt8_private_value(c,h,MOVE_VALUE,v);intrinsic(c,v->row.type,IR8_PACKET_SHAPE_KIND_I64);
 G(c,25,STATE,STATE,14,v->site.id,5,v->node->state!=RT8_NS_HOLE);
}
Rt8Handle *rt8_select_i64(Rt8Context *c,Rt8Handle *a,Rt8Handle *condition,Rt8Handle *left,Rt8Handle *right,const char *out) {
 Rt8ValueFacts v,l,r;Trace t;rt8_private_enter(c,RT8_OP_SELECT,1);rt8_private_label(c,out);rt8_private_authority(c,a);
 int decision=ready_scalar(c,condition,IR8_PACKET_SHAPE_KIND_BOOL,&v)!=0;
 G(c,17,OWNERSHIP,OWNER,N,N,N,left!=right&&left!=a&&right!=a);
 selectable(c,left,&l);selectable(c,right,&r);Rt8Handle *selected=decision?left:right,*discard=decision?right:left;
 trace_shape(c,decision?&l.shape:&r.shape,&t);rt8_private_charge(c,256);Rt8Node *n=selected->node;
 if(rt8_private_event(c,"select_i64")){rt8_private_num(c,"condition_node",v.node->id);rt8_private_bool(c,"condition_value",decision);
  rt8_private_num(c,"then_node",l.node->id);rt8_private_num(c,"else_node",r.node->id);rt8_private_num(c,"result",n->id);
  rt8_private_num(c,"owner",selected->id);rt8_private_num(c,"group",n->group->id);typed_trace(c,&t);
  rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"out",out);rt8_private_end_event(c);}
 rt8_private_drop_prepared(c,discard);return selected;
}
static uint32_t family_check(Rt8Context *c,const Rt8Family *ref,Ir8PacketFamilySpec *f) {
 uint32_t id=rt8_private_descriptor_auth(c,3,ref);rt8_private_descriptor(c,3,id,f,sizeof(*f));
 G(c,0,REFERENCE,COUNT,11,id,3,f->family==id&&f->variants.count>0&&f->variants.count<=RT8_MAX_VARIANTS);return id;
}
static uint32_t variant_check(Rt8Context *c,const Ir8PacketFamilySpec *f,const Rt8Variant *ref,Ir8PacketVariantSpec *v) {
 uint32_t id=rt8_private_descriptor_auth(c,4,ref);rt8_private_descriptor(c,4,id,v,sizeof(*v));
 G(c,0,REFERENCE,EQUATION,11,f->family,3,v->family==f->family&&v->shape==f->shape&&v->index<f->variants.count&&v->field_count<=RT8_MAX_VARIANT_FIELDS);
 Ir8PacketVariantRef member;rt8_private_vector(c,f->variants.object,IR8_PACKET_ELEMENT_VARIANT_REF,v->index,&member,sizeof(member));
 G(c,0,REFERENCE,EQUATION,11,f->family,3,member.row==id);return id;
}
static const Rt8Variant *variant_at(Rt8Context *c,const Ir8PacketFamilySpec *f,uint32_t index,Ir8PacketVariantSpec *v) {
 Ir8PacketVariantRef r;rt8_private_vector(c,f->variants.object,IR8_PACKET_ELEMENT_VARIANT_REF,index,&r,sizeof(r));
 const Rt8Variant *ref=rt8_private_descriptor_ref(c,4,r.row);(void)variant_check(c,f,ref,v);return ref;
}
static const Rt8Variant *ready_sum(Rt8Context *c,Rt8Handle *h,const Ir8PacketFamilySpec *f,Rt8ValueFacts *value,Ir8PacketVariantSpec *variant) {
 rt8_private_value(c,h,MONO_OWN,value);
 G(c,25,STATE,STATE,14,value->site.id,5,value->node->state==RT8_NS_READY&&value->shape.kind==IR8_PACKET_SHAPE_KIND_SUM&&value->shape.shape==f->shape);
 rt8_private_charge(c,sizeof(const Rt8Variant *));const Rt8Variant *ref=((Rt8SumNode *)value->node)->variant;
 (void)variant_check(c,f,ref,variant);return ref;
}
static Rt8Handle *sum_construct(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Family *family,
 const Rt8Variant *variant,size_t count,Rt8Handle *const *values,const char *out,int nullary) {
 Ir8PacketFamilySpec f;Ir8PacketVariantSpec v;Rt8SiteFacts s;Trace t;rt8_private_label(c,out);rt8_private_authority(c,a);
 (void)family_check(c,family,&f);uint32_t vid=variant_check(c,&f,variant,&v);
 rt8_private_site_facts(c,site,IR8_PACKET_SITE_CATEGORY_SUM,NULL,NULL,&s);
 G(c,25,STATE,EQUATION,14,s.site.id,13,s.site.sum_family==f.family&&s.site.sum_variant==v.index&&s.shape.shape==f.shape&&s.shape.kind==IR8_PACKET_SHAPE_KIND_SUM);
 G(c,0,REFERENCE,COUNT,14,s.site.id,13,count==v.field_count&&(!nullary||count==0));
 trace_shape(c,&s.shape,&t);const char *name=rt8_private_string(c,v.name);
 FieldSpan span=field_span(c,a->group,&s,5,v.fields_object,v.field_first,count,IR8_PACKET_SLOT_ROLE_VARIANT_FIELD,values,IR8_PACKET_FIELD_OWNER_VARIANT,vid);
 for(size_t i=0;i<count;++i){Rt8ValueFacts field;rt8_private_value(c,values[i],MONO_OWN,&field);
  G(c,3,TYPE,APPLICABILITY,17,field.row.id,5,field.shape.kind==IR8_PACKET_SHAPE_KIND_I64||field.shape.kind==IR8_PACKET_SHAPE_KIND_BOOL||field.shape.kind==IR8_PACKET_SHAPE_KIND_SUM);}
 reserve_rows(c,count,256);Rt8Node *n=rt8_private_new_node(c,a->group,&s,RT8_NS_READY,NULL,count);
 ((Rt8SumNode *)n)->variant=variant;
 for(size_t i=0;i<count;++i){Ir8PacketFieldSpec field;
  memcpy(&field,span.first+i*sizeof(field),sizeof(field));
  rt8_private_publish_prepared(c,n,(const char *)span.pool+field.name,values[i]->node,values[i]->access);
 }
 Rt8Handle *h=expose(c,n,&s,&t,out,nullary?"construct_nullary":"construct_sum");
 if(rt8_private_event(c,"sum_value")){rt8_private_num(c,"node",n->id);rt8_private_str(c,"family",t.layout);rt8_private_str(c,"variant",name);rt8_private_num(c,"variant_index",v.index);rt8_private_end_event(c);}
 return h;
}
Rt8Handle *rt8_construct_nullary(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,const Rt8Family *f,const Rt8Variant *v,const char *out) {
 rt8_private_enter(c,RT8_OP_NULLARY,1);return sum_construct(c,a,s,f,v,0,NULL,out,1);
}
Rt8Handle *rt8_construct_sum(Rt8Context *c,Rt8Handle *a,const Rt8Site *s,const Rt8Family *f,const Rt8Variant *v,size_t n,Rt8Handle *const *values,const char *out) {
 rt8_private_enter(c,RT8_OP_SUM,1);return sum_construct(c,a,s,f,v,n,values,out,0);
}
Rt8Handle *rt8_case_i64(Rt8Context *c,Rt8Handle *a,const Rt8Family *family,Rt8Handle *scrutinee,size_t count,const Rt8CaseArm *arms,const char *out) {
 Ir8PacketFamilySpec f;Ir8PacketVariantSpec selected;Rt8ValueFacts sv;Trace st,rt;
 const char *names[RT8_MAX_VARIANTS];rt8_private_enter(c,RT8_OP_CASE,1);
 rt8_private_charge(c,sizeof(st)+sizeof(rt));memset(&st,0,sizeof(st));memset(&rt,0,sizeof(rt));rt8_private_label(c,out);rt8_private_authority(c,a);
 (void)family_check(c,family,&f);
 for(uint32_t i=0;i<f.variants.count;++i){Ir8PacketVariantSpec v;(void)variant_at(c,&f,i,&v);G(c,25,STATE,EQUATION,11,f.family,3,v.field_count==0);}
 (void)ready_sum(c,scrutinee,&f,&sv,&selected);
 G(c,0,REFERENCE,COUNT,11,f.family,3,count==f.variants.count&&arms!=NULL);
 for(size_t i=0;i<count;++i){Ir8PacketVariantSpec v;Rt8ValueFacts value;const Rt8Variant *expected=variant_at(c,&f,(uint32_t)i,&v);
  G(c,25,STATE,EQUATION,11,f.family,3,arms[i].variant==expected&&v.field_count==0&&arms[i].value!=a);
  for(size_t j=0;j<i;++j)G(c,17,OWNERSHIP,OWNER,N,N,N,arms[i].value!=arms[j].value);
  selectable(c,arms[i].value,&value);names[i]=rt8_private_string(c,v.name);
  if(i==selected.index)trace_shape(c,&value.shape,&rt);
 }
 trace_shape(c,&sv.shape,&st);reserve_rows(c,count,256);
 Rt8Handle *h=arms[selected.index].value;Rt8Node *n=h->node;
 if(rt8_private_event(c,"case_i64")){rt8_private_num(c,"scrutinee",sv.node->id);rt8_private_str(c,"family",st.layout);rt8_private_str(c,"variant",names[selected.index]);
  rt8_private_num(c,"variant_index",selected.index);rt8_private_num(c,"result",n->id);rt8_private_num(c,"owner",h->id);rt8_private_num(c,"group",n->group->id);
  typed_trace(c,&rt);rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"out",out);fputs(",\"alternatives\":{",c->output);
  for(size_t i=0;i<count;++i){if(i)fputc(',',c->output);quoted(c->output,names[i]);fprintf(c->output,":%"PRIu64,arms[i].value->node->id);}fputc('}',c->output);rt8_private_end_event(c);}
 for(size_t i=0;i<count;++i){if(i!=selected.index)rt8_private_drop_prepared(c,arms[i].value);}
 return h;
}
Rt8Handle *rt8_case_fields_i64(Rt8Context *c,Rt8Handle *a,const Rt8Family *family,
 Rt8Handle *scrutinee,size_t count,const Rt8FactoryArm *arms,const char *out) {
 Ir8PacketFamilySpec f;Ir8PacketVariantSpec selected;Rt8ValueFacts sv;
 Rt8SiteFacts chosen_site;Trace source_trace,chosen_trace;
 const char *names[RT8_MAX_CAPTURES],*field_layouts[RT8_MAX_VARIANT_FIELDS];
 const char *variant_name;uint32_t chosen_id=N;
 rt8_private_enter(c,RT8_OP_FACTORY,1);
 rt8_private_charge(c,sizeof(chosen_site)+sizeof(source_trace)+sizeof(chosen_trace));
 memset(&chosen_site,0,sizeof(chosen_site));memset(&source_trace,0,sizeof(source_trace));memset(&chosen_trace,0,sizeof(chosen_trace));
 rt8_private_label(c,out);rt8_private_authority(c,a);
 (void)family_check(c,family,&f);(void)ready_sum(c,scrutinee,&f,&sv,&selected);
 G(c,0,REFERENCE,COUNT,11,f.family,3,count==f.variants.count&&arms!=NULL);
 /* No selected payload cursor is read until the complete arm table passes. */
 for(size_t i=0;i<count;++i){
  Ir8PacketVariantSpec variant;Rt8SiteFacts site;Ir8PacketCodeSpec code;
  const Rt8Variant *expected=variant_at(c,&f,(uint32_t)i,&variant);const Rt8FactoryArm *arm=&arms[i];
  G(c,0,REFERENCE,EQUATION,11,f.family,3,arm->variant==expected);
  rt8_private_site_facts(c,arm->site,IR8_PACKET_SITE_CATEGORY_THUNK,arm->code,NULL,&site);
  intrinsic(c,site.execution.principal_type,IR8_PACKET_SHAPE_KIND_I64);
  G(c,10,TYPE,EQUATION,14,site.site.id,5,site.shape.kind==IR8_PACKET_SHAPE_KIND_I64);
  rt8_private_descriptor(c,2,site.site.code,&code,sizeof(code));
  G(c,10,ORIGIN,COUNT,5,site.site.code,7,arm->capture_count==code.capture_count&&arm->capture_count<=RT8_MAX_CAPTURES&&((arm->capture_count!=0)==(arm->captures!=NULL)));
  size_t fields=0,externals=0;
  for(size_t j=0;j<arm->capture_count;++j){
   const Rt8FactoryCapture *binding=&arm->captures[j];Rt8SlotFacts slot;Ir8PacketFieldSpec capture;
   rt8_private_charge(c,sizeof(*binding)+32);rt8_private_label(c,binding->name);
   rt8_private_descriptor(c,6,code.capture_first+(uint32_t)j,&capture,sizeof(capture));
   rt8_private_slot_spec(c,arm->site,site.origin.env,IR8_PACKET_SLOT_ROLE_CAPTURE,j,&slot);
   G(c,10,ORIGIN,EQUATION,5,site.site.code,7,capture.owner_kind==IR8_PACKET_FIELD_OWNER_CODE&&capture.owner==site.site.code&&capture.position==j&&capture.type==slot.row.type&&capture.relation==slot.row.relation);
   const char *name=rt8_private_string(c,capture.name);
   G(c,0,REFERENCE,EQUATION,5,site.site.code,7,rt8_private_text_equal(c,binding->name,name));
   if(binding->kind==RT8_FACTORY_FIELD){Ir8PacketFieldSpec field;
    G(c,0,REFERENCE,COUNT,11,f.family,3,fields<RT8_MAX_FACTORY_FIELDS&&binding->external==NULL&&binding->field_index<variant.field_count);++fields;
    rt8_private_descriptor(c,5,variant.field_first+(uint32_t)binding->field_index,&field,sizeof(field));
    uint32_t type=rt8_private_resolve(c,field.type,site.origin.env);
    G(c,3,TYPE,EQUATION,16,slot.row.id,6,type==slot.resolved_type);
   }else if(binding->kind==RT8_FACTORY_EXTERNAL){Rt8ValueFacts v;
    G(c,0,REFERENCE,COUNT,11,f.family,3,externals<RT8_MAX_FACTORY_EXTERNALS&&binding->field_index==0);++externals;
    rt8_private_value(c,binding->external,MONO_OWN,&v);rt8_private_publish_check(c,&site.origin,slot.resolved_type,&v);relation(c,a->group,&slot,&v);
   }else rt8_private_guard_fault(c,RT8_STATUS_REFERENCE,RT8_DETAIL_DOMAIN,0,11,f.family,3);
   if(i==selected.index)names[j]=name;
  }
  if(i==selected.index){rt8_private_charge(c,sizeof(site));chosen_site=site;chosen_id=site.site.code;}
 }
 /* Includes fields not selected by any capture (wildcards). */
 for(size_t i=0;i<selected.field_count;++i){Rt8ValueFacts value;Rt8SlotFacts slot;Trace t;
  rt8_private_slot_check(c,sv.node,IR8_PACKET_SLOT_ROLE_VARIANT_FIELD,i,&sv.node->slots[i],&value,&slot);
  G(c,25,STATE,STATE,14,value.site.id,5,value.node->state!=RT8_NS_HOLE);
  trace_shape(c,&value.shape,&t);field_layouts[i]=t.layout;
 }
 const Rt8FactoryArm *chosen=&arms[selected.index];
 /* Check selected target publication against its own THUNK Site, not merely
  * the selected SUM's type. No allocation has occurred yet. */
 for(size_t j=0;j<chosen->capture_count;++j){Rt8SlotFacts slot;Rt8ValueFacts value;
  rt8_private_slot_spec(c,chosen->site,chosen_site.origin.env,IR8_PACKET_SLOT_ROLE_CAPTURE,j,&slot);
  if(chosen->captures[j].kind==RT8_FACTORY_FIELD){const Rt8Slot *field=&sv.node->slots[chosen->captures[j].field_index];rt8_private_node_access(c,field->target,field->access,1,&value);}
  else rt8_private_value(c,chosen->captures[j].external,MONO_OWN,&value);
  rt8_private_publish_check(c,&chosen_site.origin,slot.resolved_type,&value);relation(c,a->group,&slot,&value);
 }
 trace_shape(c,&sv.shape,&source_trace);trace_shape(c,&chosen_site.shape,&chosen_trace);trace_code(c,chosen_id,&chosen_trace);
 variant_name=rt8_private_string(c,selected.name);
 reserve_rows(c,chosen->capture_count,UINT64_C(1024)+sizeof(Rt8FactoryCapture)+sizeof(Rt8Handle)+sizeof(Rt8Slot));
 Rt8Handle **values=rt8_private_array(c,chosen->capture_count,sizeof(*values),RT8_MC_CAPTURES);uint32_t mask=0;
 for(size_t j=0;j<chosen->capture_count;++j){const Rt8FactoryCapture *binding=&chosen->captures[j];
  if(binding->kind==RT8_FACTORY_FIELD){const Rt8Slot *field=&sv.node->slots[binding->field_index];
   values[j]=rt8_private_acquire(c,field->target,field->access);mask|=UINT32_C(1)<<binding->field_index;
   if(rt8_private_event(c,"sum_field_capture")){rt8_private_num(c,"scrutinee",sv.node->id);rt8_private_str(c,"family",source_trace.layout);rt8_private_str(c,"variant",variant_name);
    rt8_private_num(c,"variant_index",selected.index);rt8_private_str(c,"capture",binding->name);rt8_private_num(c,"field_index",binding->field_index);
    rt8_private_num(c,"node",field->target->id);rt8_private_num(c,"owner",values[j]->id);rt8_private_str(c,"layout",field_layouts[binding->field_index]);rt8_private_num(c,"frame",c->frame->id);rt8_private_end_event(c);}
  }else values[j]=binding->external;
 }
 size_t capacity=chosen->capture_count?chosen->capture_count:1;
 Rt8Node *n=rt8_private_new_node(c,a->group,&chosen_site,RT8_NS_THUNK,chosen->code,capacity);
 for(size_t j=0;j<chosen->capture_count;++j)rt8_private_publish_prepared(c,n,names[j],values[j]->node,values[j]->access);
 Rt8Handle *result=expose(c,n,&chosen_site,&chosen_trace,out,"case_fields_i64");
 for(size_t j=0;j<chosen->capture_count;++j)if(chosen->captures[j].kind==RT8_FACTORY_FIELD)rt8_private_drop_prepared(c,values[j]);
 rt8_private_free(c,values);
 if(rt8_private_event(c,"case_fields_i64")){rt8_private_num(c,"scrutinee",sv.node->id);rt8_private_str(c,"family",source_trace.layout);rt8_private_str(c,"variant",variant_name);
  rt8_private_num(c,"variant_index",selected.index);rt8_private_str(c,"code",chosen_trace.code);rt8_private_num(c,"result",n->id);rt8_private_num(c,"owner",result->id);rt8_private_num(c,"group",n->group->id);
  typed_trace(c,&chosen_trace);rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"out",out);rt8_private_num(c,"field_mask",mask);slots_trace(c,n,"captures");
  fputs(",\"field_indices\":{",c->output);int first=1;
  for(size_t j=0;j<chosen->capture_count;++j)if(chosen->captures[j].kind==RT8_FACTORY_FIELD){if(!first)fputc(',',c->output);first=0;quoted(c->output,chosen->captures[j].name);fprintf(c->output,":%zu",chosen->captures[j].field_index);}
  fputc('}',c->output);rt8_private_end_event(c);}
 return result;
}
static void intro_rows(Rt8Context *c,const Rt8Intro *ref,Ir8PacketIntro *intro,Ir8PacketScheme *scheme,Ir8PacketEnv *env) {
 uint32_t id=rt8_private_table_auth(c,18,ref);rt8_private_table(c,18,id,intro,sizeof(*intro));
 rt8_private_table(c,3,intro->scheme,scheme,sizeof(*scheme));rt8_private_table(c,4,scheme->neutral_env,env,sizeof(*env));
 G(c,14,ORIGIN,TOKEN,18,id,1,scheme->intro==id&&scheme->body==intro->body_type&&env->mode==IR8_PACKET_ENV_MODE_NEUTRAL&&env->scheme==scheme->id);
}
void rt8_generic_begin(Rt8Context *c,Rt8GenericScope *scope,const Rt8Intro *ref,Rt8Handle *authority) {
 Ir8PacketIntro intro;Ir8PacketScheme scheme;Ir8PacketEnv env;
 rt8_private_enter(c,RT8_OP_BEGIN,1);G(c,14,ORIGIN,TOKEN,N,N,N,scope!=NULL);
 intro_rows(c,ref,&intro,&scheme,&env);rt8_private_authority(c,authority);Rt8Frame *f=c->frame;
 G(c,14,ORIGIN,TOKEN,18,intro.id,2,!f->active_intro&&f->execution.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE&&f->execution.capsule_id==0&&f->execution.creation_activation==0&&rt8_private_table_auth(c,4,f->execution.env)==0);
 if(intro.container_tag==IR8_PACKET_INTRO_CONTAINER_ENTRY)
  G(c,14,ORIGIN,TOKEN,18,intro.id,2,f->kind==RT8_FRAME_ENTRY&&f->code==NULL&&intro.container_code==N);
 else {Ir8PacketCodeTyping ct;Ir8PacketCodeExecution ce;(void)rt8_private_code_execution(c,f->code,f->execution.env,&ct,&ce);
  G(c,14,ORIGIN,TOKEN,18,intro.id,3,intro.container_tag==IR8_PACKET_INTRO_CONTAINER_CODE&&f->kind!=RT8_FRAME_ENTRY&&ct.id==intro.container_code);}
 rt8_private_charge(c,sizeof(*scope));
 G(c,14,ORIGIN,TOKEN,18,intro.id,N,scope->frame_id==0&&scope->capsule_id==0&&scope->handle_watermark==0&&scope->intro==NULL&&scope->authority==NULL&&scope->prior_env==NULL&&scope->prior_capsule_id==0&&scope->prior_intro==NULL&&scope->prior_origin_kind==0&&scope->state==RT8_SCOPE_UNUSED);
 const Rt8Env *neutral=rt8_private_table_ref(c,4,env.id);
 rt8_private_charge(c,256);uint64_t capsule=rt8_private_identity(c,&c->next_capsule);
 Rt8EventReservation event=rt8_private_event_prepare(c);
 uint64_t frame=f->id,aid=authority->id,watermark=c->next_handle;
 /* All fallible guard/counter work precedes the plain member-write suffix. */
 scope->frame_id=frame;scope->capsule_id=capsule;scope->handle_watermark=watermark;scope->intro=ref;scope->authority=authority;
 scope->prior_env=f->execution.env;scope->prior_capsule_id=f->execution.capsule_id;scope->prior_intro=f->active_intro;scope->prior_origin_kind=f->execution.kind;
 f->execution.env=neutral;f->execution.capsule_id=capsule;f->execution.creation_activation=0;f->execution.kind=IR8_PACKET_ORIGIN_KIND_GENERIC;f->active_intro=ref;scope->state=RT8_SCOPE_ACTIVE;
 if(rt8_private_event_commit(c,"generic_begin",event)){rt8_private_num(c,"frame",frame);rt8_private_num(c,"intro",intro.id);rt8_private_num(c,"scheme",scheme.id);rt8_private_num(c,"capsule",capsule);rt8_private_num(c,"authority",aid);rt8_private_num(c,"watermark",watermark);rt8_private_end_event(c);}
}
Rt8Handle *rt8_generic_seal(Rt8Context *c,Rt8GenericScope *scope,Rt8Handle *h,const char *out) {
 Ir8PacketIntro intro;Ir8PacketScheme scheme;Ir8PacketEnv env;Rt8ValueFacts v;
 rt8_private_enter(c,RT8_OP_SEAL,0);rt8_private_label(c,out);G(c,14,ORIGIN,TOKEN,N,N,N,scope!=NULL);
 rt8_private_charge(c,sizeof(*scope));Rt8Frame *f=c->frame;
 G(c,14,ORIGIN,TOKEN,N,N,N,scope->state==RT8_SCOPE_ACTIVE&&scope->frame_id==f->id&&scope->intro==f->active_intro&&scope->capsule_id==f->execution.capsule_id&&scope->capsule_id!=0&&scope->handle_watermark<=c->next_handle);
 intro_rows(c,scope->intro,&intro,&scheme,&env);rt8_private_authority(c,scope->authority);
 G(c,14,ORIGIN,TOKEN,18,intro.id,N,scope->prior_origin_kind==IR8_PACKET_ORIGIN_KIND_CONCRETE&&scope->prior_capsule_id==0&&scope->prior_intro==NULL&&rt8_private_table_auth(c,4,scope->prior_env)==0&&f->execution.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&f->execution.creation_activation==0&&rt8_private_table_auth(c,4,f->execution.env)==env.id);
 rt8_private_value(c,h,MOVE_VALUE,&v);
 G(c,5,ORIGIN,EQUATION,18,intro.id,6,v.node->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&v.node->origin.capsule_id==scope->capsule_id&&v.row.origin_env==env.id&&v.row.use_env==env.id&&v.row.type==scheme.body&&h->scope==f->id);
 int permitted=0;for(uint32_t i=0;i<intro.result_sites.count;++i){Ir8PacketSiteRef r;rt8_private_vector(c,intro.result_sites.object,IR8_PACKET_ELEMENT_SITE_REF,i,&r,sizeof(r));rt8_private_charge(c,4);if(r.row==v.site.id)permitted=1;}
 G(c,3,TYPE,EQUATION,18,intro.id,6,permitted&&v.site.principal_type==scheme.body&&v.site.context_intro==intro.id);
 for(Rt8Handle *p=c->handles;p;){rt8_private_live(c,p);G(c,20,OWNERSHIP,EQUATION,18,intro.id,N,p->id<=scope->handle_watermark||p==h);rt8_private_charge(c,sizeof(p->next));p=p->next;}
 const Rt8Access *next=rt8_private_access(c,v.site.id,env.id,IR8_PACKET_ACCESS_MODE_SCHEME,N,scheme.id);
 uint32_t next_id=rt8_private_table_auth(c,17,next);rt8_private_guard_seen(c,16);rt8_private_charge(c,256);
 uint64_t frame=f->id,capsule=scope->capsule_id,owner=h->id,node=v.node->id;uint32_t old=v.row.id;
 Rt8EventReservation event=rt8_private_event_prepare(c);
 h->access=next;f->execution.env=scope->prior_env;f->execution.capsule_id=scope->prior_capsule_id;f->execution.creation_activation=0;f->execution.kind=scope->prior_origin_kind;f->active_intro=scope->prior_intro;scope->state=RT8_SCOPE_SEALED;
 if(rt8_private_event_commit(c,"generic_seal",event)){rt8_private_num(c,"frame",frame);rt8_private_num(c,"intro",intro.id);rt8_private_num(c,"capsule",capsule);rt8_private_num(c,"owner",owner);rt8_private_num(c,"node",node);rt8_private_num(c,"old_access",old);rt8_private_num(c,"new_access",next_id);rt8_private_end_event(c);}
 return h;
}
/* The borrowed packet was fully admitted and remains immutable. Its pool and
 * LEGACY bindings have the same unsigned-byte lexical order, so exact registered
 * string offsets permit a bounded search without reinterpreting a nominal name.
 * No result, Handle or metadata cache is published by this preflight. */
static int nominal_argument(Rt8Context *c,const Ir8PacketType *t,const char *atom) {
 uint32_t lo=0,hi;Ir8PacketShapeBinding s;Ir8PacketShapeTyping st;
 Ir8PacketShapeSpec spec;Ir8PacketRepresentation rep;
 rt8_private_charge(c,1);hi=c->program.typed_header.table[6].count;
 while(lo<hi){uint32_t m=lo+(hi-lo)/2;rt8_private_table(c,7,m,&s,sizeof(s));
  rt8_private_charge(c,5);
  if(s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&s.source_reference<t->atom)lo=m+1;else hi=m;}
 G(c,15,TYPE,MISSING,1,t->id,2,lo<c->program.typed_header.table[6].count);
 rt8_private_table(c,7,lo,&s,sizeof(s));rt8_private_table(c,8,lo,&st,sizeof(st));
 rt8_private_table(c,9,lo,&rep,sizeof(rep));rt8_private_descriptor(c,1,lo,&spec,sizeof(spec));
 G(c,15,TYPE,EQUATION,1,t->id,2,t->tag==IR8_PACKET_TYPE_TAG_CLOSED&&
  s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&s.source_reference==t->atom&&
  s.source_type==N&&s.source_scheme==N&&
  (s.kind==IR8_PACKET_SHAPE_KIND_DATA||s.kind==IR8_PACKET_SHAPE_KIND_SUM));
 G(c,15,TYPE,EQUATION,8,st.id,2,st.shape==s.id&&st.type==t->id&&st.scope==N&&st.contract==N&&
  rep.shape==s.id&&rep.typing==st.id&&
  rep.ready_kind==(s.kind==IR8_PACKET_SHAPE_KIND_DATA?IR8_PACKET_READY_KIND_DATA:IR8_PACKET_READY_KIND_SUM));
 G(c,15,TYPE,EQUATION,7,s.id,5,spec.shape==s.id&&spec.typing==st.id&&spec.representation==rep.id&&
  spec.kind==s.kind&&s.argument_rep==N&&s.result_rep==N&&spec.argument_rep==N&&spec.result_rep==N);
 if(s.kind==IR8_PACKET_SHAPE_KIND_DATA){
  G(c,15,TYPE,EQUATION,1,t->id,2,atom[0]!='#'&&atom[0]!='%'&&atom[0]!='@'&&atom[0]!='^');return 1;}
 G(c,15,TYPE,EQUATION,1,t->id,2,atom[0]=='%');
 rt8_private_charge(c,2);lo=0;hi=c->program.typed_header.table[10].count;
 while(lo<hi){Ir8PacketFamilyTyping f;uint32_t m=lo+(hi-lo)/2;
  rt8_private_table(c,11,m,&f,sizeof(f));rt8_private_charge(c,3);if(f.shape<s.id)lo=m+1;else hi=m;}
 G(c,15,TYPE,MISSING,7,s.id,5,lo<c->program.typed_header.table[10].count);
 Ir8PacketFamilyTyping f;Ir8PacketFamilySpec fs;
 rt8_private_table(c,11,lo,&f,sizeof(f));rt8_private_descriptor(c,3,lo,&fs,sizeof(fs));
 G(c,15,TYPE,EQUATION,11,f.id,2,f.shape==s.id&&fs.family==f.id&&fs.shape==s.id&&
  fs.variants.count==f.variants.count&&f.variants.count>=1&&f.variants.count<=RT8_MAX_VARIANTS);
 const char *name=rt8_private_string(c,f.name);
 G(c,15,TYPE,EQUATION,11,f.id,1,literal_equal(c,atom+1,name));return 1;
}
/* Fresh bounded lookup in the admitted immutable Shape table. This helper is
 * exclusive to arrow-coordinate validation; old atom paths keep their work. */
static uint32_t argument_shape(Rt8Context *c,const Ir8PacketType *t) {
 uint32_t lo=0,hi,tag,key;Ir8PacketShapeBinding s;
 rt8_private_charge(c,5);hi=c->program.typed_header.table[6].count;
 tag=t->tag==IR8_PACKET_TYPE_TAG_ARROW?IR8_PACKET_SHAPE_SOURCE_CANONICAL_ARROW:IR8_PACKET_SHAPE_SOURCE_LEGACY;
 key=t->tag==IR8_PACKET_TYPE_TAG_ARROW?t->id:t->atom;
 while(lo<hi){uint32_t m=lo+(hi-lo)/2;rt8_private_table(c,7,m,&s,sizeof(s));
  rt8_private_charge(c,7);uint32_t value=tag==IR8_PACKET_SHAPE_SOURCE_LEGACY?s.source_reference:s.source_type;
  if(s.source_tag<tag||(s.source_tag==tag&&value<key))lo=m+1;else hi=m;}
 G(c,15,TYPE,MISSING,1,t->id,1,lo<c->program.typed_header.table[6].count);
 rt8_private_table(c,7,lo,&s,sizeof(s));
 G(c,15,TYPE,MISSING,7,lo,1,s.source_tag==tag&&
  (tag==IR8_PACKET_SHAPE_SOURCE_LEGACY?s.source_reference:s.source_type)==key);
 return lo;
}
static int arrow_argument(Rt8Context *c,uint32_t root) {
 uint32_t stack[RT8_MAX_WALK_DEPTH][3],sp=1;
 rt8_private_charge(c,sizeof(stack[0])+1);stack[0][0]=root;stack[0][1]=N;stack[0][2]=1;
 while(sp){uint32_t type,expected,depth,id;Ir8PacketType t;Ir8PacketShapeBinding s;
  Ir8PacketShapeTyping st;Ir8PacketRepresentation rep;Ir8PacketShapeSpec spec;
  rt8_private_charge(c,sizeof(stack[0])+4);--sp;
  type=stack[sp][0];expected=stack[sp][1];depth=stack[sp][2];rt8_private_table(c,1,type,&t,sizeof(t));
  G(c,15,TYPE,EQUATION,1,type,1,depth<=RT8_MAX_WALK_DEPTH&&
   (t.tag==IR8_PACKET_TYPE_TAG_CLOSED||t.tag==IR8_PACKET_TYPE_TAG_ARROW));
  id=argument_shape(c,&t);
  G(c,15,TYPE,EQUATION,1,type,1,(expected==N&&depth==1)||(expected!=N&&expected==id));
  rt8_private_table(c,7,id,&s,sizeof(s));rt8_private_table(c,8,id,&st,sizeof(st));
  rt8_private_table(c,9,id,&rep,sizeof(rep));rt8_private_descriptor(c,1,id,&spec,sizeof(spec));
  G(c,15,TYPE,EQUATION,8,id,2,st.shape==id&&st.type==t.id&&st.scope==N&&rep.shape==id&&rep.typing==id&&
   spec.shape==id&&spec.typing==id&&spec.representation==id&&spec.kind==s.kind&&
   spec.argument_rep==s.argument_rep&&spec.result_rep==s.result_rep);
  if(t.tag==IR8_PACKET_TYPE_TAG_ARROW){Ir8PacketCallableContract contract;
   G(c,15,TYPE,EQUATION,1,type,5,t.atom==N&&t.scheme==N&&t.index==N&&t.argument<t.id&&t.result<t.id&&
    t.protocol==IR8_PACKET_PROTOCOL_REPEAT&&t.result_identity==IR8_PACKET_RESULT_IDENTITY_UNKNOWN);
   G(c,15,TYPE,EQUATION,7,id,1,s.source_tag==IR8_PACKET_SHAPE_SOURCE_CANONICAL_ARROW&&s.source_type==t.id&&
    s.source_reference==N&&s.source_scheme==N&&s.kind==IR8_PACKET_SHAPE_KIND_REPEAT&&
    rep.ready_kind==IR8_PACKET_READY_KIND_FUNCTION&&s.argument_rep!=N&&s.result_rep!=N&&
    spec.fields_object==N&&spec.field_first==0&&spec.field_count==0);
   rt8_private_table(c,2,st.contract,&contract,sizeof(contract));
   G(c,15,TYPE,EQUATION,2,contract.id,1,contract.type==t.id&&contract.argument==t.argument&&
    contract.result==t.result&&contract.protocol==t.protocol&&contract.result_identity==t.result_identity);
   G(c,15,TYPE,COUNT,1,type,N,depth<RT8_MAX_WALK_DEPTH&&sp<=RT8_MAX_WALK_DEPTH-2);
   rt8_private_charge(c,2*sizeof(stack[0])+8);
   stack[sp][0]=t.result;stack[sp][1]=s.result_rep;stack[sp][2]=depth+1;++sp;
   stack[sp][0]=t.argument;stack[sp][1]=s.argument_rep;stack[sp][2]=depth+1;++sp;
  }else{const char *atom=rt8_private_string(c,t.atom);int b,i;
   G(c,15,TYPE,EQUATION,1,type,1,t.scheme==N&&t.index==N&&t.argument==N&&t.result==N&&t.protocol==N&&t.result_identity==N);
   b=literal_equal(c,atom,"#bool");i=literal_equal(c,atom,"#i64");
   if(b||i){
    G(c,15,TYPE,EQUATION,7,id,1,s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&s.source_reference==t.atom&&
     s.source_type==N&&s.source_scheme==N&&s.kind==(b?IR8_PACKET_SHAPE_KIND_BOOL:IR8_PACKET_SHAPE_KIND_I64)&&
     st.contract==N&&rep.ready_kind==IR8_PACKET_READY_KIND_SCALAR&&s.argument_rep==N&&s.result_rep==N&&
     spec.fields_object==N&&spec.field_first==0&&spec.field_count==0);
   }else (void)nominal_argument(c,&t,atom);
  }
 }
 return 1;
}

Rt8Handle *rt8_instantiate(Rt8Context *c,Rt8Handle *h,const Rt8Instantiation *ref,const char *out,const char *source) {
 Rt8ValueFacts v;Ir8PacketUse use;Ir8PacketScheme scheme;Ir8PacketEnv env;
 rt8_private_enter(c,RT8_OP_INSTANTIATE,1);rt8_private_label(c,out);rt8_private_label(c,source);
 rt8_private_value(c,h,RT8_VALUE_TICKET_FREE|RT8_VALUE_NO_LOANS,&v);
 uint32_t uid=rt8_private_table_auth(c,19,ref);rt8_private_table(c,19,uid,&use,sizeof(use));
 rt8_private_table(c,3,use.scheme,&scheme,sizeof(scheme));rt8_private_table(c,4,use.env,&env,sizeof(env));
 G(c,21,TYPE,APPLICABILITY,19,uid,2,v.row.mode==IR8_PACKET_ACCESS_MODE_SCHEME&&v.row.scheme==use.scheme&&v.row.type==scheme.body&&v.node->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&v.row.origin_env==scheme.neutral_env);
 G(c,15,TYPE,EQUATION,19,uid,3,scheme.parameters>=1&&scheme.parameters<=8&&use.arguments.count==scheme.parameters&&env.arguments.count==scheme.parameters&&env.scheme==scheme.id&&env.mode==IR8_PACKET_ENV_MODE_CLOSED);
 for(uint32_t i=0;i<scheme.parameters;++i){Ir8PacketTypeRef a,b;Ir8PacketType t;
  rt8_private_vector(c,use.arguments.object,IR8_PACKET_ELEMENT_TYPE_REF,i,&a,sizeof(a));rt8_private_vector(c,env.arguments.object,IR8_PACKET_ELEMENT_TYPE_REF,i,&b,sizeof(b));
  G(c,15,TYPE,EQUATION,19,uid,3,a.row==b.row);rt8_private_table(c,1,a.row,&t,sizeof(t));
  if(t.tag==IR8_PACKET_TYPE_TAG_ARROW){(void)arrow_argument(c,t.id);}
  else {G(c,15,TYPE,EQUATION,1,t.id,1,t.tag==IR8_PACKET_TYPE_TAG_CLOSED);const char *atom=rt8_private_string(c,t.atom);
   G(c,15,TYPE,EQUATION,1,t.id,2,literal_equal(c,atom,"#i64")||literal_equal(c,atom,"#bool")||nominal_argument(c,&t,atom));}}
 G(c,25,STATE,STATE,14,v.site.id,5,v.node->state!=RT8_NS_HOLE);
 const Rt8Access *next=rt8_private_access(c,v.site.id,v.row.origin_env,IR8_PACKET_ACCESS_MODE_MONO,use.env,N);uint32_t nextid=rt8_private_table_auth(c,17,next);Ir8PacketAccess access;
 rt8_private_table(c,17,nextid,&access,sizeof(access));G(c,15,TYPE,EQUATION,19,uid,5,access.type==use.result_type);
 rt8_private_guard_seen(c,16);rt8_private_guard_seen(c,22);rt8_private_charge(c,256);
 uint64_t frame=c->frame->id,owner=h->id,node=v.node->id,anchor=h->anchor?h->anchor->id:0;int loan=h->anchor!=NULL;
 Rt8EventReservation event=rt8_private_event_prepare(c);h->access=next;
 if(rt8_private_event_commit(c,"instantiate",event)){rt8_private_num(c,"frame",frame);rt8_private_num(c,"use",uid);rt8_private_num(c,"scheme",scheme.id);rt8_private_num(c,"owner",owner);rt8_private_num(c,"node",node);rt8_private_num(c,"old_access",v.row.id);rt8_private_num(c,"new_access",nextid);rt8_private_str(c,"mode",loan?"loan":"own");if(loan)rt8_private_num(c,"anchor",anchor);else rt8_private_str(c,"anchor",NULL);rt8_private_end_event(c);}
 return h;
}
