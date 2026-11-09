#!/usr/bin/env python3
"""Actual lowered QUERY4 and checked distribution public-entry controls.
Independent format expectations are fixed here; no learned target oracle.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path


def run_integration(fixture,output,run,record,typed,ref,shared_fixtures):
    def require(ok,message):
        if not ok:raise ValueError(message)
    def sha(raw):return hashlib.sha256(raw).hexdigest()
    def invoke(name,*args,**kw):return run(name,[fixture,*args],**kw)
    require(invoke('production-admission','admission')==b'PASS production-admission-distinct-from-raw-codec\n','production syntax-domain exact oracles')
    source_admission=output/'source-admission'
    require(invoke('source-admission','source-admission',source_admission)==b'PASS source-key-context-admission-and-priority\n','real schema301 emptycontext expectedDS/memo/priority regression')
    guarded_query=typed.inspect_artifact((source_admission/'record.mlfq').read_bytes(),2)
    guarded_root=guarded_query.values()[0]
    require(guarded_root[1]==301,'source admission record stays actual shared binary')
    reference=typed.text(guarded_root[2][0]);carrier=source_admission/('context-'+reference+'.mlfqc')
    require(sha(carrier.read_bytes())==reference,'source admission physical context SHA')
    guarded_context=typed.inspect_artifact(carrier.read_bytes(),1)
    require(typed.list_values(typed.value_node(guarded_context.values()[0],244,1)[0])==(),'source admission real empty typed context')
    record['source_admission']={'record_sha256':sha((source_admission/'record.mlfq').read_bytes()),'context_sha256':reference,
                                'scope':'unchanged full key; int-only body; only expectedDS changes; cold and genuine warm memo; missing/digest/mismatch priority; actual legacy CACHE3 own SHA'}
    base64_dir=output/'base64'
    require(invoke('base64','base64',base64_dir)==b'PASS canonical-base64\n','base64 fixture complete marker')
    require((base64_dir/'allbytes.base64').read_bytes()==base64.b64encode(bytes(range(256))),'base64 independent all-byte canonical encoding')
    lowered=output/'lowered';lowered.mkdir();cache=lowered/'cache'
    phases=[]
    def phase(name,value,inferred,reused,expected_formats=None):
        result=lowered/(name+'.objects')
        report=json.loads(invoke('lowered-'+name,'lowered-query',cache,result,str(value)))
        require(report['format']==1 and report['inferred_groups']==inferred and report['reused_groups']==reused,'lowered actual inference/reuse count '+name)
        keys=[row['query_key'] for row in report['groups']]
        require(len(keys)==2 and len(set(keys))==2,'lowered two exact query records')
        snapshot=typed.cache_snapshot(cache,keys)
        if expected_formats is not None:require(set(snapshot['active_records'].values())==set(expected_formats),'lowered exact physical formats '+name)
        require(not snapshot['reachable_contexts'],'lowered QUERY4 must not invent source-v6 context')
        require(not (cache/'query-key.new').exists(),'lowered scratch lifecycle')
        phases.append(dict(name=name,query_report=report,cache=snapshot,final_sha256=sha(result.read_bytes())))
        return keys,result.read_bytes()
    binary={'MLFBIN-QUERY-INLINE-1'}
    keys,cold=phase('cold',41,2,0,binary)
    _,warm=phase('warm',41,0,2,binary);require(warm==cold,'lowered exact cold/warm semantic artifacts')
    changed_keys,changed=phase('change',42,1,1,binary);require(changed!=cold,'lowered real value change')
    _,changed_warm=phase('changed-warm',42,0,2,binary);require(changed_warm==changed,'lowered changed warm semantics')
    for version in ('1','2'):
        target=cache/(changed_keys[0]+'.mlfq')
        require(invoke('lowered-install-'+version,'lowered-legacy',target,version)==('PASS lowered-install-CACHE'+version+'\n').encode(),'explicit old lowered format seed')
        _,mixed=phase('mixed-cache'+version,42,0,2,binary|{'MLF-QUERY-CACHE-'+version})
        require(mixed==changed,'old lowered record preserves exact raw/final meaning')
        # Corrupt only that old record, so the ordinary actual driver repairs it
        # to the default binary form; unrelated hit remains untouched.
        target.write_bytes(b'corrupt old cache')
        _,repaired=phase('repair-cache'+version,42,1,1,binary);require(repaired==changed,'lowered old record repair semantics')
    target=cache/(changed_keys[0]+'.mlfq');original=target.read_bytes()
    corrupted=bytearray(original);corrupted[8:12]=(2).to_bytes(4,'little');target.write_bytes(ref.repair_crc(corrupted))
    _,repaired=phase('identified-binary-corruption',42,1,1,binary)
    require(repaired==changed and target.read_bytes()==original,'identified binary cannot fallback and repairs canonical bytes')
    record['lowered_query']=phases

    seed=output/'distribution-seed'
    require(invoke('distribution-seed','distribution-seed',seed)==b'PASS actual-binary-library-and-legacy-formal\n','real Session binary library producer')
    require(invoke('open-interface-controls','open-interface-controls',seed)==b'PASS open-interface-context-closure-and-portable-paths\n',
            'actual supplied-interface closure and portable-path admission controls')
    binary_pair=((seed/'seed.mlfci').read_bytes(),(seed/'seed.mlfco').read_bytes())
    legacy_pair=((seed/'legacy.mlfci').read_bytes(),(seed/'legacy.mlfco').read_bytes())
    original_builtin_pair=((seed/'builtin.mlfci').read_bytes(),(seed/'builtin.mlfco').read_bytes())
    # The Session root uses the existing open ABI; the canonical builtin keeps
    # its original closed ABI. Neither physical expectation is autodetected.
    typed.inspect_crate_pair(*original_builtin_pair,4)
    typed.inspect_crate_pair(*binary_pair,7,[original_builtin_pair[0]])
    record['open_object_reader_controls']=typed.open_pair_controls(binary_pair,[original_builtin_pair[0]])
    require(not any(raw.startswith(ref.MAGIC) for raw in legacy_pair),'explicit old formal serialization really text')
    for variant in ('seed','legacy'):
        require(invoke('formal-'+variant,'formal-check',seed/variant,'accept')==b'PASS formal-accept\n','actual formal reader '+variant)
    # Same source compiled by GHC and the actual native compiler reads the
    # real Session-produced pair and republishes it through public storage APIs.
    for variant,source_pair,source_prefix,object_schema,dependencies,record_key in (
        ('',binary_pair,seed/'seed',7,[original_builtin_pair[0]],'shared_public_pairs'),
        ('-closed',original_builtin_pair,seed/'builtin',4,[],'shared_closed_public_pairs')):
        public_pairs={}
        for backend in ('shared-ghc','shared-native'):
            name=backend+variant+'-public-pair'
            destination=output/name;destination.mkdir();prefix=destination/'unit'
            result=run(name,[shared_fixtures[backend]],
                       ('formal\n'+str(source_prefix)+'\n'+str(prefix)+'\n').encode())
            require(result==b'PASS shared-public-binary-pair\n','public pair exact completion')
            require({p.name for p in destination.iterdir()}=={'unit.mlfci','unit.mlfco'},'public pair exact publication inventory/no staging')
            rows={}
            transferred=tuple(prefix.with_suffix(suffix).read_bytes() for suffix in ('.mlfci','.mlfco'))
            typed.inspect_crate_pair(*transferred,object_schema,dependencies)
            for schema,suffix,expected in zip((3,object_schema),('.mlfci','.mlfco'),source_pair):
                raw=prefix.with_suffix(suffix).read_bytes();doc=typed.inspect_artifact(raw,schema)
                require(raw==expected,'public native/GHC pair equals independently inspected original artifact bytes')
                rows[suffix]={'sha256':sha(raw),**doc.accounting()}
            public_pairs[backend]=rows
        require(public_pairs['shared-ghc']==public_pairs['shared-native'],'cross-host public pair identity')
        record[record_key]=public_pairs
    record['native_scope']='raw bytes, wire, typed Graph/raw admission, public full artifact pair; not native Session or Distribution'
    # A recognized new magic cannot be interpreted by a legacy parser on error.
    for schema,suffix in ((3,'.mlfci'),(4,'.mlfco'),(7,'.mlfco')):
        source_pair=original_builtin_pair if schema==4 else binary_pair
        bad=output/('formal-corrupt-'+str(schema));bad.mkdir()
        for extension,data in zip(('.mlfci','.mlfco'),source_pair):(bad/('unit'+extension)).write_bytes(data)
        damaged=bytearray((bad/('unit'+suffix)).read_bytes());damaged[8:12]=(2).to_bytes(4,'little')
        damaged=ref.repair_crc(damaged)
        (bad/('unit'+suffix)).write_bytes(damaged)
        if schema == 7:
            # Open admission authenticates the paired object SHA before parsing.
            # Rebind it so this control reaches the actual version check.
            fields=list(typed.value_node(typed.inspect_artifact(binary_pair[0],3).values()[0],242,13))
            fields[11]=typed.s(sha(damaged))
            (bad/'unit.mlfci').write_bytes(ref.tree_document([typed.n(242,*fields)],schema=3))
        family='interface' if schema==3 else 'object'
        require(invoke('formal-corrupt-'+str(schema),'formal-check',bad/'unit','reject-'+family+'-version')==('PASS formal-'+family+'-version-reject\n').encode(),'formal exact binary-version diagnostic; no legacy fallback')

    distro=output/'distribution';distro.mkdir();distribution=[]
    builtin_id='mlf:builtin-shared-haskell-v1:13';root_id='binary-package/1/library'
    identities=(builtin_id,root_id)
    def pair_at(prefix):return tuple(prefix.with_suffix(suffix).read_bytes() for suffix in ('.mlfci','.mlfco'))
    def interface_summary(pair,dependencies=()):
        metadata,body=pair
        if metadata.startswith(ref.MAGIC):
            interface,_=typed.inspect_crate_pair(metadata,body,typed.binary_object_schema(body),dependencies)
            fields=typed.value_node(interface.values()[0],242,13)
            dependencies=[tuple(typed.text(x) for x in typed.value_node(row,3,3)) for row in typed.list_values(fields[1])]
            return {'identity':typed.text(fields[0]),'dependencies':dependencies,
                    'modules':[typed.text(x) for x in typed.list_values(fields[2])],'entry':typed.text(fields[10])}
        require(not body.startswith(ref.MAGIC),'legacy pair must have two text artifacts')
        fields=typed.unpack(metadata.decode('utf-8','strict'))
        require(len(fields)==14 and fields[0]=='MLFCI-5','exact legacy interface framing')
        object_fields=typed.unpack(body.decode('utf-8','strict'))
        require(len(object_fields)==4 and object_fields[0]=='MLFCO-2' and object_fields[1]==fields[1],
                'exact complete projected legacy object framing/identity')
        dependencies=[tuple(typed.unpack(row)) for row in typed.unpack(fields[2])]
        require(all(len(row)==3 for row in dependencies),'legacy dependency triples')
        return {'identity':fields[1],'dependencies':dependencies,'modules':typed.unpack(fields[3]),'entry':fields[10]}
    original_summary=interface_summary(binary_pair,[original_builtin_pair[0]])
    require(original_summary['identity']==root_id and original_summary['modules']==['BinaryPackage'] and original_summary['entry']=='',
            'original real Session root identity/modules/no entry')
    original_dependencies=original_summary['dependencies']
    require(len(original_dependencies)==1 and original_dependencies[0][0]==builtin_id and
            original_dependencies[0][1]==str((seed/'builtin.mlfci').resolve()) and original_dependencies[0][2],
            'original real Session root exact builtin edge')
    semantic=original_dependencies[0][2]
    original_builtin_summary=interface_summary(original_builtin_pair)
    require(original_builtin_summary['identity']==builtin_id and original_builtin_summary['dependencies']==[] and
            original_builtin_summary['entry']=='' and 'Prelude' in original_builtin_summary['modules'] and
            'MLF.Primitive' in original_builtin_summary['modules'],'actual builtin leaf identity/dependency inventory')
    require(interface_summary(legacy_pair)==original_summary,'Session legacy export preserves complete dependency edge')
    published=seed/'release-binary'
    published_manifest=json.loads((published/'release.json').read_bytes())
    require([row['identity'] for row in published_manifest['crates']]==list(identities),'production release exact topological builtin/root order')
    binary_closure=tuple(pair_at(published/'crates'/row['key']/'unit') for row in published_manifest['crates'])
    legacy_closure=(pair_at(seed/'release-legacy-builtin'),pair_at(seed/'release-legacy-root'))
    def manifest_for(pairs,legacy):
        require(len(pairs)==2,'complete two-crate closure')
        keys=[sha(pair[0])+sha(pair[1]) for pair in pairs]
        require(len(set(keys))==2,'distinct leaf/root keys')
        summaries=[interface_summary(pairs[0]),interface_summary(pairs[1],[pairs[0][0]])]
        require([item['identity'] for item in summaries]==list(identities),'exact closure crate identities')
        require(summaries[0]==original_builtin_summary,'canonical builtin leaf full summary unchanged')
        require(summaries[1]==dict(original_summary,dependencies=[(builtin_id,'/__mlf_release__/'+keys[0]+'/unit.mlfci',semantic)]),
                'root depends on its own actual portable builtin byte key with unchanged semantic identity')
        require(all((not pair[0].startswith(ref.MAGIC) and not pair[1].startswith(ref.MAGIC)) if legacy
                    else (pair[0].startswith(ref.MAGIC) and pair[1].startswith(ref.MAGIC)) for pair in pairs),
                'both pairs have the exact intended binary/legacy representation')
        manifest={'format':1,'name':'binary-package','version':'1','compiler_sha256':sha(fixture.read_bytes()),
                  'no_prelude':True,'root':keys[1],'modules':['BinaryPackage'],
                  'crates':[{'key':key,'identity':identity,'metadata_sha256':sha(pair[0]),'object_sha256':sha(pair[1])}
                            for key,identity,pair in zip(keys,identities,pairs)]}
        raw=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
        return manifest,raw,keys
    binary_manifest,_,binary_keys=manifest_for(binary_closure,False)
    require(published_manifest==binary_manifest,'production Release.publish matches independent complete manifest')
    require(binary_closure[0]==original_builtin_pair,'production release preserves canonical builtin leaf bytes')
    expected_published={'release.json',*('crates/'+key+'/unit'+suffix for key in binary_keys for suffix in ('.mlfci','.mlfco'))}
    require({str(p.relative_to(published)) for p in published.rglob('*') if p.is_file()}==expected_published,
            'production release full five-file inventory, no hidden crate or staging')
    legacy_manifest,_,legacy_keys=manifest_for(legacy_closure,True)
    require(binary_keys[0]!=legacy_keys[0] and binary_keys[1]!=legacy_keys[1],'binary and legacy closure use distinct actual pair keys')
    def seed_bundle(name,pairs,legacy):
        manifest,raw,keys=manifest_for(pairs,legacy);directory=distro/name
        for key,pair in zip(keys,pairs):
            prefix=directory/'crates'/key/'unit';prefix.parent.mkdir(parents=True)
            for extension,data in zip(('.mlfci','.mlfco'),pair):prefix.with_suffix(extension).write_bytes(data)
        (directory/'release.json').write_bytes(raw)
        return directory,manifest,raw,keys
    source,manifest,manifest_raw,keys=seed_bundle('binary-source',binary_closure,False)
    key=keys[1];release_root_pair=binary_closure[1]
    asset=distro/'binary.mlfr'
    receipt=json.loads(invoke('distribution-pack-binary','distribution-pack',source,asset))
    require(receipt=={'sha256':sha(manifest_raw),'asset_sha256':sha(asset.read_bytes())},'public pack returns exact manifest and asset SHA')
    envelope=json.loads(asset.read_bytes());require(set(envelope)=={'format','manifest','crates'} and envelope['format']==2,'default checked release format2')
    require(envelope['manifest'].encode()==manifest_raw and [row['key'] for row in envelope['crates']]==keys,'manifest bytes and exact ordered two-crate inventory retained')
    for entry,pair in zip(envelope['crates'],binary_closure):
        require(set(entry)=={'key','metadata_base64','object_base64'},'closed binary envelope field set')
        for field,data in zip(('metadata_base64','object_base64'),pair):
            require(base64.b64decode(entry[field],validate=True)==data and base64.b64encode(data).decode()==entry[field],'both complete pairs exact canonical base64')
    entry=envelope['crates'][1]
    require(entry['key']==key,'explicit root target for all payload mutations')
    def unpack_case(name,env,expected_digest,pairs=None,error=None,legacy=False):
        case=distro/name;case.mkdir();source=case/'asset.mlfr';source.write_text(json.dumps(env,ensure_ascii=False,separators=(',',':'))+'\n')
        destination=case/'bundle'
        if error is not None:
            invoke('distribution-'+name,'distribution-unpack',source,destination,expected_digest,
                   expected_status=1,expected_stderr=('mlfpkg: '+error+'\n').encode())
        else:
            decoded=json.loads(invoke('distribution-'+name,'distribution-unpack',source,destination,expected_digest))
            wanted=json.loads(env['manifest']);independent,_,wanted_keys=manifest_for(pairs,legacy)
            require(wanted==independent and decoded==wanted,'unpack exact independently checked full manifest')
            actual_pairs=[]
            for row,pair in zip(wanted['crates'],pairs):
                prefix=destination/'crates'/row['key']/'unit'
                actual=pair_at(prefix);require(actual==pair,'unpack both full raw artifact pairs byte-for-byte');actual_pairs.append(actual)
            manifest_for(actual_pairs,legacy)
            actual={str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
            require(actual=={'release.json',*('crates/'+k+'/unit'+suffix for k in wanted_keys for suffix in ('.mlfci','.mlfco'))},'unpack exact five-file two-crate physical inventory')
            prefix=destination/'crates'/wanted['root']/'unit'
            require(invoke('distribution-'+name+'-formal','formal-bundle-check',destination)==b'PASS formal-accept\n','unpacked complete portable closure typed reader and linker')
        distribution.append({'name':name,'asset_sha256':sha(source.read_bytes()),'expected_manifest_sha256':expected_digest,
                             'expected_outcome':'reject' if error else 'accept','error_oracle':error})
    unpack_case('format2-roundtrip',envelope,sha(manifest_raw),binary_closure)
    _,old_manifest,old_raw,old_keys=seed_bundle('legacy-source',legacy_closure,True)
    legacy_envelope={'format':1,'manifest':old_raw.decode(),'crates':[{'key':k,'metadata':pair[0].decode('utf-8'),'object':pair[1].decode('utf-8')} for k,pair in zip(old_keys,legacy_closure)]}
    unpack_case('format1-compatibility',legacy_envelope,sha(old_raw),legacy_closure,legacy=True)
    legacy_asset=distro/'legacy-repacked.mlfr'
    legacy_receipt=json.loads(invoke('distribution-repack-legacy','distribution-pack',distro/'legacy-source',legacy_asset))
    legacy_repacked=json.loads(legacy_asset.read_bytes())
    require(set(legacy_repacked)=={'format','manifest','crates'} and legacy_repacked['format']==2 and
            legacy_repacked['manifest'].encode()==old_raw and [row['key'] for row in legacy_repacked['crates']]==old_keys and
            legacy_receipt=={'sha256':sha(old_raw),'asset_sha256':sha(legacy_asset.read_bytes())},'format2 repack preserves complete legacy closure and pins')
    for row,pair in zip(legacy_repacked['crates'],legacy_closure):
        require(set(row)=={'key','metadata_base64','object_base64'},'legacy repack closed fields')
        for field,data in zip(('metadata_base64','object_base64'),pair):
            require(base64.b64decode(row[field],validate=True)==data and base64.b64encode(data).decode()==row[field],'repack preserves both old artifact pairs and canonical base64')
    unpack_case('format2-old-pair',legacy_repacked,sha(old_raw),legacy_closure,legacy=True)
    wrong=copy.deepcopy(envelope);wrong['format']=3
    unpack_case('wrong-version',wrong,sha(manifest_raw),error='unsupported checked release asset format')
    missing=copy.deepcopy(envelope);missing['crates']=[]
    unpack_case('missing-crate',missing,sha(manifest_raw),error='release asset crate inventory mismatch')
    duplicate=copy.deepcopy(envelope);duplicate['crates']*=2
    unpack_case('duplicate-crate',duplicate,sha(manifest_raw),error='release asset crate inventory mismatch')
    extra=copy.deepcopy(envelope);extra['crates'].append(dict(entry,key='a'*128))
    unpack_case('extra-crate',extra,sha(manifest_raw),error='release asset crate inventory mismatch')
    escaping=copy.deepcopy(envelope);escaping['crates'][1]['key']='../escape'
    unpack_case('escaping-key',escaping,sha(manifest_raw),error='invalid release asset crate key')
    unknown=copy.deepcopy(envelope);unknown['extra']=True
    unpack_case('unknown-envelope-field',unknown,sha(manifest_raw),error='checked release asset: unknown field extra')
    mixed=copy.deepcopy(envelope);mixed['crates'][1]['metadata']='legacy text in binary envelope'
    unpack_case('mixed-payload-fields',mixed,sha(manifest_raw),error='release asset crate: unknown field metadata')
    unpack_case('manifest-pin',envelope,'0'*64,error='release asset manifest SHA-256 mismatch')
    for name,text,error in [('base64-padding','Zh==','noncanonical release base64'),('base64-length','Zg=','invalid release base64 length')]:
        malformed=copy.deepcopy(envelope);malformed['crates'][1]['metadata_base64']=text
        unpack_case(name,malformed,sha(manifest_raw),error=error)
    for index,(field,suffix) in enumerate((('metadata_base64','.mlfci'),('object_base64','.mlfco'))):
        name='payload-'+('metadata' if index==0 else 'object')+'-sha'
        poisoned=copy.deepcopy(envelope);changed=bytearray(release_root_pair[index]);changed[-1]^=1
        poisoned['crates'][1][field]=base64.b64encode(changed).decode('ascii')
        require(base64.b64decode(poisoned['crates'][1][field],validate=True)==bytes(changed),'poison stays valid canonical base64 transport')
        require(poisoned['manifest']==envelope['manifest'] and poisoned['crates'][1]['key']==key and poisoned['crates'][0]==envelope['crates'][0],'root payload-only mutation retains manifest/key/builtin pins')
        expected_path=distro/name/'bundle'/'crates'/key/('unit'+suffix)
        unpack_case(name,poisoned,sha(manifest_raw),error='release artifact digest mismatch: '+str(expected_path))
    for label,digest in [('valid',sha(asset.read_bytes())),('invalid','0'*64)]:
        require(invoke('distribution-asset-'+label,'distribution-asset',asset,digest,label)==b'PASS distribution-asset-pin\n','actual asset SHA validator')
    record['release_closure']={'identities':identities,'binary_keys':binary_keys,'legacy_keys':legacy_keys,
                             'original_session_dependencies':original_dependencies,'production_published_manifest':published_manifest,
                             'scope':'complete canonical builtin plus original Session library; binary and legacy independently relocated to their own actual byte keys'}
    record['distribution']=distribution
    record['distribution_physical_inventory']=ref.physical_inventory(distro)

    require(invoke('release-builtin-branches','release-builtin-branches',seed)==b'PASS release-canonical-builtin-paths-ownership-binary-legacy\n',
            'current builtin binary/legacy verify and all exact ownership/path branch oracles')
    require(invoke('release-forged-current','release-forged-current',seed,expected_status=1,
                   expected_stderr=b'mlfpkg: release contains a noncanonical builtin Prelude\n')==b'PASS release-forged-current-fully-typed\n',
            'same-current noncanonical object must pass ordinary full type linking before exact canonicality refusal')
    compiler_digest=sha(fixture.read_bytes());install_cache=distro/'materialized-cache'
    expected_root=install_cache/'.releases'/compiler_digest/key
    installed_prefixes=[install_cache/'.queries/builtin-prelude'/compiler_digest/'unit',expected_root/'unit']
    receipt_path=install_cache/'.releases/verified'/(sha(manifest_raw)+'-'+compiler_digest+'.json')
    saved_materialized=None
    for phase_name in ('cold','warm'):
        result=invoke('release-materialize-'+phase_name,'release-materialize',source,sha(manifest_raw),install_cache,compiler_digest)
        require(result==(str(expected_root)+'\n').encode(),'public materialize returns exact ordinary root path')
        actual_pairs=[pair_at(prefix) for prefix in installed_prefixes]
        require(actual_pairs[0]==binary_closure[0],'materialize installs exact canonical builtin into dedicated compiler cache')
        expected_installed_root=dict(original_summary,dependencies=[(builtin_id,str(installed_prefixes[0])+'.mlfci',semantic)])
        require(interface_summary(actual_pairs[1],[actual_pairs[0][0]])==expected_installed_root,'materialized root relocates exact local dependency and remains typed')
        expected_files={str(prefix)+suffix:sha(data) for prefix,pair in zip(installed_prefixes,actual_pairs) for suffix,data in zip(('.mlfci','.mlfco'),pair)}
        saved=json.loads(receipt_path.read_bytes())
        require(saved=={'format':1,'release':sha(manifest_raw),'validator_sha256':compiler_digest,'files':expected_files},
                'public materialization verified receipt binds all four exact installed files and current validator')
        physical={str(p) for p in install_cache.rglob('*') if p.is_file() and p.suffix in ('.mlfci','.mlfco')}
        require(physical==set(expected_files),'exact installed artifact population and canonical builtin destination')
        # Byte equality alone does not prove receiptValid took the warm path:
        # a reconstruction may reproduce those same bytes. Exclude atime only,
        # since successful verification legitimately reads these five files.
        retained_paths=[Path(name) for name in sorted(expected_files)]+[receipt_path]
        retained_stats={}
        for path in retained_paths:
            info=path.lstat()
            require(not path.is_symlink() and path.is_file(),'retained installed artifact/receipt must be regular')
            retained_stats[str(path)]=[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
        state={'files':expected_files,'receipt_sha256':sha(receipt_path.read_bytes()),
               'retained_lstat_without_atime':retained_stats}
        if phase_name=='cold':saved_materialized=state
        else:require(state==saved_materialized,'warm receiptValid reuses exact four objects and verified receipt without rewrite')
    record['release_authority_regressions']={'commands':4,'canonical_binary_and_legacy_verified':True,
        'old_and_forged_owners_rejected':True,'noncanonical_current_object_fully_typed_then_rejected':True,
        'cold_warm_materialization':saved_materialized}
    record['distribution_physical_inventory']=ref.physical_inventory(distro)
