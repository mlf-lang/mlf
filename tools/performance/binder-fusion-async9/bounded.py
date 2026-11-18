"""CI-only bounded process-group supervision; no performance conclusions."""
import hashlib,json,os,pathlib,re,resource,signal,stat,subprocess,time
P=pathlib.Path
MIB=1024**2
class GateError(RuntimeError):pass
def need(ok,msg):
    if not ok:raise GateError(msg)
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def sha(path,check=lambda:None):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for b in iter(lambda:f.read(MIB),b''):check();h.update(b)
    return h.hexdigest()
def identity(path,check=lambda:None):
    path=P(path);s=path.stat()
    return dict(bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),sha256=sha(path,check),resolved=str(path.resolve()))
def inventory(root,check):
    rows=[]
    for p in sorted(root.rglob('*')):
        check();s=p.lstat();rel=str(p.relative_to(root))
        if p.is_symlink():rows.append(dict(path=rel,symlink=os.readlink(p)))
        elif p.is_dir():continue
        else:
            need(stat.S_ISREG(s.st_mode),'nonregular inventory file')
            rows.append(dict(path=rel,bytes=s.st_size,mode=stat.S_IMODE(s.st_mode),sha256=sha(p,check)))
    return rows
def artifact_budget(root,limit=88*MIB):
    total=count=0
    for p in root.rglob('*'):
        s=p.lstat()
        if p.is_dir():continue
        need(stat.S_ISREG(s.st_mode),'artifact symlink/special')
        total+=s.st_size;count+=1
        need(total<=limit and count<=2048,'artifact cap exceeded')
    return total
def resource_floor(root,disk_floor_GiB=4):
    import shutil
    rows=dict((l.split(':')[0],l.split(':')[1].split()[0])for l in P('/proc/meminfo').read_text().splitlines())
    result=dict(mem_available_KiB=int(rows['MemAvailable']),disk_bytes=shutil.disk_usage(root).free,required_disk_bytes=disk_floor_GiB*1024**3)
    need(result['mem_available_KiB']>=4*1024**2,'CI less than4GiB available')
    need(result['disk_bytes']>=disk_floor_GiB*1024**3,'CI disk below required phase floor')
    return result
def limits(file_limit):
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,((600 if file_limit==256*MIB else 240),)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def group_alive(pid):
    try:os.killpg(pid,0);return True
    except ProcessLookupError:return False
def send(pid,sig):
    try:os.killpg(pid,sig)
    except ProcessLookupError:pass
def cleanup(p):
    if p is None:return True
    if group_alive(p.pid):send(p.pid,signal.SIGTERM)
    try:p.wait(timeout=2)
    except subprocess.TimeoutExpired:
        send(p.pid,signal.SIGKILL)
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:return False
    if group_alive(p.pid):send(p.pid,signal.SIGKILL)
    end=time.monotonic()+1
    while group_alive(p.pid)and time.monotonic()<end:time.sleep(.05)
    return not group_alive(p.pid)
class Supervisor:
    def __init__(self,artifacts,whole,work,phase):
        need(phase in ['install','focused','build'],'unknown limit policy phase')
        self.phase=phase;self.file_limit={'install':1024*MIB,'focused':8*MIB,'build':256*MIB}[phase]
        self.artifacts=artifacts;self.start=time.monotonic();self.whole=whole;self.work=work
        self.proc=None;self.records=[];self.clean=True;self.stopped=False
        self.oldterm=signal.getsignal(signal.SIGTERM);self.oldalarm=signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGTERM,self.stop);signal.signal(signal.SIGALRM,self.stop);signal.alarm(whole-5)
    def stop(self,*args):
        if self.stopped:return
        self.stopped=True;raise GateError('termination/deadline requested')
    def check(self):
        need(not self.stopped and time.monotonic()-self.start<self.work,'bounded phase deadline')
    def run(self,name,argv,cwd,seconds,env):
        self.check();need(seconds>0,'aggregate budget exhausted before spawn');before=time.monotonic();rec=dict(name=name,argv=list(map(str,argv)),exit=None,limit_policy_phase=self.phase,child_fsize_limit_bytes=self.file_limit,utc_start=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        log=self.artifacts/'logs'/name;log.parent.mkdir(exist_ok=True)
        with open(str(log)+'.stdout','xb')as out,open(str(log)+'.stderr','xb')as err:
            try:
                self.proc=subprocess.Popen(list(map(str,argv)),cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,preexec_fn=lambda:limits(self.file_limit))
                rec['pid']=self.proc.pid
                while True:
                    self.check();need(time.monotonic()-before<seconds,'step deadline '+name)
                    pid,status,usage=os.wait4(self.proc.pid,os.WNOHANG)
                    if pid:
                        self.proc.returncode=os.waitstatus_to_exitcode(status);rec['exit']=self.proc.returncode
                        rec['rusage']=dict(user_s=usage.ru_utime,system_s=usage.ru_stime,maxrss_KiB=usage.ru_maxrss,scope='direct waited child, not tree RSS');break
                    artifact_budget(self.artifacts);time.sleep(.1)
            finally:
                clean=cleanup(self.proc);self.clean=self.clean and clean;self.proc=None
                rec.update(cleanup=clean,elapsed_s=time.monotonic()-before)
                self.records.append(rec);write(self.artifacts/'steps'/(name+'.json'),rec)
        need(rec['exit']==0 and rec['cleanup'],'child failed/cleanup incomplete '+name)
        need(rec['elapsed_s']<=seconds,'post-step cap '+name)
        return log,rec['elapsed_s']
    def finish(self):
        self.clean=cleanup(self.proc)and self.clean;self.proc=None
        signal.alarm(0);signal.signal(signal.SIGTERM,self.oldterm);signal.signal(signal.SIGALRM,self.oldalarm)
        return dict(limit_policy_phase=self.phase,child_fsize_limit_bytes=self.file_limit,cleanup=self.clean,whole_s=time.monotonic()-self.start,within_whole=time.monotonic()-self.start<self.whole,process_group_scope_only=True,global_descendants_or_ECHILD_claim=False)
def ci_identity():
    # Explicit nonsecret allowlist only. Never dump environment/proxy/token values.
    keys=['GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REPOSITORY','GITHUB_REF']
    value={key:os.environ.get(key,'')for key in keys}
    need(re.fullmatch(r'[0-9a-f]{40}',value['GITHUB_SHA']) is not None,'invalid CI commit identity')
    for key in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT']:need(re.fullmatch(r'[1-9][0-9]*',value[key]) is not None,'invalid CI run identity')
    need(value['GITHUB_REPOSITORY']=='mlf-lang/mlf','only target repository admitted')
    need(value['GITHUB_REF']=='refs/heads/perf/binder-fusion-async9-20261118','only exact qualification branch admitted')
    return value
def ci_only():
    need(os.environ.get('GITHUB_ACTIONS')=='true','only GitHub Actions admitted')
    return ci_identity()
def safe_env(root,prefix=None):
    home=root/'home';tmp=root/'tmp';home.mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
    env=dict(PATH=(str(prefix/'bin')+':'if prefix else'')+'/usr/bin:/bin',HOME=str(home),TMPDIR=str(tmp),TMP=str(tmp),LANG='C.UTF-8',LC_ALL='C.UTF-8')
    # Preserve configured network trust/routing; never serialize these values.
    for key in ['http_proxy','https_proxy','all_proxy','no_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE']:
        if key in os.environ:env[key]=os.environ[key]
    return env


