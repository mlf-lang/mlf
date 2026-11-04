/* Real-session controls for scoped scalar operations. Generated callbacks and
 * admitted metadata remain unchanged. Interposition changes a live frame or a
 * copied immediate value fact, never packet bytes or callback implementations.
 * These private test seams do not promise hostile-pointer recovery. */
#include "rir8_runtime_internal.h"
#include "ir8_runtime_generated.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define N IR8_PACKET_NULL
static Rt8Program program;
static Ir8PacketExpectedBindings expected;
static Rt8BindingWorkspace workspace;
static unsigned failures;
static void need(int condition,const char *message) {
 if(!condition){fprintf(stderr,"Instance scalar guard: %s\n",message);exit(70);}
}
enum Mode {HEALTHY,GENERIC_FORCE,GENERIC_PRIM2,GENERIC_SELECT,NEUTRAL_FRAME,
 FOREIGN_ENV,NEUTRAL_ENV,FOREIGN_CODE,FOREIGN_EXECUTION,ZERO_CAPSULE,FUTURE_CAPSULE,
 WRONG_ACTIVATION,ACTIVE_INTRO,WRONG_KIND,WRONG_RESULT,WRONG_IDENTITY,WRONG_HOME,
 ENTRY_WORK,FORCE_ARROW,FORCE_PRINCIPAL,FORCE_SHAPE,FORCE_TYPE_WORK,MODE_COUNT};
static const char *const names[]={"healthy","generic-force","generic-prim2","generic-select",
 "neutral-frame","foreign-env","neutral-env","foreign-code","foreign-execution","zero-capsule",
 "future-capsule","wrong-activation","active-intro","wrong-kind","wrong-result","wrong-identity",
 "wrong-home","entry-work","force-arrow","force-principal","force-shape","force-type-work"};
