/* Focused controls on a checked generated generic scalar-import program.
 * Callbacks and metadata remain genuine. Copied packet mutations precede
 * admission. Real-entry injections alter one capability, a copied preflight
 * fact, or a work limit; the immutable admitted packet is never patched.
 * Private-fact controls are test seams, not claims about a public C ABI. */
#include "rir8_runtime_internal.h"
#include "ir8_runtime_generated.h"
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define N IR8_PACKET_NULL
static Rt8Program program;
static Ir8PacketExpectedBindings expected;
static Ir8PacketWorkspace packet_workspace;
static Rt8BindingWorkspace binding_workspace;
static Ir8PacketProgramHeader header;
static Ir8PacketTypedHeader typed;
static const unsigned char *root;
static size_t length;
static unsigned failures,packet_cases;
static void need(int yes,const char *message) {
 if(!yes){fprintf(stderr,"generic capture guard: %s\n",message);exit(70);}
}
static void read_at(size_t offset,void *out,size_t size) {
 need(offset<=length&&size<=length-offset,"read range");memcpy(out,root+offset,size);
}
static Ir8PacketObjectDirectoryEntry object(uint32_t id) {
 Ir8PacketObjectDirectoryEntry d;need(id<header.directory_count,"object id");
 read_at(header.directory_offset+(size_t)id*sizeof(d),&d,sizeof(d));return d;
}
static size_t row(uint32_t obj,uint32_t index,size_t size) {
 Ir8PacketObjectDirectoryEntry d=object(obj);need(index<d.count&&size==d.element_bytes,"row shape");
 size_t off=(size_t)d.offset+(size_t)index*size;need(off<=length&&size<=length-off,"row range");return off;
}
static size_t table(uint32_t domain,uint32_t index,size_t size) {
 need(domain>=1&&domain<=20,"table domain");return row(typed.table[domain-1].object,index,size);
}
static const char *atom(uint32_t offset) {
 Ir8PacketObjectDirectoryEntry d=object(header.string_pool_object);need(offset<d.count,"atom offset");
 const char *p=(const char *)root+d.offset+offset;need(memchr(p,0,d.count-offset)!=NULL,"atom terminator");return p;
}
static int scalar_type(uint32_t id) {
 Ir8PacketType t;read_at(table(1,id,sizeof(t)),&t,sizeof(t));
 return t.tag==IR8_PACKET_TYPE_TAG_CLOSED&&(!strcmp(atom(t.atom),"#i64")||!strcmp(atom(t.atom),"#bool"));
}
static void mutate(const char *name,size_t offset,uint32_t value) {
 unsigned char *copy=malloc(length),*before=malloc(length);Ir8PacketReport r;
 need(copy&&before,"packet copy");need(offset<=length&&sizeof(value)<=length-offset,"mutation range");
 memcpy(copy,root,length);memcpy(copy+offset,&value,sizeof(value));memcpy(before,copy,length);
 uint32_t status=ir8_packet_validate(copy,length,&expected,&packet_workspace,&r);
 int ok=status!=0&&r.status==status&&!r.graph_executed&&memcmp(copy,before,length)==0;
 printf("{\"kind\":\"packet\",\"case\":\"%s\",\"status\":%"PRIu32",\"phase\":%"PRIu32",\"domain\":%"PRIu32",\"row\":%"PRIu32",\"field\":%"PRIu32",\"detail\":%"PRIu32",\"work\":%"PRIu64",\"ok\":%d}\n",name,status,r.phase,r.domain,r.row,r.field,r.detail,r.work_used,ok);
 if(!ok)++failures;
 ++packet_cases;free(before);free(copy);
}
#define MUT(name,base,kind,field,value) mutate(name,(base)+offsetof(kind,field),(value))
static void packet_controls(void) {
 unsigned captures=0,identities=0;
 for(uint32_t i=0;i<typed.table[15].count;++i){Ir8PacketSlot s;Ir8PacketSite site;
  size_t off=table(16,i,sizeof(s));read_at(off,&s,sizeof(s));read_at(table(14,s.site,sizeof(site)),&site,sizeof(site));
  if(s.role_tag!=IR8_PACKET_SLOT_ROLE_CAPTURE||site.scope==N||!scalar_type(s.type))continue;
  ++captures;
  MUT("capture-role",off,Ir8PacketSlot,role_tag,IR8_PACKET_SLOT_ROLE_MEMO);
  MUT("capture-name",off,Ir8PacketSlot,role_name,N);
  MUT("capture-type",off,Ir8PacketSlot,type,typed.table[0].count);
  MUT("capture-site",off,Ir8PacketSlot,site,typed.table[13].count);
 }
 for(uint32_t i=0;i<typed.table[19].count;++i){Ir8PacketTransport t;Ir8PacketAccess a;
  size_t off=table(20,i,sizeof(t));read_at(off,&t,sizeof(t));read_at(table(17,t.source_access,sizeof(a)),&a,sizeof(a));
  if(t.projection_env!=N||a.origin_env!=0||a.mode!=IR8_PACKET_ACCESS_MODE_MONO||!scalar_type(a.type))continue;
  ++identities;
  MUT("identity-kind",off,Ir8PacketTransport,kind,IR8_PACKET_TRANSPORT_KIND_PROJECT);
  MUT("identity-result",off,Ir8PacketTransport,result_access,typed.table[16].count);
  MUT("identity-projection",off,Ir8PacketTransport,projection_env,0);
 }
 need(captures>0&&identities>0,"generic scalar capture and concrete identity rows required");
}
enum Mode {HEALTHY,FOREIGN_ACCESS,CONCRETE_CAPSULE,INSTANCE_ORIGIN,WRONG_ROLE,WRONG_TYPE,
 WRONG_SHAPE,OLD_PUBLISH,CAPTURE_WORK,FOREIGN_REQUEST,BAD_CAPTURE_INDEX,TRANSPORT_WORK,
 ALIAS_LEAK,ALIAS_BALANCED,AFTER_RETAIN_WORK,MODE_COUNT};
