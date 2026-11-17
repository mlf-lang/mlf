from pathlib import Path
import shutil
src=Path('/tmp/mlf-profile-prep-20261117');dst=Path('/tmp/mlf-profile-split-prep-20261117')
for p in src.iterdir():
 if p.is_file() and p.name not in ['adapt.py','prep-manifest.txt','remote-foundation-screen.yml']:shutil.copy2(p,dst/p.name)
def edit(name,old,new):
 p=dst/name;s=p.read_text();assert s.count(old)==1,(name,old,s.count(old));p.write_text(s.replace(old,new))
edit('build.py',"REFS={'A':'fc300bc9fdc389b585cbef0630fc8915d53e89c5'}","REFS={s:'fc300bc9fdc389b585cbef0630fc8915d53e89c5' for s in ['A','P']}\nfrom instrumentation import instrument")
edit('build.py',"for side,source in [('A',P(a.a_source).resolve())]:","for side,source in [(s,P(a.a_source).resolve()) for s in ['A','P']]:")
edit('build.py',"expected=row[side]","expected=row['A']")
edit('build.py',"            objects=[]","            if side=='P':\n                changes=instrument(dst/'src');write(art/'instrumentation.json',changes)\n            objects=[]")
edit('build.py',"need(sha(build/side/rel,sup.check)==row[side]['sha256'],'staged source changed')","expected=row['A']['sha256']\n                if side=='P' and row['module'] in changes: expected=changes[row['module']]['after_sha256']\n                need(sha(build/side/rel,sup.check)==expected,'staged source changed')")
edit('screen.py',"SEQUENCE=[('qual-A','A'),('profile-A','A')]","SEQUENCE=[('qual-A','A'),('profile-A','P')]")
edit('screen.py',"ap.add_argument('--a'); args=ap.parse_args()","ap.add_argument('--a'); ap.add_argument('--p'); args=ap.parse_args()")
edit('screen.py',"all([args.root,args.sources,args.a])","all([args.root,args.sources,args.a,args.p])")
edit('screen.py',"producers={'A':Path(args.a).resolve()}","producers={'A':Path(args.a).resolve(),'P':Path(args.p).resolve()}")
edit('screen.py',"for side in ['A']:","for side in ['A','P']:")
edit('screen.py',"{'graph_ms','load_ms','infer_ms','finish_ms','output_ms','publish_ms'}","{'graph_ms','load_ms','infer_ms','finish_ms','output_ms','publish_ms','raw_record_ms'}")
edit('screen.py',"row['phase_clock_sum_ms']=sum(phases.values())","need(phases['raw_record_ms']<=phases['infer_ms'],'nested record exceeds infer')\n                row['phase_clock_sum_ms']=sum(v for k,v in phases.items() if k!='raw_record_ms')\n                row['pre_record_residual_ms']=phases['infer_ms']-phases['raw_record_ms']")
edit('screen.py',"SEQUENCE==[('qual-A','A'),('profile-A','A')]","SEQUENCE==[('qual-A','A'),('profile-A','P')]")
p=dst/'remote-foundation-profile.yml';s=p.read_text().replace('remote-foundation-profile','remote-foundation-split').replace('main phase profile','main record-boundary profile').replace('Build exact main A,','Build main A and instrumented P,').replace('--a "$ROOT/producers/A/bin/emlf"','--a "$ROOT/producers/A/bin/emlf" --p "$ROOT/producers/P/bin/emlf"');(dst/'remote-foundation-split.yml').write_text(s);p.unlink()
