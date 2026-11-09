// Native orchestration keeps the same full Clang -O2 pipeline and real -r output.
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/raw_ostream.h"
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
using namespace llvm;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
int partitionMain(int,char**);
static volatile sig_atomic_t cancelled=0;
static void cancel(int){cancelled=1;}
static std::string readText(const fs::path &path){auto b=MemoryBuffer::getFile(path.string());return b?(*b)->getBuffer().str():"";}
static std::string hashFile(const fs::path &path){auto b=MemoryBuffer::getFile(path.string());if(!b)return "";return toHex(SHA256::hash(arrayRefFromStringRef((*b)->getBuffer())),true);}
static double seconds(Clock::time_point start){return std::chrono::duration<double>(Clock::now()-start).count();}
struct Child {
 pid_t pid=-1;std::vector<std::string> argv;std::string label;fs::path out,err;
 Clock::time_point start;double elapsed=0;int code=-1;bool done=false;
};
class Processes {
 fs::path work;Clock::time_point deadline;
 public:
 std::vector<Child> children;
 Processes(fs::path directory,Clock::time_point limit):work(std::move(directory)),deadline(limit){}
 void stop(){
  for(auto &child:children)if(child.pid>0)::kill(-child.pid,SIGKILL);
  for(auto &child:children)if(child.pid>0&&!child.done){int status;while(waitpid(child.pid,&status,0)<0&&errno==EINTR){}child.done=true;child.code=-1;child.elapsed=seconds(child.start);}
 }
 ~Processes(){stop();}
 bool spawn(std::vector<std::string> command,std::string label,bool partition=false){
  if(cancelled||Clock::now()>=deadline)return false;
  Child child;child.argv=std::move(command);child.label=std::move(label);child.start=Clock::now();
  child.out=work/(child.label+".stdout");child.err=work/(child.label+".stderr");
  int out=open(child.out.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600),err=open(child.err.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);
  if(out<0||err<0){if(out>=0)close(out);if(err>=0)close(err);return false;}
  std::vector<char*> args;for(auto &arg:child.argv)args.push_back(arg.data());args.push_back(nullptr);
  outs().flush();errs().flush();
  child.pid=fork();
  if(child.pid==0){
   setpgid(0,0);dup2(out,STDOUT_FILENO);dup2(err,STDERR_FILENO);close(out);close(err);
   // No threads exist in this native driver. The parser child inherits LLVM
   // without another exec/dynamic-loader startup and remains deadline-killable.
   if(partition){int result=partitionMain((int)child.argv.size(),args.data());outs().flush();errs().flush();_exit(result);}
   execv(args[0],args.data());perror("exec compilation child");_exit(127);
  }
  close(out);close(err);
  if(child.pid<0)return false;
  setpgid(child.pid,child.pid); // Child also establishes its group before exec.
  children.push_back(std::move(child));return true;
 }
 bool waitAll(){
  for(;;){
   if(cancelled||Clock::now()>=deadline){stop();return false;}
   bool pending=false;
   for(auto &child:children)if(!child.done){
    int status=0;pid_t got=waitpid(child.pid,&status,WNOHANG);
    if(got==0){pending=true;continue;}
    if(got<0&&errno==EINTR){pending=true;continue;}
    child.done=true;child.elapsed=seconds(child.start);
    child.code=got<0?127:WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
    // A completed leader must not leave descendants behind with open pipes.
    kill(-child.pid,SIGKILL);
    if(child.code!=0){stop();return false;}
   }
   if(!pending)return true;
   usleep(1000);
  }
 }
 json::Array records(){
  json::Array result;
  for(auto &child:children){json::Array args;for(auto &arg:child.argv)args.push_back(arg);
   result.push_back(json::Object{{"label",child.label},{"argv",std::move(args)},{"exit_code",child.code},{"seconds",child.elapsed},
       {"stdout",readText(child.out)},{"stderr",readText(child.err)}});
  }
  return result;
 }
};
int nativeDriver(int argc,char **argv){
 auto start=Clock::now();
 struct sigaction action{};action.sa_handler=cancel;sigemptyset(&action.sa_mask);sigaction(SIGINT,&action,nullptr);sigaction(SIGTERM,&action,nullptr);
 auto text=readText(argv[2]);auto parsed=json::parse(text);
 if(!parsed){consumeError(parsed.takeError());errs()<<"invalid driver configuration\n";return 2;}
 auto *settings=parsed->getAsObject();auto *clangInfo=settings?settings->getObject("clang"):nullptr;
 auto *helperInfo=settings?settings->getObject("helper"):nullptr;
 auto clang=clangInfo?clangInfo->getString("path"):std::nullopt;
 auto helper=helperInfo?helperInfo->getString("path"):std::nullopt;
 auto count=settings?settings->getInteger("jobs"):std::nullopt;
 auto timeout=settings?settings->getInteger("timeout_seconds"):std::nullopt;
 if(!clang||!helper||!count||*count<1||*count>64||!timeout||*timeout<1){errs()<<"invalid driver contract\n";return 2;}
 std::string input,output;bool compile=false,optimize=false;int sources=0,outputs=0;
 for(int i=3;i<argc;++i){StringRef value(argv[i]);
  if(value=="-o"&&i+1<argc){output=argv[++i];++outputs;}
  else if(value=="-c")compile=true;
  else if(value=="-O2")optimize=true;
  else if(value=="-Wno-override-module"){}
  else if(!value.starts_with("-")&&value.ends_with(".ll")){input=value.str();++sources;}
  else {errs()<<"unsupported native driver arguments\n";return 2;}
 }
 if(!compile||!optimize||sources!=1||outputs!=1){errs()<<"invalid native compilation request\n";return 2;}
 std::error_code ec;fs::path source=fs::canonical(input,ec);if(ec){errs()<<ec.message()<<"\n";return 2;}
 fs::path destination=fs::weakly_canonical(fs::absolute(output,ec),ec);if(ec){errs()<<ec.message()<<"\n";return 2;}
 if(source==destination){std::vector<char*> args{const_cast<char*>(clang->data())};for(int i=3;i<argc;++i)args.push_back(argv[i]);args.push_back(nullptr);execv(args[0],args.data());return 127;}
 auto sourceHash=hashFile(source);
 std::string temporary=(destination.parent_path()/".mlf-parallel-XXXXXX").string();std::vector<char> buffer(temporary.begin(),temporary.end());buffer.push_back(0);
 if(!mkdtemp(buffer.data())){errs()<<"cannot create parallel work directory\n";return 2;}
 fs::path work(buffer.data());
 bool success=false;std::string error="parallel compilation failed";json::Array records;std::string outputHash;
 {
  Processes jobs(work,start+std::chrono::seconds(*timeout));
  std::vector<std::string> partition{helper->str(),source.string(),(work/"part-").string(),std::to_string(*count)};
  bool good=jobs.spawn(std::move(partition),"partition",true)&&jobs.waitAll();
  std::vector<std::string> objects;
  for(int64_t i=0;good&&i<*count;++i){auto part=(work/("part-"+std::to_string(i)+".bc")).string();auto object=(work/(std::to_string(i)+".o")).string();objects.push_back(object);
   good=jobs.spawn({clang->str(),"-O2","-Wno-override-module","-c",part,"-o",object},"compile-"+std::to_string(i));
  }
  if(good)good=jobs.waitAll();
  auto combined=work/"combined.o";
  if(good){std::vector<std::string> command{clang->str(),"-nostdlib","-r"};command.insert(command.end(),objects.begin(),objects.end());command.push_back("-o");command.push_back(combined.string());good=jobs.spawn(std::move(command),"combine")&&jobs.waitAll();}
  if(good&&!cancelled&&hashFile(source)==sourceHash){outputHash=hashFile(combined);if(!outputHash.empty()&&rename(combined.c_str(),destination.c_str())==0)success=true;}
  if(!success)jobs.stop();
  records=jobs.records();
 }
 json::Object receipt{{"format",1},{"complete",success},{"source",source.string()},{"source_sha256",sourceHash},{"jobs",*count},
                      {"installed_tools",*parsed},{"commands",std::move(records)},{"seconds",seconds(start)}};
 if(success)receipt["output_sha256"]=outputHash;else receipt["error"]=error;
 std::error_code writeError;raw_fd_ostream stream(destination.string()+".parallel.json",writeError,sys::fs::OF_None);
 if(writeError){errs()<<writeError.message()<<"\n";success=false;}else{stream<<formatv("{0:2}\n",json::Value(std::move(receipt)));stream.flush();if(stream.has_error()){errs()<<"cannot write parallel compilation receipt\n";stream.clear_error();success=false;}}
 fs::remove_all(work,ec);
 if(!success)errs()<<error<<"\n";
 return success?0:1;
}
int main(int argc,char **argv){if(argc>=3&&StringRef(argv[1])=="--driver")return nativeDriver(argc,argv);return partitionMain(argc,argv);}