static const char *const names[]={"healthy","foreign-access","concrete-capsule","instance-origin",
 "wrong-role","wrong-type","wrong-shape","noncapture-publish","capture-work","foreign-request",
 "bad-capture-index","transport-work","alias-leak","alias-balanced","after-retain-work"};
static enum Mode mode;
static unsigned injected,publish_calls,publish_real,transport_calls,transport_real,imports,alias_checks,pending_seen,old_publish_calls;
static Rt8Handle *parent_owner,*watched;
static Rt8Node *watched_node;
static const Rt8Access *before_access;
static uint32_t before_state;
static uint64_t before_nodes;
static Ir8PacketAccess foreign_access;
Rt8Handle *__real_rt8_retain(Rt8Context *,Rt8Handle *);
Rt8Handle *__real_rt8_closure(Rt8Context *,Rt8Handle *,const Rt8Site *,const Rt8Code *,Rt8Handle *const *,const char *);
Rt8Handle *__real_rt8_generic_seal(Rt8Context *,Rt8GenericScope *,Rt8Handle *,const char *);
void __real_rt8_private_capture_publish(Rt8Context *,const Rt8Origin *,const Rt8SlotFacts *,const Rt8ValueFacts *);
const Rt8Access *__real_rt8_private_capture_transport(Rt8Context *,Rt8Node *,const Rt8Access *,size_t);
static void watch(Rt8Context *c,Rt8Handle *h,Rt8Node *n,const Rt8Access *a) {
 watched=h;watched_node=n;before_access=a;before_state=n->state;before_nodes=c->report.nodes_allocated;
}
Rt8Handle *__wrap_rt8_retain(Rt8Context *c,Rt8Handle *h) {
 int importing=c->frame&&c->frame->active_intro&&h->node&&
  h->node->origin.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE&&h->access->mode==IR8_PACKET_ACCESS_MODE_MONO&&scalar_type(h->access->type);
 uint64_t prior=c->next_handle;Rt8Handle *result=__real_rt8_retain(c,h);
 if(importing){++imports;parent_owner=h;
  need(result!=h&&result->id>prior&&result->node==h->node&&result->access==h->access&&result->anchor==NULL,"independent import owner");
  ++alias_checks;
  if(mode==AFTER_RETAIN_WORK&&!injected){injected=1;watch(c,result,result->node,result->access);c->guard_work.limit=c->guard_work.used;}}
 return result;
}
Rt8Handle *__wrap_rt8_closure(Rt8Context *c,Rt8Handle *a,const Rt8Site *site,const Rt8Code *code,Rt8Handle *const *values,const char *out) {
 if(c->frame->active_intro&&values&&!injected&&mode>=FOREIGN_ACCESS&&mode<=INSTANCE_ORIGIN){
  Ir8PacketCodeTyping ct;read_at(table(5,code->code_id,sizeof(ct)),&ct,sizeof(ct));
  for(uint32_t i=0;i<ct.captures.count;++i){Rt8Handle *h=values[i];
   if(!h->node||h->node->origin.kind!=IR8_PACKET_ORIGIN_KIND_CONCRETE||!scalar_type(h->access->type))continue;
   injected=1;
   if(mode==FOREIGN_ACCESS){foreign_access=*h->access;h->access=&foreign_access;}
   if(mode==CONCRETE_CAPSULE)h->node->origin.capsule_id=1;
   if(mode==INSTANCE_ORIGIN)h->node->origin.kind=IR8_PACKET_ORIGIN_KIND_INSTANCE;
   watch(c,h,h->node,h->access);break;
  }
 }
 return __real_rt8_closure(c,a,site,code,values,out);
}
void __wrap_rt8_private_capture_publish(Rt8Context *c,const Rt8Origin *host,const Rt8SlotFacts *slot,const Rt8ValueFacts *target) {
 ++publish_calls;Rt8SlotFacts s=*slot;Rt8ValueFacts v=*target;
 int importing=host->kind==IR8_PACKET_ORIGIN_KIND_GENERIC&&target->node->origin.kind==IR8_PACKET_ORIGIN_KIND_CONCRETE;
 if(importing){if(target->node->state==RT8_NS_APPLICATION||target->node->state==RT8_NS_THUNK)++pending_seen;
  if(!injected&&mode>=WRONG_ROLE&&mode<=CAPTURE_WORK){injected=1;watch(c,NULL,target->node,target->access);
   if(mode==WRONG_ROLE)s.row.role_tag=IR8_PACKET_SLOT_ROLE_MEMO;
   if(mode==WRONG_TYPE)s.resolved_type=N;
   if(mode==WRONG_SHAPE)v.shape.kind=IR8_PACKET_SHAPE_KIND_REPEAT;
   if(mode==CAPTURE_WORK)c->guard_work.limit=c->guard_work.used;
   if(mode==OLD_PUBLISH){++old_publish_calls;rt8_private_publish_check(c,host,slot->resolved_type,target);need(0,"old noncapture rule unexpectedly admitted concrete scalar");}
  }
 }
 uint64_t nodes=c->report.nodes_allocated;uint32_t state=target->node->state;const Rt8Access *access=target->access;
 ++publish_real;__real_rt8_private_capture_publish(c,host,&s,&v);
 need(c->report.nodes_allocated==nodes&&target->node->state==state&&target->access==access,"capture preflight changed node/readiness/Access");
}
const Rt8Access *__wrap_rt8_private_capture_transport(Rt8Context *c,Rt8Node *host,const Rt8Access *request,size_t index) {
 ++transport_calls;need(index<host->used,"known valid generated capture index");
 Rt8Slot original=host->slots[index];uint32_t state=original.target->state;
 if(!injected&&mode>=FOREIGN_REQUEST&&mode<=TRANSPORT_WORK){injected=1;watch(c,NULL,original.target,original.access);
  if(mode==FOREIGN_REQUEST){foreign_access=*request;request=&foreign_access;}
  if(mode==BAD_CAPTURE_INDEX)index=host->used;
  if(mode==TRANSPORT_WORK)c->guard_work.limit=c->guard_work.used;
 }
 ++transport_real;const Rt8Access *result=__real_rt8_private_capture_transport(c,host,request,index);
 need(result==original.access&&host->slots[index].target==original.target&&original.target->state==state,"capture identity transport changed target/view/readiness");return result;
}
Rt8Handle *__wrap_rt8_generic_seal(Rt8Context *c,Rt8GenericScope *scope,Rt8Handle *h,const char *out) {
 if(!injected&&(mode==ALIAS_LEAK||mode==ALIAS_BALANCED)){
  need(parent_owner!=NULL,"import parent recorded");injected=1;
  Rt8Handle *extra=__real_rt8_retain(c,parent_owner);
  need(extra!=parent_owner&&extra->node==parent_owner->node&&extra->access==parent_owner->access&&extra->id>scope->handle_watermark,"post-begin alias preserves concrete owner");
  if(mode==ALIAS_BALANCED){Rt8Handle *second=__real_rt8_retain(c,parent_owner);
   need(second!=extra&&second->node==extra->node&&second->access==extra->access,"distinct aliases to same target");
   rt8_drop(c,second);rt8_drop(c,extra);
  }else watch(c,h,h->node,h->access);
 }
 return __real_rt8_generic_seal(c,scope,h,out);
}
static void runtime_control(enum Mode which) {
 mode=which;injected=publish_calls=publish_real=transport_calls=transport_real=imports=alias_checks=pending_seen=old_publish_calls=0;
 parent_owner=watched=NULL;watched_node=NULL;before_access=NULL;before_state=0;before_nodes=0;
 Rt8Context *context=NULL;Rt8Options options={UINT64_C(1000000),UINT64_C(100000),0};
 Rt8Report report={0},before={0},again={0};Rt8DestroyReport destroyed={0};
 need(rt8_session_open(&program,&expected,&binding_workspace,&options,&context,&report)==0,"fresh real session");
 int rc=rt8_session_step(context,&report);int healthy=which==HEALTHY||which==ALIAS_BALANCED;
 int ok=imports>0&&alias_checks==imports&&publish_calls==publish_real+old_publish_calls&&transport_calls==transport_real;
 if(healthy){ok=ok&&rc==0&&!report.fault&&publish_calls>0&&transport_calls>0;
  need(rt8_session_close(&context,&report)==0&&context==NULL,"healthy close");
  ok=ok&&!report.memory.live_bytes&&!report.memory.live_blocks;
  for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&!report.categories[i].live_bytes&&!report.categories[i].live_blocks;
 }else{
  ok=ok&&rc==2&&injected==1&&report.fault==RT8_FAULT_TYPED_GUARD&&watched_node&&watched_node->state==before_state;
  if(watched)ok=ok&&watched->access==before_access;
  if(which!=AFTER_RETAIN_WORK)ok=ok&&report.nodes_allocated==before_nodes;
  if(which==CAPTURE_WORK||which==TRANSPORT_WORK||which==AFTER_RETAIN_WORK)
   ok=ok&&report.location.status==RT8_STATUS_WORK_LIMIT&&report.location.detail==RT8_DETAIL_WORK_EXHAUSTED;
  else if(which==FOREIGN_ACCESS||which==FOREIGN_REQUEST)ok=ok&&report.location.status==RT8_STATUS_REFERENCE&&report.location.detail==RT8_DETAIL_UNREGISTERED;
  else if(which==ALIAS_LEAK)ok=ok&&report.location.status==RT8_STATUS_OWNERSHIP&&report.location.guard_index==20;
  else if(which==CONCRETE_CAPSULE||which==INSTANCE_ORIGIN||which==OLD_PUBLISH||which==WRONG_ROLE)ok=ok&&report.location.status==RT8_STATUS_ORIGIN;
  else if(which==BAD_CAPTURE_INDEX)ok=ok&&report.location.status==RT8_STATUS_ORIGIN&&report.location.detail==RT8_DETAIL_COUNT;
  else if(which==WRONG_TYPE)ok=ok&&report.location.status==RT8_STATUS_TYPE;
  else if(which==WRONG_SHAPE)ok=ok&&report.location.status==RT8_STATUS_STATE;
  need(rt8_session_snapshot(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"retained fault snapshot");
  need(rt8_session_step(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"poison refuses resume");
  Rt8Context *same=context;need(rt8_session_close(&context,&again)==2&&context==same,"default close retains fault");
  need(rt8_session_destroy_terminal(&context,&before,&destroyed)==0&&context==NULL,"explicit terminal surrender");
  ok=ok&&memcmp(&before,&report,sizeof(report))==0&&destroyed.retired_bytes==report.memory.live_bytes&&destroyed.retired_blocks==report.memory.live_blocks&&!destroyed.totals_overflow;
  for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&destroyed.category_bytes[i]==report.categories[i].live_bytes&&destroyed.category_blocks[i]==report.categories[i].live_blocks;
 }
 printf("{\"kind\":\"runtime\",\"case\":\"%s\",\"rc\":%d,\"fault\":%"PRIu32",\"status\":%"PRIu32",\"detail\":%"PRIu32",\"guard\":%"PRIu32",\"imports\":%u,\"alias_checks\":%u,\"publish_calls\":%u,\"publish_real\":%u,\"old_publish_calls\":%u,\"transport_calls\":%u,\"transport_real\":%u,\"pending_seen\":%u,\"work\":%"PRIu64",\"scalar_kind\":%"PRIu32",\"scalar\":%"PRId64",\"live_bytes\":%"PRIu64",\"retired_bytes\":%"PRIu64",\"ok\":%d}\n",names[which],rc,report.fault,report.location.status,report.location.detail,report.location.guard_index,imports,alias_checks,publish_calls,publish_real,old_publish_calls,transport_calls,transport_real,pending_seen,report.guard_work_used,report.scalar_result_kind,report.scalar_result,report.memory.live_bytes,destroyed.retired_bytes,ok);
 if(!ok)++failures;
}
int main(void) {
 program=ir8_runtime_generated_program();root=program.packet;length=program.packet_bytes;
 need(length<=IR8_PACKET_MAX_BYTES,"packet cap");memcpy(&expected,ir8_runtime_generated_expected_bindings(),sizeof(expected));
 Ir8PacketReport report;need(ir8_packet_validate(root,length,&expected,&packet_workspace,&report)==0,"untouched packet admission");
 read_at(0,&header,sizeof(header));Ir8PacketObjectDirectoryEntry d=object(header.typed_header_object);read_at(d.offset,&typed,sizeof(typed));
 packet_controls();for(unsigned i=0;i<MODE_COUNT;++i)runtime_control((enum Mode)i);
 printf("{\"summary\":true,\"packet_cases\":%u,\"runtime_cases\":%u,\"failures\":%u}\n",packet_cases,(unsigned)MODE_COUNT,failures);
 need(fflush(stdout)==0&&!ferror(stdout),"stdout");return failures?1:0;
}
