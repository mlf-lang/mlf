from pathlib import Path
import hashlib
SOURCE_SHA='380d29e7b951da022b49517237d74df2ecd3ee3a'
OLD='bindE (rebind before (canonicalize skeleton))'
NEW='bindE (rebind before (if IM.null (links skeleton) then skeleton else canonicalize skeleton))'
def instrument(source):
    raw=source.encode();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==SOURCE_SHA
    assert source.count(OLD)==1
    return source.replace(OLD,NEW)
if __name__=='__main__':
    import sys
    Path(sys.argv[2]).write_text(instrument(Path(sys.argv[1]).read_text()))
