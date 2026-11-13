"""Runtime and profiling-package closure pins. No subprocess calls: run is guarded by caller."""
from pathlib import Path
import hashlib
import os
import re
import shlex
import stat
import struct
from oracles import require, PACKAGES


def binding(path):
    """Bind raw absolute runtime spelling using kernel-order symlink/.. traversal.

    Source/admission paths still use strict oracles.safe. Loader output may
    legitimately contain bin/../lib; never lexically collapse a symlink/.. pair.
    """
    raw = os.fspath(path)
    require(Path(raw).is_absolute(), 'absolute runtime input path required')
    todo = raw.split('/')[1:]; current = Path('/'); links = []; traversed = 0
    while todo:
        part = todo.pop(0)
        if part == '..': current = current.parent
        elif part not in ('', '.'): current /= part
        st = current.lstat()
        if stat.S_ISLNK(st.st_mode):
            traversed += 1; require(traversed <= 40, 'symlink cycle/limit')
            target = os.readlink(current)
            links.append({'path':str(current),'target':target,'device':st.st_dev,'inode':st.st_ino})
            if target.startswith('/'):
                current = Path('/'); expanded = target.split('/')[1:]
            else:
                current = current.parent; expanded = target.split('/')
            todo = expanded + todo
        elif todo:
            require(stat.S_ISDIR(st.st_mode), 'non-directory path component')
    require(stat.S_ISREG(current.lstat().st_mode), 'binding target not regular')
    with current.open('rb') as stream:
        before = os.fstat(stream.fileno()); digest = hashlib.file_digest(stream, 'sha256').hexdigest(); after = os.fstat(stream.fileno())
    require((before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'file changed during pin')
    return {'path':raw,'resolved':str(current),'links':links,'sha256':digest,'bytes':after.st_size,'device':after.st_dev,'inode':after.st_ino}


def interpreter(path):
    """Read bounded ELF32/ELF64 program headers, refusing scripts/static binaries."""
    with open(path,'rb') as f:
        header=f.read(64)
        require(header[:4]==b'\x7fELF' and len(header)==64,'ELF executable required, no wrapper scripts')
        cls, endian = header[4], header[5]
        require(cls in (1,2) and endian in (1,2) and header[6]==1,'unsupported ELF encoding')
        order='<' if endian==1 else '>'
        if cls==2:
            offset=struct.unpack_from(order+'Q',header,32)[0]; size,count=struct.unpack_from(order+'HH',header,54); fmt=order+'IIQQQQQQ'
        else:
            offset=struct.unpack_from(order+'I',header,28)[0]; size,count=struct.unpack_from(order+'HH',header,42); fmt=order+'IIIIIIII'
        require(0<count<4096 and size==struct.calcsize(fmt),'unsupported ELF headers')
        length=os.fstat(f.fileno()).st_size
        require(offset+size*count<=length,'truncated ELF program headers')
        found=[]
        for i in range(count):
            f.seek(offset+i*size); values=struct.unpack(fmt,f.read(size))
            if values[0]!=3:continue
            start,n=(values[2],values[5]) if cls==2 else (values[1],values[4])
            require(1<n<=4096 and start+n<=length,'invalid PT_INTERP bounds')
            f.seek(start); raw=f.read(n)
            require(raw[-1:]==b'\0' and b'\0' not in raw[:-1],'invalid PT_INTERP string')
            text=raw[:-1].decode('ascii');require(text.startswith('/') and '..' not in Path(text).parts,'unsafe interpreter')
            found.append(text)
        require(len(found)==1,'exactly one ELF interpreter required')
        return found[0]


def loader_paths(stdout):
    require(type(stdout) is str and len(stdout)<1024*1024,'invalid loader output')
    result=[]; names=set(); vdso=0
    for line in stdout.splitlines():
        line=line.strip()
        if re.fullmatch(r'linux-vdso\.so\.\d+ \(0x[0-9a-fA-F]+\)',line):
            vdso+=1;require(vdso==1,'duplicate vdso');continue
        match=re.fullmatch(r'(?:(\S+) => )?(/[^\s]+) \(0x[0-9a-fA-F]+\)',line)
        require(match is not None,'unrecognized/unresolved loader line: '+line)
        name,path=match.groups();name=name or path
        require(name not in names,'duplicate loader binding');names.add(name)
        result.append({'name':name,'binding':binding(path)})
    require(result,'empty loader resolution')
    return sorted(result,key=lambda x:x['name'])


def config_snapshot(paths, dirs):
    files={str(Path(p)) for p in paths}; listings={}
    for directory in dirs:
        d=Path(directory);require(d.is_dir() and not d.is_symlink(),'config directory missing/symlink')
        entries=sorted(str(p) for p in d.iterdir());listings[str(d)]=entries
        for p in entries:
            require(Path(p).is_file(),'non-file loader config entry');files.add(p)
    return {'files':[binding(p) for p in sorted(files)],'directories':listings}


def pin_runtime(executable,run,*,config_paths=('/etc/ld.so.cache','/etc/ld.so.conf'),config_dirs=('/etc/ld.so.conf.d',)):
    executable=binding(executable);loader=binding(interpreter(executable['resolved']))
    config=config_snapshot(config_paths,config_dirs)
    command=[loader['resolved'],'--list',executable['resolved']]
    response=run(command)
    require(type(response) is dict and response.get('returncode')==0 and response.get('stderr')=='','loader command failed')
    require(type(response.get('auth')) is dict and response['auth'],'guarded callback authentication required')
    libraries=loader_paths(response['stdout'])
    require(any(x['binding']['resolved']==loader['resolved'] for x in libraries),'loader missing from runtime closure')
    require(binding(executable['path'])==executable and binding(loader['path'])==loader,'runtime changed during discovery')
    require(config_snapshot(config_paths,config_dirs)==config,'loader configuration changed')
    for item in libraries:
        require(binding(item['binding']['path'])==item['binding'],'runtime library changed during discovery')
    return {'schema':'allocation-runtime-v1','executable':executable,'loader':loader,'libraries':libraries,'config':config,'config_paths':list(config_paths),'config_dirs':list(config_dirs),'command':command,'command_auth':response['auth']}


def verify_runtime(receipt,run):
    current=pin_runtime(receipt['executable']['path'],run,config_paths=receipt['config_paths'],config_dirs=receipt['config_dirs'])
    require({k:v for k,v in current.items() if k!='command_auth'}=={k:v for k,v in receipt.items() if k!='command_auth'},'runtime binding drift')
    return current


def package_records(text):
    records={}
    for chunk in re.split(r'^---\s*$',text,flags=re.M):
        if not chunk.strip():continue
        fields={};key=None
        for line in chunk.splitlines():
            if not line.strip():continue
            if line[:1].isspace():
                require(key is not None,'orphan package continuation');fields[key]+=' '+line.strip()
            else:
                match=re.fullmatch(r'([a-z][a-z0-9-]*):\s*(.*)',line)
                require(match is not None,'invalid package field')
                key,value=match.groups();require(key not in fields,'duplicate package field');fields[key]=value
        unit=fields.get('id');require(unit and unit not in records,'missing/duplicate package unit')
        records[unit]=fields
    return records


def profile_packages(packages_path,expected_sha256,configurations,*,pkgroot):
    """Require authenticated ghc-pkg dump, all 23 units and real profile files.

    configurations maps IDs to current .conf files and is pinned along with dump.
    ${pkgroot} is the sole supported variable; ambiguity is rejected.
    """
    dump=binding(packages_path);require(dump['sha256']==expected_sha256,'package dump authentication failed')
    records=package_records(Path(dump['resolved']).read_text())
    roots=[]
    for name in PACKAGES:
        matches=[u for u,r in records.items() if r.get('name')==name]
        require(len(matches)==1,'ambiguous/missing package root '+name);roots+=matches
    closure=set();todo=list(roots)
    while todo:
        unit=todo.pop();require(unit in records,'missing dependency unit '+unit)
        if unit in closure:continue
        closure.add(unit);todo.extend(shlex.split(records[unit].get('depends','')))
    require(len(closure)==23,'expected 23 transitive package units')
    def directories(record,field):
        values=shlex.split(record.get(field,''));out=[]
        for value in values:
            value=value.replace('${pkgroot}',str(pkgroot))
            require('$' not in value and Path(value).is_absolute(),'unresolved package path')
            p=Path(os.path.normpath(value));require(p.is_dir(),'missing package directory');out.append(p)
        return out
    units=[]
    for unit in sorted(closure):
        record=records[unit];require(unit in configurations,'package configuration missing')
        conf=binding(configurations[unit]);conf_records=package_records(Path(conf['resolved']).read_text())
        require(set(conf_records)=={unit},'package config identity differs')
        # Compare critical resolution fields, expanding pkgroot for both forms.
        for field in ('name','depends','hs-libraries','library-dirs','library-dirs-static','import-dirs'):
            normalize=lambda r:[os.path.normpath(x.replace('${pkgroot}',str(pkgroot))) for x in shlex.split(r.get(field,''))]
            require(normalize(record)==normalize(conf_records[unit]),'package configuration differs: '+field)
        libraries=directories(record,'library-dirs')+directories(record,'library-dirs-static')
        archives=[]
        for library in shlex.split(record.get('hs-libraries','')):
            require(re.fullmatch(r'[A-Za-z0-9_.+-]+',library),'invalid library name')
            matches={str(d/('lib'+library+'_p.a')) for d in libraries if (d/('lib'+library+'_p.a')).exists()}
            require(len(matches)==1,'missing/ambiguous profile archive '+library)
            archives.append(binding(matches.pop()))
        interfaces=[]
        for directory in directories(record,'import-dirs'):
            # Never silently omit an interface subtree through rglob's symlink behavior.
            for folder, child_dirs, _ in os.walk(directory, followlinks=False):
                require(not any((Path(folder)/name).is_symlink() for name in child_dirs), 'symlink interface subtree requires explicit resolution')
            for ordinary in sorted(directory.rglob('*.hi')):
                profile=ordinary.with_suffix('.p_hi');require(profile.is_file(),'missing profiling interface '+str(profile))
                interfaces.append({'ordinary':binding(ordinary),'profile':binding(profile)})
        require(archives or not record.get('hs-libraries'),'profile archive inventory empty')
        units.append({'unit_id':unit,'configuration':conf,'profiling_archives':archives,'interfaces':interfaces})
    for unit in units:
        pins=[unit['configuration'],*unit['profiling_archives']]
        for pair in unit['interfaces']:pins.extend(pair.values())
        for pin in pins:require(binding(pin['path'])==pin,'package input changed during discovery')
    require(binding(packages_path)==dump,'package dump changed')
    return {'schema':'allocation-profile-packages-v1','dump':dump,'roots':roots,'units':units}


def verify_packages(receipt, configurations, *, pkgroot):
    current=profile_packages(receipt['dump']['path'],receipt['dump']['sha256'],configurations,pkgroot=pkgroot)
    require(current==receipt,'profiling package closure drift')
    return current
