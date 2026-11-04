/* Stage05B genuine callback/Force engine. Source-only, unexecuted.
 * Principal evaluation, saved per-destination requests, reverse validation and
 * forward operational publication are distinct phases. No inverse type lookup. */
#include "rir8_runtime_internal.h"
#include <inttypes.h>
#include <string.h>
#define N RT8_NULL
#define G(c,n,s,d,t,r,f,p) do { rt8_private_charge((c),16); \
 rt8_private_guard_seen((c),(n)); if(!(p)) \
 rt8_private_guard_fault((c),RT8_STATUS_##s,RT8_DETAIL_##d,(n),(t),(r),(f)); } while(0)
#define MOVE_VALUE (RT8_VALUE_OWN|RT8_VALUE_MONO|RT8_VALUE_TICKET_FREE|RT8_VALUE_NO_LOANS)

typedef struct CallPlan {
 Rt8Frame frame;
 Rt8Body body;
 size_t count;
 const char *name;
 const Rt8Access *views[RT8_MAX_CAPTURES];
} CallPlan;
static const char *state_name(uint32_t s) {
 switch(s){case RT8_NS_READY:return "READY";case RT8_NS_HOLE:return "HOLE";case RT8_NS_INDIRECT:return "INDIRECT";
 case RT8_NS_THUNK:return "THUNK";case RT8_NS_CLOSURE:return "CLOSURE";case RT8_NS_APPLICATION:return "APPLICATION";
 case RT8_NS_BUSY:return "BUSY";case RT8_NS_MEMO:return "MEMO";default:return NULL;}
}
static void quoted(FILE *out,const char *s) {
 if(!s){fputs("null",out);return;}fputc('"',out);
 for(const unsigned char *p=(const unsigned char *)s;*p;++p){unsigned x=*p;
  if(x=='"'||x=='\\'){fputc('\\',out);fputc((int)x,out);}else if(x<32)fprintf(out,"\\u%04x",x);else fputc((int)x,out);}
 fputc('"',out);
}
static const char *layout(Rt8Context *c,const Rt8ValueFacts *v) {
 Ir8PacketShapeBinding b;rt8_private_table(c,7,v->shape.shape,&b,sizeof(b));
 return b.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY?rt8_private_string(c,b.source_reference):NULL;
}
static void charge_rows(Rt8Context *c,size_t count,uint64_t unit) {
 G(c,0,OVERFLOW,OVERFLOW,N,N,N,unit!=0&&count<=UINT64_MAX/unit);rt8_private_charge(c,(uint64_t)count*unit);
}
static void depth_preflight(Rt8Context *c) {
 rt8_private_charge(c,8);if(c->activation_depth>=RT8_MAX_ACTIVATION_DEPTH)rt8_private_fault(c,RT8_FAULT_STACK_LIMIT);
}
void rt8_private_frame_push(Rt8Context *c,Rt8Frame *f,const char *name,Rt8Node *source) {
 /* Inputs and all subsequent plain read/write work are prepared by caller.
  * Identity/metric/event failure remains a genuine operational boundary. */
 if(c->activation_depth>=RT8_MAX_ACTIVATION_DEPTH)rt8_private_fault(c,RT8_FAULT_STACK_LIMIT);
 f->id=rt8_private_identity(c,&c->next_frame);f->parent=c->frame;c->frame=f;
 if(f->execution.kind==IR8_PACKET_ORIGIN_KIND_INSTANCE)f->execution.creation_activation=f->id;
 rt8_private_bump(c,&c->activation_depth);rt8_private_peak(&c->report.max_activation_depth,c->activation_depth);
 if(f->home){f->home->home=1;f->home->scope=f->id;}
 if(rt8_private_event(c,"frame_enter")){rt8_private_num(c,"frame",f->id);
  if(f->parent)rt8_private_num(c,"parent_frame",f->parent->id);else rt8_private_str(c,"parent_frame",NULL);
  fputs(",\"context\":{\"kind\":",c->output);quoted(c->output,f->kind==RT8_FRAME_ENTRY?"entry":f->kind==RT8_FRAME_FUNCTION?"function":"thunk");
  if(f->code){rt8_private_str(c,"name",name);rt8_private_num(c,"node",source->id);rt8_private_num(c,"home_group",f->home->group->id);}
  fputc('}',c->output);rt8_private_end_event(c);}
}
void rt8_private_frame_pop(Rt8Context *c,Rt8Frame *f) {
 if(c->frame!=f||!c->activation_depth)rt8_private_fault(c,RT8_FAULT_INVARIANT);
 c->frame=f->parent;--c->activation_depth;
}
static void capture_plan(Rt8Context *c,Rt8Node *n,const Rt8Access *request,
 const Ir8PacketCodeExecution *execution,CallPlan *plan,int projected) {
 G(c,10,ORIGIN,COUNT,5,execution->code,7,n->used<=RT8_MAX_CAPTURES&&n->used==execution->captures.count);
 plan->count=n->used;
 for(size_t i=0;i<n->used;++i){Rt8ValueFacts value;Rt8SlotFacts slot;Ir8PacketResolvedCapture resolved;
  rt8_private_slot_check(c,n,IR8_PACKET_SLOT_ROLE_CAPTURE,i,&n->slots[i],&value,&slot);
  const Rt8Access *view=value.access;
  if(projected){
   if(n->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&value.node->origin.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE)
    view=rt8_private_capture_transport(c,n,request,i);
   else view=rt8_private_transport(c,n,slot.resolved_type,request,value.node,value.access);
  }
  rt8_private_vector(c,execution->captures.object,IR8_PACKET_ELEMENT_RESOLVED_CAPTURE,(uint32_t)i,&resolved,sizeof(resolved));
  Ir8PacketAccess access;uint32_t aid=rt8_private_table_auth(c,17,view);rt8_private_table(c,17,aid,&access,sizeof(access));
  G(c,3,TYPE,EQUATION,6,execution->id,5,resolved.code==execution->code&&resolved.position==i&&resolved.type==access.type);
  rt8_private_charge(c,sizeof(view));plan->views[i]=view;
 }
 charge_rows(c,plan->count,UINT64_C(512)+sizeof(Rt8Slot)+sizeof(Rt8Handle));
}
static void prepare_call(Rt8Context *c,Rt8Node *n,const Rt8Access *request,Rt8Handle *argument,int thunk,CallPlan *plan) {
 Rt8ValueFacts value;Ir8PacketCodeTyping code;Ir8PacketCodeExecution execution;Ir8PacketEnv env;
 rt8_private_node_access(c,n,request,1,&value);depth_preflight(c);
 G(c,25,STATE,STATE,14,value.site.id,5,n->state==(thunk?RT8_NS_THUNK:RT8_NS_CLOSURE));
 rt8_private_charge(c,sizeof(*plan));memset(plan,0,sizeof(*plan));plan->frame.execution=n->origin;
 const Rt8Env *lexical=n->origin.env;int projected=0;
 if(!thunk&&n->origin.kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&value.row.use_env!=value.row.origin_env){
  lexical=rt8_private_table_ref(c,4,value.row.use_env);rt8_private_table(c,4,value.row.use_env,&env,sizeof(env));
  G(c,15,ORIGIN,EQUATION,4,env.id,1,env.mode==IR8_PACKET_ENV_MODE_CLOSED&&env.scheme==value.site.scope);
  plan->frame.execution.kind=IR8_PACKET_ORIGIN_KIND_INSTANCE;projected=1;
 }
 plan->frame.execution.env=lexical;
 plan->frame.code=n->code;plan->frame.kind=thunk?RT8_FRAME_THUNK:RT8_FRAME_FUNCTION;
 plan->frame.code_execution=rt8_private_code_execution(c,n->code,lexical,&code,&execution);
 G(c,10,ORIGIN,EQUATION,5,code.id,1,code.id==value.site.code&&code.kind==(thunk?IR8_PACKET_CODE_KIND_THUNK:IR8_PACKET_CODE_KIND_FUNCTION));
 plan->frame.expected_result_type=execution.result;
 plan->frame.result_identity=thunk?N:(code.expected_identity_flag?IR8_PACKET_RESULT_IDENTITY_ARGUMENT:IR8_PACKET_RESULT_IDENTITY_UNKNOWN);
 plan->name=rt8_private_string(c,code.name);
 /* Authentication above used typed native Code reads. This is the same exact
  * immutable Code member, not a converted object pointer or lookup by name. */
 Rt8Code binding;rt8_private_charge(c,sizeof(binding)*2);memcpy(&binding,n->code,sizeof(binding));plan->body=binding.body;
 G(c,10,ORIGIN,EQUATION,5,code.id,0,plan->body!=NULL);
 if(thunk){G(c,10,TYPE,EQUATION,6,execution.id,4,execution.result==value.execution.principal_type&&argument==NULL);}
 else {Rt8ValueFacts arg;Ir8PacketType arrow;
  rt8_private_value(c,argument,MOVE_VALUE,&arg);rt8_private_table(c,1,value.row.type,&arrow,sizeof(arrow));
  G(c,26,TYPE,EQUATION,6,execution.id,2,arrow.tag==IR8_PACKET_TYPE_TAG_ARROW&&arrow.protocol==IR8_PACKET_PROTOCOL_REPEAT&&
   execution.callable_type==value.row.type&&arrow.argument==execution.argument&&arrow.result==execution.result&&
   arrow.result_identity==plan->frame.result_identity);
  if(projected){
   G(c,3,TYPE,EQUATION,6,execution.id,3,arg.row.type==execution.argument&&rt8_private_type_closed(c,execution.argument));
   G(c,6,ORIGIN,EQUATION,4,env.id,1,env.mode==IR8_PACKET_ENV_MODE_CLOSED&&env.scheme==value.site.scope&&n->origin.capsule_id!=0);
   rt8_private_guard_seen(c,9);
  }else rt8_private_publish_check(c,&plan->frame.execution,execution.argument,&arg);
  plan->frame.argument_node_id=arg.node->id;plan->frame.argument_group=arg.node->group;
 }
 capture_plan(c,n,request,&execution,plan,projected);
 rt8_private_charge(c,UINT64_C(1024)+sizeof(Rt8Frame));
}
static Rt8Handle **capture_owners(Rt8Context *c,Rt8Node *n,size_t count,const Rt8Access *const *views) {
 Rt8Handle **owners=rt8_private_array(c,count,sizeof(*owners),RT8_MC_CAPTURES);
 for(size_t i=0;i<count;++i){owners[i]=rt8_private_acquire(c,n->slots[i].target,views[i]);}
 return owners;
}
static void handoff(Rt8Context *c,const char *kind,Rt8Node *n,Rt8Handle **owners,size_t count,int repeat) {
 if(rt8_private_event(c,kind)){rt8_private_num(c,"node",n->id);if(repeat)rt8_private_str(c,"protocol","repeat");fputs(",\"owners\":{",c->output);
  for(size_t i=0;i<count;++i){if(i)fputc(',',c->output);quoted(c->output,n->slots[i].name);fprintf(c->output,":%"PRIu64,owners[i]->id);}fputc('}',c->output);rt8_private_end_event(c);}
}
static Rt8Handle *invoke(Rt8Context *c,Rt8Handle *callee,Rt8Handle *argument,Rt8Handle *ceiling) {
 Rt8ValueFacts value;CallPlan plan;rt8_private_value(c,callee,MOVE_VALUE,&value);
 /* Internal Force pin is not a public authority. Authenticate its exact role
  * and live Group directly; never pass it through public authority(). */
 rt8_private_live(c,ceiling);G(c,17,OWNERSHIP,OWNER,N,N,N,ceiling->role==RT8_RC_PIN&&!ceiling->anchor&&!ceiling->home&&!ceiling->access&&!ceiling->fill_ticket);
 prepare_call(c,value.node,value.access,argument,0,&plan);
 Rt8Handle *pin=rt8_private_handle(c,ceiling->group,NULL,NULL,NULL,RT8_RC_PIN);
 Rt8Handle *home=rt8_private_handle(c,ceiling->group,NULL,NULL,pin,RT8_RC_KEY);
 rt8_private_bump(c,&c->report.ordinary_calls);
 Rt8Handle **captures=capture_owners(c,value.node,plan.count,plan.views);handoff(c,"closure_capture_handoff",value.node,captures,plan.count,1);
 if(rt8_private_event(c,"invoke_enter")){rt8_private_num(c,"closure",value.node->id);rt8_private_num(c,"closure_group",value.node->group->id);rt8_private_num(c,"home",ceiling->group->id);rt8_private_num(c,"argument",plan.frame.argument_node_id);rt8_private_str(c,"protocol","repeat");rt8_private_end_event(c);}
 plan.frame.home=home;rt8_private_frame_push(c,&plan.frame,plan.name,value.node);
 for(size_t i=0;i<plan.count;++i){captures[i]->scope=plan.frame.id;}
 argument->scope=plan.frame.id;
 Rt8Handle *result=plan.body(c,home,captures,argument,plan.frame.execution.env);
 G(c,23,OWNERSHIP,EQUATION,N,N,N,plan.frame.returned&&result==plan.frame.returned_handle&&c->frame==&plan.frame);
 Rt8ValueFacts returned;rt8_private_value(c,result,MOVE_VALUE,&returned);
 rt8_private_charge(c,512);
 if(rt8_private_event(c,"invoke_raw_return")){rt8_private_num(c,"closure",value.node->id);rt8_private_num(c,"argument",plan.frame.argument_node_id);rt8_private_num(c,"result",returned.node->id);rt8_private_str(c,"token",NULL);rt8_private_num(c,"owner",result->id);rt8_private_num(c,"home",pin->group->id);rt8_private_end_event(c);}
 rt8_private_frame_pop(c,&plan.frame);rt8_private_free(c,captures);rt8_private_drop_prepared(c,home);rt8_private_drop_prepared(c,callee);rt8_private_drop_prepared(c,pin);return result;
}
static Rt8Handle *callback(Rt8Context *c,Rt8Node *n,Rt8Handle *pin,Rt8Handle **captures,CallPlan *plan) {
 Rt8Handle *home=rt8_private_handle(c,n->group,NULL,NULL,pin,RT8_RC_KEY);
 rt8_private_bump(c,&c->report.callback_calls);
 if(rt8_private_event(c,"callback_enter")){rt8_private_num(c,"node",n->id);rt8_private_num(c,"pin",pin->id);rt8_private_end_event(c);}
 plan->frame.home=home;rt8_private_frame_push(c,&plan->frame,plan->name,n);
 for(size_t i=0;i<plan->count;++i)captures[i]->scope=plan->frame.id;
 Rt8Handle *result=plan->body(c,home,captures,NULL,plan->frame.execution.env);
 G(c,23,OWNERSHIP,EQUATION,N,N,N,plan->frame.returned&&result==plan->frame.returned_handle&&c->frame==&plan->frame);
 Rt8ValueFacts returned;rt8_private_value(c,result,MOVE_VALUE,&returned);rt8_private_charge(c,512);
 if(rt8_private_event(c,"raw_return")){rt8_private_num(c,"source",n->id);rt8_private_num(c,"result",returned.node->id);rt8_private_str(c,"result_state",state_name(returned.node->state));rt8_private_num(c,"owner",result->id);rt8_private_num(c,"home_pin",pin->id);rt8_private_end_event(c);}
 if(returned.node->state!=RT8_NS_READY&&returned.node->state!=RT8_NS_CLOSURE)rt8_private_bump(c,&c->report.raw_deferred_returns);
 rt8_private_frame_pop(c,&plan->frame);rt8_private_free(c,captures);rt8_private_drop_prepared(c,home);return result;
}
static _Noreturn void demand_fault(Rt8Context *c,uint32_t fault,uint32_t site) {
 Rt8FaultInfo *d=&c->report.location;rt8_private_guard_seen(c,25);c->report.guards_failed_mask|=UINT32_C(1)<<25;
 d->status=RT8_STATUS_STATE;d->phase=RT8_PHASE_DYNAMIC_GUARD;d->detail=RT8_DETAIL_STATE;
 d->region=RT8_REGION_PACKET;d->domain_kind=RT8_DOMAIN_KIND_PACKET_TABLE;d->domain=14;
 d->object=c->program.typed_header.table[13].object;d->row=site;d->field=5;d->guard_index=25;
 rt8_private_fault(c,fault);
}
static Rt8Handle *force_engine(Rt8Context *c,Rt8Handle *cursor,const char *out,const char *source) {
 Rt8ValueFacts initial;rt8_private_value(c,cursor,MOVE_VALUE,&initial);rt8_private_charge(c,128);
 if(c->force_depth>=RT8_MAX_FORCE_DEPTH)rt8_private_fault(c,RT8_FAULT_STACK_LIMIT);
 uint32_t expected=initial.row.type;cursor->scope=0;rt8_private_bump(c,&c->report.force_calls);rt8_private_bump(c,&c->force_depth);rt8_private_peak(&c->report.max_force_depth,c->force_depth);
 Rt8Pending *first=NULL,*last=NULL;
 if(rt8_private_event(c,"force_enter")){rt8_private_num(c,"depth",c->force_depth);rt8_private_num(c,"cursor",initial.node->id);rt8_private_end_event(c);}
 for(;;){
  Rt8ValueFacts value;rt8_private_tick(c);rt8_private_value(c,cursor,MOVE_VALUE,&value);Rt8Node *n=value.node;
  rt8_private_charge(c,32);uint32_t state=n->state;
  if(state==RT8_NS_READY||state==RT8_NS_CLOSURE)break;
  if(state==RT8_NS_HOLE)demand_fault(c,RT8_FAULT_HOLE,value.site.id);
  if(state==RT8_NS_BUSY)demand_fault(c,RT8_FAULT_BUSY,value.site.id);
  if(state==RT8_NS_MEMO){Rt8ValueFacts target;Rt8SlotFacts slot;
   rt8_private_slot_check(c,n,IR8_PACKET_SLOT_ROLE_MEMO,0,&n->slots[0],&target,&slot);
   const Rt8Access *access=rt8_private_transport(c,n,slot.resolved_type,value.access,target.node,target.access);
   rt8_private_guard_seen(c,8);rt8_private_charge(c,256);
   Rt8Handle *next=rt8_private_acquire(c,target.node,access);rt8_private_bump(c,&c->report.memo_fast_paths);rt8_private_drop_prepared(c,cursor);cursor=next;continue;
  }
  CallPlan plan;Rt8SlotFacts memo;rt8_private_charge(c,sizeof(plan));memset(&plan,0,sizeof(plan));
  rt8_private_slot_spec(c,n->origin_site,n->origin.env,IR8_PACKET_SLOT_ROLE_MEMO,0,&memo);
  G(c,3,TYPE,EQUATION,16,memo.row.id,6,memo.resolved_type==value.execution.principal_type);
  if(state==RT8_NS_INDIRECT){Rt8ValueFacts target;Rt8SlotFacts slot;
   rt8_private_slot_check(c,n,IR8_PACKET_SLOT_ROLE_MEMO,0,&n->slots[0],&target,&slot);plan.count=1;plan.views[0]=target.access;
  }else if(state==RT8_NS_THUNK){
   const Rt8Access *principal=rt8_private_access(c,value.site.id,value.row.origin_env,IR8_PACKET_ACCESS_MODE_MONO,value.row.origin_env,N);
   prepare_call(c,n,principal,NULL,1,&plan);
  }else if(state==RT8_NS_APPLICATION){Rt8ValueFacts fn,arg;Rt8SlotFacts fs,as;Ir8PacketType arrow;
   rt8_private_slot_check(c,n,IR8_PACKET_SLOT_ROLE_FUNCTION,0,&n->slots[0],&fn,&fs);
   rt8_private_slot_check(c,n,IR8_PACKET_SLOT_ROLE_ARGUMENT,0,&n->slots[1],&arg,&as);
   rt8_private_table(c,1,fn.row.type,&arrow,sizeof(arrow));
   G(c,26,TYPE,EQUATION,14,value.site.id,5,arrow.tag==IR8_PACKET_TYPE_TAG_ARROW&&arrow.protocol==IR8_PACKET_PROTOCOL_REPEAT&&arrow.argument==arg.row.type&&arrow.result==value.execution.principal_type);
   plan.count=2;plan.views[0]=fn.access;plan.views[1]=arg.access;
  }else rt8_private_guard_fault(c,RT8_STATUS_STATE,RT8_DETAIL_STATE,25,14,value.site.id,5);
  charge_rows(c,plan.count,UINT64_C(512)+sizeof(Rt8Slot)+sizeof(Rt8Handle));rt8_private_charge(c,1024);
  Rt8Handle *pin=rt8_private_handle(c,n->group,n,NULL,NULL,RT8_RC_PIN);
  Rt8Pending *p=rt8_private_alloc(c,sizeof(*p),RT8_MC_PENDING);
  p->node=n;p->pin=pin;p->previous=last;p->next=NULL;p->requested=value.access;p->memo_access=NULL;p->memo_slot_id=N;p->prepared=0;
  if(last)last->next=p;else first=p;last=p;
  if(rt8_private_event(c,"update_pin")){rt8_private_num(c,"node",n->id);rt8_private_num(c,"pin",pin->id);rt8_private_num(c,"depth",c->force_depth);rt8_private_end_event(c);}
  if(state==RT8_NS_INDIRECT){
   Rt8Handle *next=rt8_private_acquire(c,n->slots[0].target,plan.views[0]);rt8_private_clear_prepared(c,n);n->state=RT8_NS_BUSY;rt8_private_drop_prepared(c,cursor);cursor=next;
  }else{
   Rt8Handle **owners=capture_owners(c,n,plan.count,plan.views);handoff(c,"capture_handoff",n,owners,plan.count,0);
   rt8_private_clear_prepared(c,n);n->state=RT8_NS_BUSY;
   if(rt8_private_event(c,"payload_cleared")){rt8_private_num(c,"node",n->id);rt8_private_end_event(c);}
   rt8_private_drop_prepared(c,cursor);
   if(state==RT8_NS_THUNK)cursor=callback(c,n,pin,owners,&plan);
   else{Rt8Handle *fn=owners[0],*arg=owners[1];rt8_private_free(c,owners);fn=rt8_private_force(c,fn);cursor=invoke(c,fn,arg,pin);}
  }
  /* Validate the raw cursor under THIS pending destination's principal
   * contract, never a single outer requested representation. */
  Rt8ValueFacts raw;rt8_private_value(c,cursor,MOVE_VALUE,&raw);rt8_private_publish_check(c,&n->origin,memo.resolved_type,&raw);
 }
 Rt8ValueFacts ready;rt8_private_value(c,cursor,MOVE_VALUE,&ready);Rt8Node *final=ready.node;
 const char *final_layout=layout(c,&ready),*memo_name=NULL;const Rt8Access *working=ready.access;
 Rt8Pending *next=NULL,*reverse_first=NULL;
 /* No graph memo edge may be published until this entire reverse pass passes.
  * Each iteration reserves both future forward visits and final plain writes. */
 for(Rt8Pending *p=last;p;){
  G(c,13,STATE,LENGTH,N,N,N,rt8_private_extent(c,p,RT8_MC_PENDING)==sizeof(*p));rt8_private_charge(c,sizeof(*p));
  G(c,13,STATE,EQUATION,N,N,N,p->next==next&&p->prepared==0&&p->memo_access==NULL&&p->memo_slot_id==N);
  if(next)G(c,13,STATE,EQUATION,N,N,N,next->previous==p);
  if(p->previous){G(c,13,STATE,LENGTH,N,N,N,rt8_private_extent(c,p->previous,RT8_MC_PENDING)==sizeof(*p));rt8_private_charge(c,sizeof(p->previous->next));G(c,13,STATE,EQUATION,N,N,N,p->previous->next==p);}
  Rt8Handle *pin=rt8_private_live(c,p->pin);
  G(c,13,OWNERSHIP,OWNER,N,N,N,pin->role==RT8_RC_PIN&&!pin->anchor&&!pin->home&&!pin->access&&!pin->fill_ticket&&!pin->loans&&pin->node==p->node);
  Rt8ValueFacts host,target;Rt8SlotFacts slot;rt8_private_node_access(c,p->node,p->requested,1,&host);
  G(c,13,STATE,STATE,14,host.site.id,5,pin->group==host.node->group&&host.node->state==RT8_NS_BUSY&&host.node->used==0&&host.node->capacity>=1);
  rt8_private_slot_spec(c,host.node->origin_site,host.node->origin.env,IR8_PACKET_SLOT_ROLE_MEMO,0,&slot);
  rt8_private_node_access(c,final,working,1,&target);rt8_private_publish_check(c,&host.node->origin,slot.resolved_type,&target);
  if(slot.row.relation==IR8_PACKET_RELATION_SAME)G(c,9,OWNERSHIP,EQUATION,16,slot.row.id,7,host.node->group==final->group);
  const Rt8Access *outer=rt8_private_transport(c,host.node,slot.resolved_type,p->requested,final,working);
  G(c,13,STATE,EQUATION,16,slot.row.id,2,memo_name==NULL||memo_name==slot.name);
  rt8_private_charge(c,UINT64_C(2048)+sizeof(*p)*8+sizeof(Rt8Slot)+sizeof(Rt8Handle));
  p->memo_access=working;p->memo_slot_id=slot.row.id;p->prepared=1;memo_name=slot.name;working=outer;
  reverse_first=p;next=p;p=p->previous;
 }
 G(c,13,STATE,EQUATION,N,N,N,reverse_first==first&&((first==NULL)==(last==NULL)));
 Rt8ValueFacts final_view;rt8_private_node_access(c,final,working,1,&final_view);
 G(c,3,TYPE,EQUATION,17,final_view.row.id,5,final_view.row.type==expected);
 rt8_private_guard_seen(c,8);rt8_private_charge(c,512);
 /* Operational suffix: no metadata readers, type/live/extent guards or guard
  * work reservations. RC/counter/event/OOM history remains genuinely fallible. */
 for(Rt8Pending *p=first;p;p=p->next){Rt8Node *n=p->node;
  rt8_private_publish_prepared(c,n,memo_name,final,p->memo_access);n->state=RT8_NS_MEMO;n->code=NULL;
  rt8_private_bump(c,&c->report.memo_writes);
  if(n->group==final->group)rt8_private_bump(c,&c->report.internal_memo_slots);else rt8_private_bump(c,&c->report.cross_group_memo_slots);
  if(rt8_private_event(c,"memo_publish")){rt8_private_num(c,"destination",n->id);rt8_private_num(c,"result",final->id);rt8_private_num(c,"pin",p->pin->id);rt8_private_num(c,"depth",c->force_depth);rt8_private_bool(c,"internal",n->group==final->group);rt8_private_end_event(c);}
 }
 for(Rt8Pending *p=first;p;){Rt8Pending *following=p->next;
  if(rt8_private_event(c,"update_unpin")){rt8_private_num(c,"node",p->node->id);rt8_private_num(c,"pin",p->pin->id);rt8_private_num(c,"depth",c->force_depth);rt8_private_end_event(c);}
  rt8_private_drop_prepared(c,p->pin);rt8_private_free(c,p);p=following;
 }
 cursor->access=working;
 if(rt8_private_event(c,"force_return")){rt8_private_num(c,"depth",c->force_depth);rt8_private_num(c,"result",final->id);rt8_private_num(c,"owner",cursor->id);rt8_private_num(c,"group",final->group->id);rt8_private_str(c,"layout",final_layout);rt8_private_end_event(c);}
 --c->force_depth;
 if(out){rt8_private_local(c,cursor);
  if(rt8_private_event(c,"ir_force_result")){rt8_private_num(c,"result",final->id);rt8_private_num(c,"group",cursor->group->id);rt8_private_str(c,"layout",final_layout);rt8_private_num(c,"owner",cursor->id);rt8_private_num(c,"frame",c->frame->id);rt8_private_str(c,"out",out);rt8_private_str(c,"source_variable",source);rt8_private_end_event(c);}}
 return cursor;
}
Rt8Handle *rt8_private_force(Rt8Context *c,Rt8Handle *h) { return force_engine(c,h,NULL,NULL); }
Rt8Handle *rt8_force(Rt8Context *c,Rt8Handle *h,const char *out,const char *source) {
 rt8_private_enter(c,RT8_OP_FORCE,1);rt8_private_label(c,out);rt8_private_label(c,source);
 if(c->frame->execution.kind==IR8_PACKET_ORIGIN_KIND_INSTANCE){
  Rt8ValueFacts value;rt8_private_value(c,h,MOVE_VALUE,&value);
  uint32_t kind=rt8_private_intrinsic_scalar_type(c,value.row.type);
  G(c,3,TYPE,EQUATION,17,value.row.id,5,value.execution.principal_type==value.row.type);
  G(c,2,TYPE,EQUATION,14,value.site.id,7,value.shape.kind==kind);
 }
 return force_engine(c,h,out,source);
}
Rt8Handle *rt8_return(Rt8Context *c,Rt8Handle *h) {
 Rt8ValueFacts value;rt8_private_enter(c,RT8_OP_RETURN,1);Rt8Frame *f=c->frame;
 G(c,23,OWNERSHIP,EQUATION,N,N,N,f&&(f->kind==RT8_FRAME_FUNCTION||f->kind==RT8_FRAME_THUNK)&&!f->returned&&f->home&&!f->active_intro);
 rt8_private_value(c,h,MOVE_VALUE,&value);
 G(c,23,OWNERSHIP,EQUATION,N,N,N,h->scope==f->id);
 rt8_private_authority(c,f->home);G(c,19,OWNERSHIP,DEPENDENT_LOAN,N,N,N,f->home->loans==0);
 rt8_private_result_check(c,f,&value);
 for(Rt8Handle *p=c->handles;p;){rt8_private_live(c,p);G(c,23,OWNERSHIP,EQUATION,N,N,N,p->scope!=f->id||p==h||p==f->home);rt8_private_charge(c,sizeof(p->next));p=p->next;}
 rt8_private_charge(c,256);Rt8Handle *result=rt8_private_escape_prepared(c,h);
 result->scope=0;f->returned_handle=result;f->returned=1;return result;
}
static void entry_preflight(Rt8Context *c) {
 Rt8Frame *f=c->frame;G(c,23,OWNERSHIP,EQUATION,N,N,N,f&&f->kind==RT8_FRAME_ENTRY&&!f->parent&&!f->home&&!f->code&&!f->returned&&!f->active_intro&&!c->finished);
 G(c,14,ORIGIN,TOKEN,N,N,N,f->execution.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE&&f->execution.capsule_id==0&&f->execution.creation_activation==0&&rt8_private_table_auth(c,4,f->execution.env)==0);
}
void rt8_finish_entry(Rt8Context *c) {
 rt8_private_enter(c,RT8_OP_FINISH,1);entry_preflight(c);
 G(c,20,OWNERSHIP,EQUATION,N,N,N,!c->handles&&!c->live_groups&&!c->live_nodes&&!c->live_owners);
 rt8_private_charge(c,1);c->finished=1;
}
void rt8_finish_scalar(Rt8Context *c,Rt8Handle *h) {
 Rt8ValueFacts value;rt8_private_enter(c,RT8_OP_FINISH_SCALAR,1);entry_preflight(c);rt8_private_value(c,h,MOVE_VALUE,&value);
 uint32_t kind=value.shape.kind;
 G(c,25,STATE,STATE,14,value.site.id,5,value.node->state==RT8_NS_READY&&value.node->storage_class==RT8_STORAGE_CLASS_SCALAR&&(kind==IR8_PACKET_SHAPE_KIND_I64||kind==IR8_PACKET_SHAPE_KIND_BOOL));
 G(c,20,OWNERSHIP,EQUATION,N,N,N,c->handles==h&&!h->next&&!h->previous);
 Ir8PacketType logical;Ir8PacketShapeBinding physical;
 rt8_private_table(c,1,value.row.type,&logical,sizeof(logical));rt8_private_table(c,7,value.shape.shape,&physical,sizeof(physical));
 G(c,3,TYPE,EQUATION,1,logical.id,2,logical.tag==IR8_PACKET_TYPE_TAG_CLOSED&&physical.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&logical.atom==physical.source_reference&&physical.kind==kind);
 rt8_private_charge(c,256);int64_t scalar=((Rt8ScalarNode *)value.node)->value;
 rt8_private_drop_prepared(c,h);
 /* Post-release operational emptiness, precharged above. No typed lookup. */
 if(c->handles||c->live_groups||c->live_nodes||c->live_owners)rt8_private_guard_fault(c,RT8_STATUS_OWNERSHIP,RT8_DETAIL_EQUATION,20,N,N,N);
 c->report.scalar_result_kind=kind;c->report.scalar_result=scalar;c->finished=1;
}
