#include "llvm/IR/Module.h"
#include "llvm/IR/Instructions.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include <algorithm>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>
using namespace llvm;
int partitionMain(int argc,char **argv) {
 if(argc!=4) { errs()<<"usage: partition INPUT PREFIX COUNT\n";return 2; }
 unsigned count=0; if(StringRef(argv[3]).getAsInteger(10,count)||count<1||count>64)return 2;
 LLVMContext context;SMDiagnostic diag;
 auto buffer=MemoryBuffer::getFile(argv[1]);if(!buffer){errs()<<buffer.getError().message()<<"\n";return 1;}
 auto module=parseIR((*buffer)->getMemBufferRef(),diag,context);
 const auto digest=SHA256::hash(arrayRefFromStringRef((*buffer)->getBuffer()));
 const std::string symbolPrefix="__mlf_partition_"+toHex(digest,true)+"_";
 if(!module){diag.print(argv[0],errs());return 1;}
 if(verifyModule(*module,&errs()))return 1;
 // Deliberately narrow generated-IR contract; fail closed on features not used by
 // this compiler, leaving ordinary whole-module compilation available.
 if(!module->getModuleInlineAsm().empty()||!module->alias_empty()||!module->ifunc_empty()){errs()<<"unsupported module assembly/aliases/ifuncs\n";return 1;}
 std::set<GlobalValue*> formerlyLocal;
 for(auto &g:module->global_values()){
  if(g.getName().starts_with("__mlf_partition_")){errs()<<"reserved partition symbol namespace\n";return 1;}
  if(g.hasLocalLinkage())formerlyLocal.insert(&g);
 }
 std::set<const Value*> inspectedConstants;
 std::function<bool(const Value*)> hasBlockAddress=[&](const Value *v){
  if(!inspectedConstants.insert(v).second)return false;
  if(isa<BlockAddress>(v))return true;
  if(auto *c=dyn_cast<Constant>(v))for(auto &op:c->operands())if(hasBlockAddress(op.get()))return true;
  return false;
 };
 for(auto &g:module->globals()){
  if(g.hasAppendingLinkage()||g.getName()=="llvm.global_ctors"||g.getName()=="llvm.global_dtors"){
   errs()<<"unsupported appending global/constructors/destructors\n";return 1;
  }
  if(hasBlockAddress(&g)){errs()<<"unsupported block address\n";return 1;}
 }
 for(auto &f:*module)for(auto &bb:f)for(auto &ins:bb){
  if(auto *call=dyn_cast<CallBase>(&ins))if(call->isInlineAsm()){errs()<<"unsupported inline assembly\n";return 1;}
  for(auto &op:ins.operands())if(hasBlockAddress(op)){errs()<<"unsupported block address\n";return 1;}
 }
 std::vector<Function*> funcs;std::set<const GlobalValue*> shared;
 for(auto &f:*module)if(!f.isDeclaration()){
  if(f.hasComdat()){errs()<<"unsupported comdat\n";return 1;}
  if(f.hasLocalLinkage()&&f.hasFnAttribute(Attribute::AlwaysInline)&&!f.hasAddressTaken())shared.insert(&f);
  else funcs.push_back(&f);
 }
 std::map<Function*,int> index;for(unsigned i=0;i<funcs.size();++i)index[funcs[i]]=i;
 std::vector<std::set<int>> graph(funcs.size());
 for(unsigned i=0;i<funcs.size();++i){
  std::set<const Value*> seen;
  std::function<void(const Value*)> inspect=[&](const Value *v){
   if(!seen.insert(v).second)return;
   if(auto *f=dyn_cast<Function>(v)){auto it=index.find(const_cast<Function*>(f));if(it!=index.end())graph[i].insert(it->second);return;}
   if(auto *c=dyn_cast<Constant>(v))for(auto &op:c->operands())inspect(op.get());
  };
  for(auto &bb:*funcs[i])for(auto &ins:bb)for(auto &op:ins.operands())inspect(op.get());
 }
 int serial=0;std::vector<int> ids(funcs.size(),-1),low(funcs.size()),stack;std::set<int> active;std::vector<std::vector<int>> groups;
 std::function<void(int)> visit=[&](int v){
  ids[v]=low[v]=serial++;stack.push_back(v);active.insert(v);
  for(int w:graph[v])if(ids[w]<0){visit(w);low[v]=std::min(low[v],low[w]);}else if(active.count(w))low[v]=std::min(low[v],ids[w]);
  if(low[v]==ids[v]){groups.emplace_back();for(;;){int w=stack.back();stack.pop_back();active.erase(w);groups.back().push_back(w);if(w==v)break;}}
 };
 for(unsigned i=0;i<funcs.size();++i)if(ids[i]<0)visit(i);
 auto weight=[&](const std::vector<int>&g){size_t n=0;for(int i:g)n+=funcs[i]->getInstructionCount();return n;};
 // Merge single-user callee components while retaining bounded task sizes.
 std::vector<unsigned> component(funcs.size());
 for(unsigned i=0;i<groups.size();++i)for(int v:groups[i])component[v]=i;
 std::vector<unsigned> parent(groups.size());std::vector<size_t> cost(groups.size());size_t total=0;
 for(unsigned i=0;i<groups.size();++i){parent[i]=i;cost[i]=weight(groups[i]);total+=cost[i];}
 std::function<unsigned(unsigned)> find=[&](unsigned i){return parent[i]==i?i:parent[i]=find(parent[i]);};
 std::vector<std::set<unsigned>> incoming(groups.size());
 for(unsigned v=0;v<graph.size();++v)for(int w:graph[v])if(component[v]!=component[w])incoming[component[w]].insert(component[v]);
 for(unsigned target=0;target<groups.size();++target)if(incoming[target].size()==1){
  unsigned a=find(target),b=find(*incoming[target].begin());
  if(a!=b&&cost[a]+cost[b]<=total/(count*2)){parent[a]=b;cost[b]+=cost[a];}
 }
 std::map<unsigned,std::vector<int>> merged;
 for(unsigned i=0;i<groups.size();++i)for(int v:groups[i])merged[find(i)].push_back(v);
 groups.clear();for(auto &entry:merged)groups.push_back(std::move(entry.second));
 std::stable_sort(groups.begin(),groups.end(),[&](auto&a,auto&b){return weight(a)>weight(b);});
 std::map<const GlobalValue*,unsigned> owner;std::vector<size_t> weights(count);
 for(auto &g:groups){unsigned part=std::min_element(weights.begin(),weights.end())-weights.begin();for(int i:g)owner[funcs[i]]=part;weights[part]+=weight(g);}
 // Place each global beside its actual users where possible. Recursive
 // constant/global references are followed without duplicating mutable state.
 std::map<const GlobalVariable*,std::set<unsigned>> globalUsers;
 for(auto &g:module->globals())if(!g.isDeclaration()){
  std::set<const Value*> seen;std::set<unsigned> users;
  std::function<void(const Value*)> collect=[&](const Value *v){
   if(!seen.insert(v).second)return;
   for(const User *u:v->users())if(auto *ins=dyn_cast<Instruction>(u)){
    if(shared.count(ins->getFunction()))for(unsigned i=0;i<count;++i)users.insert(i);
    else users.insert(owner[ins->getFunction()]);
   }else collect(u);
  };
  collect(&g);owner[&g]=users.empty()?0:*users.begin();globalUsers[&g]=std::move(users);
 }
 unsigned exposed=0;
 for(auto &f:*module)if(!f.isDeclaration()&&!shared.count(&f)&&f.hasLocalLinkage()){
  const unsigned home=owner[&f];std::set<const Value*> seen;
  std::function<bool(const Value*)> outside=[&](const Value *v){
   if(!seen.insert(v).second)return false;
   for(const User *u:v->users()){
    if(auto *ins=dyn_cast<Instruction>(u)){const auto *user=ins->getFunction();if(shared.count(user)||owner[user]!=home)return true;}
    else if(auto *global=dyn_cast<GlobalVariable>(u)){if(owner[global]!=home)return true;}
    else if(outside(u))return true;
   }
   return false;
  };
  if(outside(&f)){f.setLinkage(GlobalValue::ExternalLinkage);f.setVisibility(GlobalValue::HiddenVisibility);++exposed;}
 }
 outs()<<"exposed="<<exposed<<" ";
 for(auto &g:module->globals())if(!g.isDeclaration()){
  if(g.hasComdat()||g.isThreadLocal()){errs()<<"unsupported global comdat/threadlocal\n";return 1;}
  if(g.hasLocalLinkage()&&globalUsers[&g].size()>1){g.setLinkage(GlobalValue::ExternalLinkage);g.setVisibility(GlobalValue::HiddenVisibility);}
 }
 for(auto *g:formerlyLocal)if(!g->hasLocalLinkage())g->setName(symbolPrefix+g->getName().str());
 for(unsigned part=0;part<count;++part){
  ValueToValueMapTy mapping;
  auto output=CloneModule(*module,mapping,[&](const GlobalValue *g){return shared.count(g)||(owner.count(g)&&owner[g]==part);});
  if(verifyModule(*output,&errs()))return 1;
  std::error_code ec;raw_fd_ostream stream(std::string(argv[2])+std::to_string(part)+".bc",ec,sys::fs::OF_None);
  if(ec){errs()<<ec.message()<<"\n";return 1;}WriteBitcodeToFile(*output,stream);
 }
 outs()<<"functions="<<funcs.size()<<" inline="<<shared.size()<<" groups="<<groups.size()<<" weights=";for(auto w:weights)outs()<<w<<",";outs()<<"\n";
 return 0;
}
