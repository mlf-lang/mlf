"""Strict complete GHC -s parser. Raw units and inconsistent %GC are preserved.

Adapted from reviewed foundation14 run_diagnostic.parse_statistics. Residency
is sampled liveness, not RSS. Profiling allocation is not equated to RTS bytes.
"""
import math
import re

class StatisticsError(ValueError): pass

def require(value,message):
    if not value:raise StatisticsError(message)

def integer(value):
    require(re.fullmatch(r'(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)',value) is not None,'invalid RTS integer')
    return int(value.replace(',',''))

def finite(value):
    require(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value) is not None,'invalid RTS decimal')
    result=float(value)
    require(math.isfinite(result) and result>=0,'nonfinite RTS decimal')
    return result

def parse_statistics(raw):
    require(isinstance(raw,(bytes,str)),'RTS report bytes/text required')
    require(len(raw)<=1024*1024,'RTS report oversized')
    try:text=raw.decode('utf-8') if isinstance(raw,bytes) else raw
    except UnicodeError as e:raise StatisticsError('invalid RTS UTF-8') from e
    def single(pattern):
        rows=re.findall(pattern,text,re.M)
        require(len(rows)==1,'missing/duplicate RTS field: '+pattern)
        return rows[0]
    result={'schema':'ghc-rts-s-v1'}
    for key,label in [('allocated_bytes','bytes allocated in the heap'),('copied_bytes','bytes copied during GC'),('maximum_slop_bytes','bytes maximum slop')]:
        result[key]=integer(single(r'^\s*(\S+) '+label+r'\s*$'))
    residency,samples=single(r'^\s*(\S+) bytes maximum residency \((\S+) sample\(s\)\)\s*$')
    result.update(maximum_residency_bytes=integer(residency),major_gc_residency_samples=integer(samples))
    memory,unit,fragmentation,fragmentation_unit=single(r'^\s*(\S+)\s+([KMGT]i?B) total memory in use \((\S+) ([KMGT]i?B) lost due to fragmentation\)\s*$')
    result['rts_memory_in_use']={'value':finite(memory),'unit':unit,'raw_line':single(r'^(.*total memory in use.*)$'),'fragmentation':{'value':finite(fragmentation),'unit':fragmentation_unit}}
    result['times']={}
    for label in ['INIT','MUT','GC','EXIT','Total']:
        cpu,elapsed=single(r'^\s*'+label+r'\s+time\s+(\S+)s\s+\(\s*(\S+)s elapsed\)\s*$')
        result['times'][label]={'cpu_seconds':finite(cpu),'elapsed_seconds':finite(elapsed)}
    for label in ['PROF','RP']:
        if re.search(r'^\s*'+label+r'\s+time\b',text,re.M):
            cpu,elapsed=single(r'^\s*'+label+r'\s+time\s+(\S+)s\s+\(\s*(\S+)s elapsed\)\s*$')
            result['times'][label]={'cpu_seconds':finite(cpu),'elapsed_seconds':finite(elapsed)}
    result['generations']=[]
    generation_lines=re.findall(r'^\s*Gen[^\n]*$',text,re.M)
    for line in generation_lines:
        match=re.fullmatch(r'\s*Gen\s+(\S+)\s+(\S+) colls,\s+(\S+) par\s+(\S+)s\s+(\S+)s\s+(\S+)s\s+(\S+)s\s*',line)
        require(match is not None,'malformed generation row')
        gen,count,parallel,cpu,elapsed,average,maximum=match.groups()
        row=dict(generation=integer(gen),collections=integer(count),parallel_collections=integer(parallel),cpu_seconds=finite(cpu),elapsed_seconds=finite(elapsed),average_pause_seconds=finite(average),maximum_pause_seconds=finite(maximum))
        require(row['parallel_collections']==0,'unexpected parallel GC')
        # Rounded printed pause values need not equal sums; do not invent precision.
        result['generations'].append(row)
    require([r['generation'] for r in result['generations']]==[0,1],'exact ordered two-generation summary required')
    cpu,elapsed=single(r'^\s*Productivity\s+(\S+)% of total user,\s+(\S+)% of total elapsed\s*$')
    result['productivity_percent']={'user':finite(cpu),'elapsed':finite(elapsed)}
    require(all(v<=100 for v in result['productivity_percent'].values()),'invalid productivity')
    result['allocation_rate_bytes_per_mut_second']=integer(single(r'^\s*Alloc rate\s+(\S+) bytes per MUT second\s*$'))
    result['reported_gc_percent']=None
    if re.search(r'^\s*%GC\b',text,re.M):
        cpu,elapsed=single(r'^\s*%GC\s+time\s+(\S+)%\s+\(\s*(\S+)% elapsed\)\s*$')
        values={'cpu':finite(cpu),'elapsed':finite(elapsed)}
        require(all(v<=100 for v in values.values()),'invalid reported %GC')
        result['reported_gc_percent']={'values':values,'raw_line':single(r'^(\s*%GC[^\n]*)$'),'interpretation':'raw reported field only; may be inconsistent; not measured GC share'}
    total=result['times']['Total']['cpu_seconds']
    result['gc_cpu_fraction_from_rounded_times']=result['times']['GC']['cpu_seconds']/total if total>0 else None
    result['limitations']='Rounded RTS process totals. Residency is sampled major-GC liveness, not peak RSS. Raw %GC may be inconsistent. Profile self-allocation and RTS allocation are different accounting domains; no equality or ordinary exclusive attribution inferred.'
    return result

parse_stats=parse_statistics
