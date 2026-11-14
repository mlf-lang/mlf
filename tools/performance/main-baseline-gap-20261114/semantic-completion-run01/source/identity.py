"""Explicit boundary-SHA/intermediate-metadata policy, no entry point.
Not continuous content attestation. Only a cooperating single-writer scope is
covered; advisory locks are not an ACL and cannot defeat hostile write/restore.
"""
from pathlib import Path
import os,stat,hashlib

def need(ok,message):
    if not ok:raise RuntimeError(message)

def shape(path):
    p=Path(path);need(p.is_absolute() and '..' not in p.parts,'absolute resolved identity')
    for ancestor in [p,*p.parents]:need(not ancestor.is_symlink(),'identity symlink ancestor')
    st=p.lstat();need(stat.S_ISREG(st.st_mode),'identity regular file')
    return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def attest(pin):
    p=Path(pin['path']);before=shape(p)
    with p.open('rb') as stream:
        opened=os.fstat(stream.fileno())
        need((opened.st_dev,opened.st_ino)==before[:2],'hash opened different file')
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=shape(p)
    need(before==after and after[6]==pin['bytes'] and digest==pin['sha256'],'boundary full content/identity mismatch')
    return after

def capture(pins):
    result={}
    for p in pins:
        need(p['path'] not in result,'capture duplicate path')
        result[p['path']]={'pin':p,'identity':attest(p)}
    return result

def check(snapshot):
    for path,value in snapshot.items():need(shape(path)==value['identity'],'intermediate file identity changed: '+path)

def finish(snapshot):
    for value in snapshot.values():need(attest(value['pin'])==value['identity'],'boundary source/old-output identity changed')

def extend(snapshot,pins,strict_new=True):
    for p in pins:
        if p['path'] in snapshot:
            need(snapshot[p['path']]['pin']==p,'conflicting immutable output');continue
        value=attest(p);need(not strict_new or value[5]==1,'new immutable output hardlink')
        snapshot[p['path']]={'pin':p,'identity':value}

def runtime_shape(value):
    """Same kernel-order path traversal as frozen runtime binding, without SHA.
    Full bound bytes are verified at stage boundaries; every intermediate check
    authenticates the recorded raw spelling, symlink chain and final inode.
    """
    raw=value['path'];need(Path(raw).is_absolute(),'absolute runtime identity')
    todo=raw.split('/')[1:];current=Path('/');links=[];count=0
    while todo:
        part=todo.pop(0)
        if part=='..':current=current.parent
        elif part not in ('','.'):current/=part
        st=current.lstat()
        if stat.S_ISLNK(st.st_mode):
            count+=1;need(count<=40,'runtime link bound');target=os.readlink(current)
            links.append({'path':str(current),'target':target,'device':st.st_dev,'inode':st.st_ino})
            if target.startswith('/'):current=Path('/');expanded=target.split('/')[1:]
            else:current=current.parent;expanded=target.split('/')
            todo=expanded+todo
        elif todo:need(stat.S_ISDIR(st.st_mode),'runtime directory identity')
    st=current.lstat()
    need(stat.S_ISREG(st.st_mode) and str(current)==value['resolved'] and links==value['links'] and
         (st.st_dev,st.st_ino,st.st_size)==(value['device'],value['inode'],value['bytes']),'runtime resolution identity changed')
    return current

def runtime_rows(runtime):
    return [runtime['executable'],runtime['loader'],*runtime['config']['files'],*[x['binding'] for x in runtime['libraries']]]

def runtime_check(runtime):
    for value in runtime_rows(runtime):runtime_shape(value)
    for directory,entries in runtime['config']['directories'].items():
        d=Path(directory);need(d.is_dir() and not d.is_symlink(),'runtime config directory identity')
        need(sorted(str(p) for p in d.iterdir())==entries,'runtime config name set')