static enum Mode mode;
static unsigned injected,enter_calls,enter_real,manual_enters,force_calls,force_real;
static unsigned scalar_calls,scalar_real,instance_force,instance_prim2,instance_select,in_force;
static Rt8Handle *watched;
static Rt8Node *watched_node;
static const Rt8Access *watched_access;
static uint32_t watched_state;
static uint64_t before_nodes,before_memos,before_allocations,before_frees;
static Ir8PacketEnv foreign_env;
static Rt8Code foreign_code;
static Ir8PacketCodeExecution foreign_execution;
void __real_rt8_private_enter(Rt8Context *,Rt8Operation,int);
void __real_rt8_private_value(Rt8Context *,Rt8Handle *,uint32_t,Rt8ValueFacts *);
uint32_t __real_rt8_private_intrinsic_scalar_type(Rt8Context *,uint32_t);
Rt8Handle *__real_rt8_force(Rt8Context *,Rt8Handle *,const char *,const char *);
Rt8Handle *__real_rt8_generic_seal(Rt8Context *,Rt8GenericScope *,Rt8Handle *,const char *);
static int effect(Rt8Operation op) {
 return op==RT8_OP_FORCE||op==RT8_OP_PRIM2||op==RT8_OP_SELECT;
}
static void watch(Rt8Context *c,Rt8Handle *h) {
 watched=h;watched_node=h?h->node:c->frame->home->anchor->node;
 need(watched_node!=NULL,"known valid watched node");
 watched_access=h?h->access:NULL;watched_state=watched_node->state;
 before_nodes=c->report.nodes_allocated;before_memos=c->report.memo_writes;
 before_allocations=c->report.memory.allocations;before_frees=c->report.memory.frees;
}
static const Rt8Env *neutral(Rt8Context *c) {
 Ir8PacketEnv env;Ir8PacketScheme scheme;
 uint32_t eid=rt8_private_table_auth(c,4,c->frame->execution.env);
 rt8_private_table(c,4,eid,&env,sizeof(env));rt8_private_table(c,3,env.scheme,&scheme,sizeof(scheme));
 return rt8_private_table_ref(c,4,scheme.neutral_env);
}
void __wrap_rt8_private_enter(Rt8Context *c,Rt8Operation op,int tick) {
 ++enter_calls;
 if(c&&c->frame&&c->frame->execution.kind==IR8_PACKET_ORIGIN_KIND_INSTANCE&&effect(op)){
  if(op==RT8_OP_FORCE)++instance_force;
  if(op==RT8_OP_PRIM2)++instance_prim2;
  if(op==RT8_OP_SELECT)++instance_select;
  if(!injected&&mode>=NEUTRAL_FRAME&&mode<=ENTRY_WORK){
   Rt8Frame *f=c->frame;
   if(!in_force)watch(c,NULL);
   injected=1;
   switch(mode){
   case NEUTRAL_FRAME:f->execution.kind=IR8_PACKET_ORIGIN_KIND_GENERIC;break;
   case FOREIGN_ENV:foreign_env=*f->execution.env;f->execution.env=&foreign_env;break;
   case NEUTRAL_ENV:f->execution.env=neutral(c);break;
   case FOREIGN_CODE:foreign_code=*f->code;f->code=&foreign_code;break;
   case FOREIGN_EXECUTION:foreign_execution=*f->code_execution;f->code_execution=&foreign_execution;break;
   case ZERO_CAPSULE:f->execution.capsule_id=0;break;
   case FUTURE_CAPSULE:need(c->next_capsule<UINT64_MAX,"capsule increment");f->execution.capsule_id=c->next_capsule+1;break;
   case WRONG_ACTIVATION:f->execution.creation_activation=0;break;
   case ACTIVE_INTRO:f->active_intro=rt8_private_table_ref(c,18,0);break;
   case WRONG_KIND:f->kind=RT8_FRAME_ENTRY;break;
   case WRONG_RESULT:f->expected_result_type=N;break;
   case WRONG_IDENTITY:f->result_identity=f->result_identity==N?0:N;break;
   case WRONG_HOME:f->home->scope=0;break;
   case ENTRY_WORK:c->guard_work.limit=c->guard_work.used;break;
   default:need(0,"frame control mode");
   }
  }
 }
 ++enter_real;__real_rt8_private_enter(c,op,tick);
}
Rt8Handle *__wrap_rt8_generic_seal(Rt8Context *c,Rt8GenericScope *scope,Rt8Handle *h,const char *out) {
 if(!injected&&mode>=GENERIC_FORCE&&mode<=GENERIC_SELECT){
  need(c->frame->active_intro&&c->frame->execution.kind==IR8_PACKET_ORIGIN_KIND_GENERIC,"real neutral introduction");
  watch(c,h);injected=1;++manual_enters;
  Rt8Operation op=mode==GENERIC_FORCE?RT8_OP_FORCE:mode==GENERIC_PRIM2?RT8_OP_PRIM2:RT8_OP_SELECT;
  __real_rt8_private_enter(c,op,1);need(0,"neutral effect unexpectedly permitted");
 }
 return __real_rt8_generic_seal(c,scope,h,out);
}
Rt8Handle *__wrap_rt8_force(Rt8Context *c,Rt8Handle *h,const char *out,const char *source) {
 ++force_calls;
 int target=c->frame->execution.kind==IR8_PACKET_ORIGIN_KIND_INSTANCE;
 if(target&&!injected){
  if(mode==FORCE_ARROW){
   Rt8Handle *found=NULL;
   for(Rt8Handle *p=c->handles;p;p=p->next){
    if(p->role!=RT8_RC_OWNER||p->anchor||p->home||p->fill_ticket||p->loans||!p->node||!p->access)continue;
    if(p->node->state==RT8_NS_CLOSURE&&p->access->mode==IR8_PACKET_ACCESS_MODE_MONO){found=p;break;}
   }
   need(found!=NULL,"actual live callable owner for scalar Force rejection");h=found;injected=1;
  }
  watch(c,h);
 }
 ++force_real;if(target)++in_force;
 Rt8Handle *result=__real_rt8_force(c,h,out,source);if(target)--in_force;return result;
}
void __wrap_rt8_private_value(Rt8Context *c,Rt8Handle *h,uint32_t flags,Rt8ValueFacts *out) {
 __real_rt8_private_value(c,h,flags,out);
 if(in_force&&!injected&&c->frame->execution.kind==IR8_PACKET_ORIGIN_KIND_INSTANCE&&
    (mode==FORCE_PRINCIPAL||mode==FORCE_SHAPE)){
  need(h==watched,"first public Force operand preflight");injected=1;
  if(mode==FORCE_PRINCIPAL)out->execution.principal_type=N;
  else out->shape.kind=IR8_PACKET_SHAPE_KIND_REPEAT;
 }
}
uint32_t __wrap_rt8_private_intrinsic_scalar_type(Rt8Context *c,uint32_t id) {
 ++scalar_calls;
 if(in_force&&!injected&&mode==FORCE_TYPE_WORK){injected=1;c->guard_work.limit=c->guard_work.used;}
 ++scalar_real;return __real_rt8_private_intrinsic_scalar_type(c,id);
}
static int fault_class(const Rt8Report *r) {
 if(mode==ENTRY_WORK||mode==FORCE_TYPE_WORK)
  return r->location.status==RT8_STATUS_WORK_LIMIT&&r->location.detail==RT8_DETAIL_WORK_EXHAUSTED;
 if(mode==FOREIGN_ENV||mode==FOREIGN_CODE)
  return r->location.status==RT8_STATUS_REFERENCE&&r->location.detail==RT8_DETAIL_UNREGISTERED;
 if(mode==GENERIC_FORCE||mode==GENERIC_PRIM2||mode==GENERIC_SELECT||mode==NEUTRAL_FRAME||mode==ACTIVE_INTRO||mode==WRONG_KIND)
  return r->location.status==RT8_STATUS_STATE&&r->location.guard_index==25;
 if(mode==WRONG_HOME)return r->location.status==RT8_STATUS_OWNERSHIP&&r->location.guard_index==17;
 if(mode==FORCE_ARROW||mode==FORCE_PRINCIPAL)return r->location.status==RT8_STATUS_TYPE&&r->location.guard_index==3;
 if(mode==FORCE_SHAPE)return r->location.status==RT8_STATUS_TYPE&&r->location.guard_index==2;
 if(mode==WRONG_IDENTITY)return r->location.status==RT8_STATUS_TYPE&&r->location.guard_index==11;
 return r->location.status==RT8_STATUS_ORIGIN;
}
static void runtime_control(enum Mode which) {
 mode=which;injected=enter_calls=enter_real=manual_enters=force_calls=force_real=scalar_calls=scalar_real=0;
 instance_force=instance_prim2=instance_select=in_force=0;watched=NULL;watched_node=NULL;
 watched_access=NULL;watched_state=0;before_nodes=before_memos=before_allocations=before_frees=0;
 Rt8Context *context=NULL;Rt8Options options={UINT64_C(1000000),UINT64_C(100000),0};
 Rt8Report report={0},before={0},again={0};Rt8DestroyReport destroyed={0};
 need(rt8_session_open(&program,&expected,&workspace,&options,&context,&report)==0,"fresh real session");
 int rc=rt8_session_step(context,&report);
 int ok=enter_calls==enter_real&&force_calls==force_real&&scalar_calls==scalar_real;
 if(which==HEALTHY){
  ok=ok&&rc==0&&!report.fault&&instance_force>0&&(instance_prim2>0||instance_select>0)&&scalar_calls>0;
  need(rt8_session_close(&context,&report)==0&&context==NULL,"healthy close");
  ok=ok&&!report.memory.live_bytes&&!report.memory.live_blocks;
  for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&!report.categories[i].live_bytes&&!report.categories[i].live_blocks;
 }else{
  ok=ok&&rc==2&&injected==1&&report.fault==RT8_FAULT_TYPED_GUARD&&fault_class(&report)&&
   watched_node&&watched_node->state==watched_state&&report.nodes_allocated==before_nodes&&
   report.memo_writes==before_memos&&report.memory.allocations==before_allocations&&report.memory.frees==before_frees;
  if(watched)ok=ok&&watched->access==watched_access;
  need(rt8_session_snapshot(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"fault snapshot");
  need(rt8_session_step(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"poison refuses resume");
  Rt8Context *same=context;need(rt8_session_close(&context,&again)==2&&context==same,"default retains fault");
  need(rt8_session_destroy_terminal(&context,&before,&destroyed)==0&&context==NULL,"explicit terminal surrender");
  ok=ok&&memcmp(&before,&report,sizeof(report))==0&&destroyed.retired_bytes==report.memory.live_bytes&&
   destroyed.retired_blocks==report.memory.live_blocks&&!destroyed.totals_overflow;
  for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&destroyed.category_bytes[i]==report.categories[i].live_bytes&&destroyed.category_blocks[i]==report.categories[i].live_blocks;
 }
 printf("{\"case\":\"%s\",\"rc\":%d,\"fault\":%"PRIu32",\"status\":%"PRIu32",\"detail\":%"PRIu32",\"guard\":%"PRIu32",\"work\":%"PRIu64",\"enter_calls\":%u,\"enter_real\":%u,\"manual_enters\":%u,\"force_calls\":%u,\"force_real\":%u,\"scalar_calls\":%u,\"scalar_real\":%u,\"instance_force\":%u,\"instance_prim2\":%u,\"instance_select\":%u,\"scalar_kind\":%"PRIu32",\"scalar\":%"PRId64",\"live_blocks\":%"PRIu64",\"live_bytes\":%"PRIu64",\"retired_blocks\":%"PRIu64",\"retired_bytes\":%"PRIu64",\"ok\":%d}\n",
 names[which],rc,report.fault,report.location.status,report.location.detail,report.location.guard_index,report.guard_work_used,
 enter_calls,enter_real,manual_enters,force_calls,force_real,scalar_calls,scalar_real,instance_force,instance_prim2,instance_select,
 report.scalar_result_kind,report.scalar_result,report.memory.live_blocks,report.memory.live_bytes,destroyed.retired_blocks,destroyed.retired_bytes,ok);
 if(!ok)++failures;
}
int main(void) {
 program=ir8_runtime_generated_program();memcpy(&expected,ir8_runtime_generated_expected_bindings(),sizeof(expected));
 for(unsigned i=0;i<MODE_COUNT;++i)runtime_control((enum Mode)i);
 printf("{\"summary\":true,\"runtime_cases\":%u,\"failures\":%u}\n",(unsigned)MODE_COUNT,failures);
 need(fflush(stdout)==0&&!ferror(stdout),"stdout");return failures?1:0;
}
