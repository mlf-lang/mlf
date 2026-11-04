/* Focused checks on an actual generated program with nominal shared uses.
 * Packet forgeries use copies BEFORE admission. Runtime faults alter only an
 * input capability or a test work budget at a real instantiate call; immutable
 * admitted metadata is never patched. Every interposed call invokes __real once.
 * This is not general source admission or an exhaustive runtime guard proof. */
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
static unsigned failures, packet_cases;
static void need(int yes,const char *message) {
    if(!yes){fprintf(stderr,"nominal argument guard: %s\n",message);exit(70);}
}
static void read_at(size_t offset,void *out,size_t size) {
    need(offset<=length&&size<=length-offset,"read range");memcpy(out,root+offset,size);
}
static Ir8PacketObjectDirectoryEntry object(uint32_t id) {
    Ir8PacketObjectDirectoryEntry d;
    need(id<header.directory_count,"object id");
    read_at(header.directory_offset+(size_t)id*sizeof(d),&d,sizeof(d));return d;
}
static size_t row(uint32_t object_id,uint32_t index,size_t size) {
    Ir8PacketObjectDirectoryEntry d=object(object_id);
    need(index<d.count&&size==d.element_bytes,"row index/size");
    size_t offset=(size_t)d.offset+(size_t)index*size;
    need(offset<=length&&size<=length-offset,"row range");return offset;
}
static size_t table(uint32_t domain,uint32_t index,size_t size) {
    need(domain>=1&&domain<=20,"table domain");return row(typed.table[domain-1].object,index,size);
}
static size_t descriptor(uint32_t domain,uint32_t index,size_t size) {
    need(domain>=1&&domain<=6,"descriptor domain");return row(typed.descriptor[domain-1].object,index,size);
}
static const char *atom(uint32_t offset) {
    Ir8PacketObjectDirectoryEntry pool=object(header.string_pool_object);
    need(offset<pool.count,"string offset");
    const char *p=(const char *)root+pool.offset+offset;
    need(memchr(p,0,pool.count-offset)!=NULL,"string end");return p;
}
static Ir8PacketType type_at(uint32_t id) {
    Ir8PacketType t;read_at(table(1,id,sizeof(t)),&t,sizeof(t));return t;
}
static int nominal(uint32_t id) {
    Ir8PacketType t=type_at(id);
    return t.tag==IR8_PACKET_TYPE_TAG_CLOSED&&strcmp(atom(t.atom),"#i64")&&strcmp(atom(t.atom),"#bool");
}
static void mutation(const char *name,uint32_t type,size_t offset,uint32_t value) {
    unsigned char *copy=malloc(length),*before=malloc(length);Ir8PacketReport r;
    need(copy&&before,"packet copy allocation");need(offset<=length&&sizeof(value)<=length-offset,"write range");
    memcpy(copy,root,length);memcpy(copy+offset,&value,sizeof(value));memcpy(before,copy,length);
    uint32_t status=ir8_packet_validate(copy,length,&expected,&packet_workspace,&r);
    int ok=status!=0&&r.status==status&&r.graph_executed==0&&memcmp(copy,before,length)==0;
    printf("{\"kind\":\"packet\",\"case\":\"%s\",\"type\":%"PRIu32",\"status\":%"PRIu32",\"phase\":%"PRIu32",\"domain\":%"PRIu32",\"row\":%"PRIu32",\"field\":%"PRIu32",\"detail\":%"PRIu32",\"work\":%"PRIu64",\"ok\":%d}\n",
        name,type,status,r.phase,r.domain,r.row,r.field,r.detail,r.work_used,ok);
    if(!ok)++failures;
    ++packet_cases;free(before);free(copy);
}
#define MUT(name,tid,base,kind,field,value) mutation(name,tid,(base)+offsetof(kind,field),(value))
static void packet_controls(void) {
    unsigned char seen[4096]={0};uint32_t scalar=N,arrow=N,rigid=N,nominals=0;
    need(typed.table[0].count<=sizeof(seen),"finite type census");
    for(uint32_t i=0;i<typed.table[0].count;++i){Ir8PacketType t=type_at(i);
        if(t.tag==IR8_PACKET_TYPE_TAG_CLOSED&&!strcmp(atom(t.atom),"#i64"))scalar=i;
        if(t.tag==IR8_PACKET_TYPE_TAG_ARROW)arrow=i;
        if(t.tag==IR8_PACKET_TYPE_TAG_RIGID)rigid=i;}
    need(scalar!=N&&arrow!=N&&rigid!=N,"scalar/arrow/rigid controls present");
    for(uint32_t i=0;i<typed.table[3].count;++i){Ir8PacketEnv env;
        size_t eo=table(4,i,sizeof(env));read_at(eo,&env,sizeof(env));
        if(env.mode!=IR8_PACKET_ENV_MODE_CLOSED)continue;
        for(uint32_t j=0;j<env.arguments.count;++j){Ir8PacketTypeRef tr;
            size_t vo=row(env.arguments.object,j,sizeof(tr));read_at(vo,&tr,sizeof(tr));
            if(!nominal(tr.row))continue;
            mutation("vector-foreign",tr.row,vo,typed.table[0].count);
            mutation("vector-arrow",tr.row,vo,arrow);mutation("vector-rigid",tr.row,vo,rigid);
            mutation("vector-wrong-scalar",tr.row,vo,scalar);
            MUT("partial-env",tr.row,eo,Ir8PacketEnv,arguments.count,env.arguments.count-1);
            if(seen[tr.row])continue;
            seen[tr.row]=1;++nominals;
            Ir8PacketType t=type_at(tr.row);uint32_t sid=N;
            for(uint32_t k=0;k<typed.table[6].count;++k){Ir8PacketShapeBinding s;
                read_at(table(7,k,sizeof(s)),&s,sizeof(s));
                if(s.source_tag==IR8_PACKET_SHAPE_SOURCE_LEGACY&&s.source_reference==t.atom)sid=k;}
            need(sid!=N,"nominal shape exists");
            Ir8PacketShapeBinding s;size_t sb=table(7,sid,sizeof(s));read_at(sb,&s,sizeof(s));
            uint32_t other=sid?0:1;need(other<typed.table[6].count,"distinct shape identity");
            size_t st=table(8,sid,sizeof(Ir8PacketShapeTyping)),rp=table(9,sid,sizeof(Ir8PacketRepresentation));
            size_t sp=descriptor(1,sid,sizeof(Ir8PacketShapeSpec));
            MUT("binding-source",tr.row,sb,Ir8PacketShapeBinding,source_reference,type_at(scalar).atom);
            MUT("binding-source-type",tr.row,sb,Ir8PacketShapeBinding,source_type,tr.row);
            MUT("binding-kind",tr.row,sb,Ir8PacketShapeBinding,kind,IR8_PACKET_SHAPE_KIND_REPEAT);
            MUT("typing-type",tr.row,st,Ir8PacketShapeTyping,type,scalar);
            MUT("typing-shape",tr.row,st,Ir8PacketShapeTyping,shape,other);
            MUT("typing-scope",tr.row,st,Ir8PacketShapeTyping,scope,env.scheme);
            MUT("typing-contract",tr.row,st,Ir8PacketShapeTyping,contract,0);
            MUT("representation-shape",tr.row,rp,Ir8PacketRepresentation,shape,other);
            MUT("representation-typing",tr.row,rp,Ir8PacketRepresentation,typing,other);
            MUT("representation-ready",tr.row,rp,Ir8PacketRepresentation,ready_kind,IR8_PACKET_READY_KIND_FUNCTION);
            MUT("descriptor-shape",tr.row,sp,Ir8PacketShapeSpec,shape,other);
            MUT("descriptor-typing",tr.row,sp,Ir8PacketShapeSpec,typing,other);
            MUT("descriptor-representation",tr.row,sp,Ir8PacketShapeSpec,representation,other);
            MUT("descriptor-kind",tr.row,sp,Ir8PacketShapeSpec,kind,IR8_PACKET_SHAPE_KIND_I64);
            if(s.kind==IR8_PACKET_SHAPE_KIND_SUM){uint32_t family=N;Ir8PacketFamilyTyping f;
                for(uint32_t k=0;k<typed.table[10].count;++k){read_at(table(11,k,sizeof(f)),&f,sizeof(f));if(f.shape==sid){family=k;break;}}
                need(family!=N,"sum family exists");size_t ft=table(11,family,sizeof(f)),fs=descriptor(3,family,sizeof(Ir8PacketFamilySpec));
                MUT("family-shape",tr.row,ft,Ir8PacketFamilyTyping,shape,other);
                MUT("family-name",tr.row,ft,Ir8PacketFamilyTyping,name,type_at(scalar).atom);
                MUT("family-descriptor-id",tr.row,fs,Ir8PacketFamilySpec,family,N);
                MUT("family-descriptor-shape",tr.row,fs,Ir8PacketFamilySpec,shape,other);
                MUT("family-descriptor-count",tr.row,fs,Ir8PacketFamilySpec,variants.count,f.variants.count-1);
            }
        }
    }
    need(nominals>0,"actual program must instantiate at least one nominal atom");
    for(uint32_t i=0;i<typed.table[18].count;++i){Ir8PacketUse use;size_t uo=table(19,i,sizeof(use));read_at(uo,&use,sizeof(use));
        int found=0;for(uint32_t j=0;j<use.arguments.count;++j){Ir8PacketTypeRef t;read_at(row(use.arguments.object,j,sizeof(t)),&t,sizeof(t));found|=nominal(t.row);}
        if(found){MUT("partial-use",i,uo,Ir8PacketUse,arguments.count,use.arguments.count-1);
            MUT("wrong-use-result",i,uo,Ir8PacketUse,result_type,scalar);}}
}

