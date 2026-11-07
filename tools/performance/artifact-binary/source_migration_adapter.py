"""Candidate prepared-source identity loader; no native or release qualification.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. Both live pins are explicit.
"""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = '05265566df83426471beb968b0a8cd866e3e2ff53b53dc17f1efa4135f068232'
CONTRACT_SOURCE_SHA256 = 'dc5a2b904600e3975dd40d7506766ad22026e7ba567f7902090047f9ef374e91'


# Record platform support before tests wrap os.open. No unsafe whole-path fallback.
_RELATIVE_READ_SUPPORTED = (os.open in os.supports_dir_fd and
                            os.stat in os.supports_dir_fd and
                            os.stat in os.supports_follow_symlinks)

def read_implementation(path):
    """Anchor every component to retained directory handles; fail closed otherwise."""
    if (not _RELATIVE_READ_SUPPORTED or not getattr(os,'O_DIRECTORY',0) or
            not getattr(os,'O_NOFOLLOW',0) or not getattr(os,'O_NONBLOCK',0)):
        raise ValueError('secure relative-open API unavailable; no unsafe fallback')
    raw_path=os.fspath(path)
    if not isinstance(raw_path,str) or '..' in raw_path.split(os.sep):
        raise ValueError('noncanonical implementation path')
    path=Path(raw_path).absolute()
    handles=[];entries=[];fd=None
    def identity(info):
        return info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)
    def ordinary(info,directory):
        return ((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
                not getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))
    try:
        parent=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        handles.append(parent)
        for component in path.parts[1:-1]:
            before=os.stat(component,dir_fd=parent,follow_symlinks=False)
            if not ordinary(before,True):raise ValueError('implementation parent is not an ordinary directory')
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            handles.append(child)
            if identity(os.fstat(child))!=identity(before):raise ValueError('implementation parent replaced during open')
            entries.append((parent,component,identity(before),True))
            parent=child
        before=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if not ordinary(before,False) or before.st_size>65536:
            raise ValueError('bounded regular contract implementation required')
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_BINARY',0),dir_fd=parent)
        info=os.fstat(fd)
        if identity(info)!=identity(before):raise ValueError('contract implementation replaced during open')
        entries.append((parent,path.name,identity(before),False))
        raw=b''
        while len(raw)<=65536:
            chunk=os.read(fd,min(8192,65537-len(raw)))
            if not chunk:break
            raw+=chunk
        after=os.fstat(fd)
        if len(raw)>65536 or (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ValueError('implementation byte bound or mutation')
        # Verify the original directory entries through the original retained
        # parents. A rename followed by a same-target symlink is NOT accepted.
        for parent,name,expected,directory in entries:
            current=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if not ordinary(current,directory) or identity(current)!=expected:
                raise ValueError('implementation path changed during read')
        return raw
    except OSError as error:
        raise ValueError('implementation relative-open failed') from error
    finally:
        if fd is not None:os.close(fd)
        for handle in reversed(handles):os.close(handle)


def live_contract(history_root, source_root=None):
    if FINAL_MANIFEST_SHA256 is None:
        raise ValueError('binary source migration is not frozen; live135 admission is unavailable')
    directory = Path(__file__).resolve().parent
    path = directory / 'prepared_source_contract.py'
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed prepared-source candidate contract implementation SHA')
    module = types.ModuleType('fixed_binary_source_contract')
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