enum Mode { HEALTHY, FOREIGN_USE, FOREIGN_ACCESS, ZERO_CAPSULE, ENTRY_WORK, NOMINAL_WORK };
static enum Mode mode;
static unsigned calls,real_calls,nominal_calls,injected,entered,seen_type;
static uint32_t selected_type;
static Rt8Handle *watched;
static const Rt8Access *before_access;
static Rt8Access foreign_access;
static Rt8Instantiation foreign_use;
Rt8Handle *__real_rt8_instantiate(Rt8Context *,Rt8Handle *,const Rt8Instantiation *,const char *,const char *);
void __real_rt8_private_table(Rt8Context *,uint32_t,uint32_t,void *,size_t);
void __wrap_rt8_private_table(Rt8Context *c,uint32_t domain,uint32_t id,void *out,size_t bytes) {
    __real_rt8_private_table(c,domain,id,out,bytes);
    if(mode==NOMINAL_WORK&&entered&&!injected){
        if(domain==1&&id==selected_type)seen_type=1;
        if(seen_type&&domain==7){c->guard_work.limit=c->guard_work.used;injected=1;}}
}
Rt8Handle *__wrap_rt8_instantiate(Rt8Context *c,Rt8Handle *h,const Rt8Instantiation *ref,const char *out,const char *source) {
    ++calls;uint32_t nominal_type=N;
    /* These are known-valid generated references, not adversarial pointers. */
    Ir8PacketUse use;memcpy(&use,ref,sizeof(use));
    for(uint32_t i=0;i<use.arguments.count;++i){Ir8PacketTypeRef t;read_at(row(use.arguments.object,i,sizeof(t)),&t,sizeof(t));if(nominal(t.row))nominal_type=t.row;}
    if(nominal_type!=N){++nominal_calls;
        if(mode!=HEALTHY&&!injected&&!entered){entered=1;selected_type=nominal_type;watched=h;
            if(mode==FOREIGN_USE){foreign_use=use;ref=&foreign_use;injected=1;}
            if(mode==FOREIGN_ACCESS){foreign_access=*h->access;h->access=&foreign_access;injected=1;}
            if(mode==ZERO_CAPSULE){h->node->origin.capsule_id=0;injected=1;}
            if(mode==ENTRY_WORK){c->guard_work.limit=c->guard_work.used;injected=1;}
            before_access=h->access;}}
    ++real_calls;Rt8Handle *result=__real_rt8_instantiate(c,h,ref,out,source);
    need(result==h,"instantiate must preserve Handle identity");return result;
}
static void runtime_control(enum Mode which) {
    static const char *const names[]={"healthy","foreign-use","foreign-access","zero-capsule","entry-work","nominal-work"};
    mode=which;calls=real_calls=nominal_calls=injected=entered=seen_type=0;watched=NULL;before_access=NULL;
    Rt8Context *context=NULL;Rt8Options options={UINT64_C(1000000),UINT64_C(100000),0};
    Rt8Report report={0},before={0},again={0};Rt8DestroyReport destroyed={0};
    need(rt8_session_open(&program,&expected,&binding_workspace,&options,&context,&report)==0,"fresh real session admission");
    int rc=rt8_session_step(context,&report);need(calls>0&&nominal_calls>0&&calls==real_calls,"real interposition coverage");
    int ok;
    if(which==HEALTHY){ok=rc==0&&report.fault==0&&report.scalar_result==42;
        need(rt8_session_close(&context,&report)==0&&context==NULL,"healthy close");
        ok=ok&&report.memory.live_bytes==0&&report.memory.live_blocks==0;
        for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&report.categories[i].live_bytes==0&&report.categories[i].live_blocks==0;
    }else{
        ok=rc==2&&injected==1&&watched&&watched->access==before_access&&report.fault==RT8_FAULT_TYPED_GUARD;
        if(which==ENTRY_WORK||which==NOMINAL_WORK)ok=ok&&report.location.status==RT8_STATUS_WORK_LIMIT&&report.location.detail==RT8_DETAIL_WORK_EXHAUSTED;
        else if(which==FOREIGN_USE||which==FOREIGN_ACCESS)ok=ok&&report.location.status==RT8_STATUS_REFERENCE&&report.location.detail==RT8_DETAIL_UNREGISTERED;
        else ok=ok&&report.location.status==RT8_STATUS_ORIGIN;
        need(rt8_session_snapshot(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"fault snapshot retained");
        need(rt8_session_step(context,&again)==2&&memcmp(&report,&again,sizeof(report))==0,"poison cannot resume");
        Rt8Context *same=context;need(rt8_session_close(&context,&again)==2&&context==same,"default close does not surrender fault");
        need(rt8_session_destroy_terminal(&context,&before,&destroyed)==0&&context==NULL,"explicit terminal surrender");
        ok=ok&&memcmp(&report,&before,sizeof(report))==0&&destroyed.status==RT8_DESTROY_DONE&&destroyed.retired_bytes==report.memory.live_bytes&&destroyed.retired_blocks==report.memory.live_blocks&&!destroyed.totals_overflow;
        for(unsigned i=0;i<RT8_MEMORY_CATEGORIES;++i)ok=ok&&destroyed.category_bytes[i]==report.categories[i].live_bytes&&destroyed.category_blocks[i]==report.categories[i].live_blocks;
    }
    printf("{\"kind\":\"runtime\",\"case\":\"%s\",\"rc\":%d,\"fault\":%"PRIu32",\"status\":%"PRIu32",\"detail\":%"PRIu32",\"calls\":%u,\"real_calls\":%u,\"nominal_calls\":%u,\"work\":%"PRIu64",\"live_bytes\":%"PRIu64",\"retired_bytes\":%"PRIu64",\"ok\":%d}\n",names[which],rc,report.fault,report.location.status,report.location.detail,calls,real_calls,nominal_calls,report.guard_work_used,report.memory.live_bytes,destroyed.retired_bytes,ok);
    if(!ok)++failures;
}
int main(void) {
    program=ir8_runtime_generated_program();root=program.packet;length=program.packet_bytes;
    need(length<=IR8_PACKET_MAX_BYTES,"packet byte cap");
    memcpy(&expected,ir8_runtime_generated_expected_bindings(),sizeof(expected));
    Ir8PacketReport report;need(ir8_packet_validate(root,length,&expected,&packet_workspace,&report)==0,"untouched generated packet accepted first");
    read_at(0,&header,sizeof(header));Ir8PacketObjectDirectoryEntry d=object(header.typed_header_object);read_at(d.offset,&typed,sizeof(typed));
    packet_controls();for(unsigned i=0;i<=NOMINAL_WORK;++i)runtime_control((enum Mode)i);
    printf("{\"summary\":true,\"packet_cases\":%u,\"runtime_cases\":6,\"failures\":%u}\n",packet_cases,failures);
    need(fflush(stdout)==0&&!ferror(stdout),"stdout");return failures?1:0;
}
