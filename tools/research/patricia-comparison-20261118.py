import hashlib, json, os, pathlib, subprocess, types
# Predeclare a new same-machine epoch BEFORE producing any candidate.
import sys, copy, stat
HISTORICAL_TOOLCHAIN = {'actual_ghc': {'path': '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-9.14.1', 'sha256': '26628fcfe6f3f7176e5c8fc1766fe19b196e7922ff5d812e4c96bc146ae7dc92'}, 'files': {'/home/runner/work/_temp/ghc/bin/ghc-9.14.1': '38115f3ce136434725893c3e009f1c1c510f3f48ac32a293befbb79bbec34697', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-9.14.1': '26628fcfe6f3f7176e5c8fc1766fe19b196e7922ff5d812e4c96bc146ae7dc92', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-iserv-dyn-ghc-9.14.1': '4b918897ccb3e1eb62bee4931ae722e83ae3ebeb157a37da5cea2529ea951a13', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-iserv-ghc-9.14.1': 'feec56c48b9173f9b9e083397cf2afacc069eadb7a2b8546b722c7b429e03ed6', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-iserv-prof-ghc-9.14.1': '2705d2470fe1aa62e3427fdecb3dbc4f61b1cce5c55e2cf3c75bd8931cb00a86', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-pkg-9.14.1': 'e658d6fc5575046d4b15ece548ddbc3dd512b7885b1d8dae1817a8f3199e55bb', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/ghc-toolchain-bin-ghc-9.14.1': 'd9b96452c1ec6c74f7304d4979dfb8acf666c4439ff4b92da45f4b12d38f0c74', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/haddock-ghc-9.14.1': 'b97c674fb509858269dddeac6c990835ff78f9ae33cf201549321ba568724576', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/hp2ps-ghc-9.14.1': 'ba7c55c5d9f76b48479509e6d359e87b0f6fc5989073a90430d2db507d38323a', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/hpc-ghc-9.14.1': '59b3d65351a2bb00237f500ecd44050f9160a61ade9a7755e27a443b8d65dbc7', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/hsc2hs-ghc-9.14.1': 'd5ec68073266b06ef4e6eeb35e1fed2473101c8faeef687fbd91c58ebb3398c2', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/runghc-9.14.1': '43b7d4058560d216123f9f51320ceb215c7712bc1be880455c0a21ca079ad1b6', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/bin/unlit-ghc-9.14.1': 'eca6abd22cf4dcbc13c12150c6ce44a00c99f7711a8d15442a7d0f2bd7bdfeb3', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSCabal-3.16.0.0-d85b-ghc9.14.1.so': 'a4d1e92e122e4fd658724138dd95bd0f213035e219bd51d429ab3d7661ef698b', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSCabal-syntax-3.16.0.0-a87d-ghc9.14.1.so': 'ca71202ccaf23c32c53406f7f4646cf22043f4e584b0e53e72fe1c7f52b3387e', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSarray-0.5.8.0-93e8-ghc9.14.1.so': 'b2a29948b09601722b224e62e6221d08843fe4e90312e6e0e7e017b532cf70c0', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSbase-4.22.0.0-66f8-ghc9.14.1.so': '24278e30312c2e918578482f1a8f573a8119dc06d2af26df2ac4a23893a96914', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSbinary-0.8.9.3-0d14-ghc9.14.1.so': '44f837f7e0c50a3d653c819b4e77ea4356c2a340fde57d771cc5a214e243f495', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSbytestring-0.12.2.0-f1bc-ghc9.14.1.so': '844044fec7c50e765f2bf08b646665be995d26c26aab6b8ca824aa0543ea71f5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHScontainers-0.8-9e90-ghc9.14.1.so': 'e1806b7750503cbc46926c6668faa2ee5ee835db9ee774c278e17f59afa4c8e5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSdeepseq-1.5.1.0-2129-ghc9.14.1.so': '2ceb8895694351aaff479e335ae9684a91a0f1eef9cc15f2e5ce48f9618f46d4', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSdirectory-1.3.10.0-b291-ghc9.14.1.so': '8a0fd6b71ddf7e0959eb35d80170c02a1e5bbbe9e65eecbe589b56baddc8db46', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSexceptions-0.10.11-e9cb-ghc9.14.1.so': '3e4b969188c4ad94cca3a13bc59e9307977de3f5fd1dde5c54611ab07db879a9', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSfile-io-0.1.5-525e-ghc9.14.1.so': 'e48e25b84c5405bd6ddf69305eac6d2783ee943befdffdff2a3aa00f8d7c0217', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSfilepath-1.5.4.0-bbe0-ghc9.14.1.so': '3a69622ad303dc3c7150606d369655263f28e066deaed9b005d18840c6b7d504', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-9.14.1-da80-ghc9.14.1.so': '468215948002a19d082ac3948830bda180ef2a4b0582dcca03f73186fa77a3a5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-boot-9.14.1-16fe-ghc9.14.1.so': 'c60cd92ab36e4b9f7645e1b776ca30b1213c852c39d6c6f1a786d0d375b485b8', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-boot-th-9.14.1-1fb7-ghc9.14.1.so': '4fadfb6b3c26f2608ca5b6ebc007a1afbcc40988aa68bcde7a4f6403a0ff79a7', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-heap-9.14.1-df45-ghc9.14.1.so': 'fca5124f41a36bda34df4d04c023ca9efe55ec04ac9fccf88a5765f5dc22acbe', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-internal-9.1401.0-555c-ghc9.14.1.so': '7a6a54b03ea49b7ea5b50a452435d32eac3469f88ba00b91edac2caa2e9726b5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-platform-0.1.0.0-ea57-ghc9.14.1.so': '03f9fd8678d0aece81864f0f246e82e983e1d9d6eea41995ea7b72627c54e29d', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-prim-0.13.1-d287-ghc9.14.1.so': 'e4b2405ab98d3bc917f31bd0b669bbe33497b874e807d65541601a0585e1aa60', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghc-toolchain-0.1.0.0-914f-ghc9.14.1.so': '8189cb7f861f05cff64db38e6fcebd5ce576039c3880f742761bc13f43d80fa5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSghci-9.14.1-0d23-ghc9.14.1.so': '925edfb58b87ad21e52488235e8884fe5f0a094b286d0d4ea2ca6258b52aea9a', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHShaddock-api-2.33.0-c1d4-ghc9.14.1.so': '620748ecfa5aa083ff148d54c75e13033d79fede2dad32ea01d7e175efe48e15', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHShaddock-library-1.11.0-0420-ghc9.14.1.so': '123cc3289977701ef71c0bd115548b7f325eece2e6a9f928c8fda53dbc04ae62', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHShaskeline-0.8.3.0-bf9e-ghc9.14.1.so': 'ac6fecdd32b408fe7c5ace1a50b623259166586b6c71a97c59a0aa1018b51432', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHShpc-0.7.0.2-bfd5-ghc9.14.1.so': 'f1c659fef07e29125ef0c52b87e04026fd716900d61dbef75b3f251a542e2641', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSmtl-2.3.1-77f5-ghc9.14.1.so': '0b43016e2b4001b5cba843e5b3d9799ad4ecb991c5e6d75a62fe48e33b076166', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSos-string-2.0.8-4a54-ghc9.14.1.so': '60cecbd7a2764da4e259221f04aedaf69bd008aa49c3c238b5cc256209c1dfc9', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSparsec-3.1.18.0-9806-ghc9.14.1.so': '3062d3e29e83492b2a8f432ae4cbcb819d4c493e7c888351f50d914db4c76e17', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSpretty-1.1.3.6-72f5-ghc9.14.1.so': '0ea26be9213f729a88776522e24f0ea59b67b1f5a0e2ad42ac7d8e8e4764d592', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSprocess-1.6.26.1-e91f-ghc9.14.1.so': 'dadcf0eee05a68f22327a9274f73c9473de04264c4004d9778afcf198fcc883e', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSrts-1.0.3-ghc9.14.1.so': '4a66d53f58410165c16f5d6edc53b1d923ec0ccc86a8138e3f8fb93486fc3eaf', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSrts-1.0.3_thr-ghc9.14.1.so': '5c2b8a9a839b0e0bc9d81d2754bcad74a452906575c3eeacd2a30dc5c7c4d137', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSsemaphore-compat-1.0.0-add5-ghc9.14.1.so': '631c520c36fa02d0dd7b90ea94890f1ef53149b7b8e367af71e9f8d9537d44eb', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSstm-2.5.3.1-8f1a-ghc9.14.1.so': '65a7bad90f35207e141dd4c4867e2478f60df85ad8d6849bbadb148ad4944a71', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHStemplate-haskell-2.24.0.0-7769-ghc9.14.1.so': '15918581a1134ea21299cd1c6b0740f74371dfe16ae9baad76b01f825b75d2ef', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSterminfo-0.4.1.7-5cba-ghc9.14.1.so': 'c7aae2f2bbf204adc683319b6d05d789fe3aa9fcfffc04f7611050675fba2926', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHStext-2.1.3-075e-ghc9.14.1.so': 'bb8a8277ea4e3242cd90352a4dbaf9bf738b9d3e3d72cc544a2aa032fde10529', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHStime-1.15-2842-ghc9.14.1.so': 'f4fe78e9cffae70f59fe6011b1ce619cbe15364cc15f8b886cc0d24ad73ebf69', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHStransformers-0.6.1.2-53bb-ghc9.14.1.so': '279ad77bda6147aa3e616a39648e75642c8757f38660b3efb2ff09494982e790', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSunix-2.8.8.0-98c9-ghc9.14.1.so': '30fa47611eada0176a2815919f606a418248c995646826e674d374cb77c40695', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libHSxhtml-3000.2.2.1-36c7-ghc9.14.1.so': '250a813d51bc24b66bc1e75da04c8801e17a26efeedc007a84f075faac5a35b5', '/home/runner/work/_temp/ghc/lib/ghc-9.14.1/lib/x86_64-linux-ghc-9.14.1-2d39/libffi.so.8': 'cf3e47fba6aabf37c350e84927f5f50a0490757fc5c3ce6f8b456efff4de8057', '/usr/bin/false': 'e51fc98d1215569a555c03c991835c234d6f05ded01a23ae99a33b8854270e86', '/usr/bin/x86_64-linux-gnu-ar': '6452af2eea333b8c65e1adb92964fc8f97863ab003fa13f9d12bff5345cd7dbe', '/usr/bin/x86_64-linux-gnu-as': '21aff249b692b5c31a44007491f922dcb49f41323e362c57d2ada3f52eddb7f0', '/usr/bin/x86_64-linux-gnu-g++-13': '1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769', '/usr/bin/x86_64-linux-gnu-gcc-13': '1b99826121ae6682a634e5efe09bd3e3df58ce58e0b28f849114ab5b89139c26', '/usr/bin/x86_64-linux-gnu-ld.bfd': 'e9ceb054c12207970f2726dfc07e9a66b411602748628baf27399f02a9bbb31b', '/usr/bin/x86_64-linux-gnu-ld.gold': '1083eca2c464601fae4b561b1c240e7f787543261891229eebe0b112801c1e13', '/usr/bin/x86_64-linux-gnu-ranlib': '60254978b8ee2c1b21b41d16a18a621dbbcc72e43eb2fa9f916818256c77e9ee', '/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2': '5fc0940888e9d2e1a00e66d6b1a559c36364ee867683652e1074fa576952cc3f', '/usr/lib/x86_64-linux-gnu/libbfd-2.42-system.so': '11f084bc6ff5fc64e91c0b6422040fab1245419e7ff29560a95c1176ce1b9ff4', '/usr/lib/x86_64-linux-gnu/libc.so.6': '755a371e86cc9f564ab54f66140747700fb0a103f698f659f2060f707897e09a', '/usr/lib/x86_64-linux-gnu/libctf.so.0.0.0': '25c8f765c259d05b59a3dc3634d711912a7f5ce9be8a28ace081507b925b3ad1', '/usr/lib/x86_64-linux-gnu/libgcc_s.so.1': 'd93224d2b0dab4247598be683adca02f5cf00586f99c187579cd7e92058fb7cb', '/usr/lib/x86_64-linux-gnu/libgmp.so.10.5.0': '0ccdfb6d6f5c039465f6d002cf7e4c072d48ac6a2cffc8dd6c748dec31592804', '/usr/lib/x86_64-linux-gnu/libisl.so.23.3.0': 'db4f717fd1678b48e5dddea1cbdd2d239594a70b57e96d0923bfd9533351efa8', '/usr/lib/x86_64-linux-gnu/libjansson.so.4.14.0': 'c49935a4b3ac599064281b1f257576087806d0dad7ec46f353bd983b052c5e26', '/usr/lib/x86_64-linux-gnu/libm.so.6': '5dcc4d25466e29ca390ed6fabb371c69b65dff6fa4e91c34561057a020d6994a', '/usr/lib/x86_64-linux-gnu/libmpc.so.3.3.1': '91d2b2b0b794028c733431e01acc227ff39ee289384fdf22869c8b42ad3aaa3b', '/usr/lib/x86_64-linux-gnu/libmpfr.so.6.2.1': '2156351fa3dedd04a7381c6ac7a8a26efa2d6fb08b80f8a2d644ccdd653710ae', '/usr/lib/x86_64-linux-gnu/libsframe.so.1.0.0': '1693a2dbd77c909d279ae34aa9b5d8d08d97f116f8d0ed724063df11151b3c69', '/usr/lib/x86_64-linux-gnu/libtinfo.so.6.4': 'e6089d7bb95eee5b545f3770dd69095b0bca47d26701cad145af429561d16306', '/usr/lib/x86_64-linux-gnu/libz.so.1.3': 'f61677c7bdb7c2aa2a243ea781bfd16afcb361cede7b4ef76127a9d8eb9a5242', '/usr/lib/x86_64-linux-gnu/libzstd.so.1.5.5': '0a2128bc10841fb29e76d08d945864dfb0b6a66da5df6df5d8299197439e54bb', '/usr/libexec/gcc/x86_64-linux-gnu/13/cc1': '5d1679131184e2de4435b426eb264bf13472fe026db8e5c6bc97445814e8e2f4', '/usr/libexec/gcc/x86_64-linux-gnu/13/collect2': '4d1f341ae5b763b513258ee2812422a45e063c30a2f1924a0cf63d3699f3a158'}}
VARIABLE_EPOCH_PATHS=('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib/x86_64-linux-gnu/libc.so.6','/usr/lib/x86_64-linux-gnu/libm.so.6')
RUNTIME_PATHS=set(VARIABLE_EPOCH_PATHS)|{'/usr/lib/x86_64-linux-gnu/libgmp.so.10.5.0'}
LOCK=pathlib.Path('evidence/prebuild-toolchain-lock.json')
def digest_path(p):
    with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def measured_file(p):
    p=pathlib.Path(p);before=p.stat()
    if str(p.resolve(strict=True))!=str(p) or not stat.S_ISREG(before.st_mode):raise RuntimeError('unknown file topology '+str(p))
    h=digest_path(p);after=p.stat()
    metadata=lambda x:dict(bytes=x.st_size,mtime_ns=x.st_mtime_ns,ctime_ns=x.st_ctime_ns,device=x.st_dev,inode=x.st_ino,mode=x.st_mode)
    if metadata(before)!=metadata(after):raise RuntimeError('file changed during measurement '+str(p))
    return dict(path=str(p),sha256=h,**metadata(after))
def freeze_prebuild():
    if LOCK.exists():raise RuntimeError('existing epoch lock cannot be overwritten')
    if not os.environ.get('GITHUB_RUN_ID') or not os.environ.get('ImageVersion'):raise RuntimeError('missing epoch metadata')
    assert len(HISTORICAL_TOOLCHAIN['files'])==80 and set(VARIABLE_EPOCH_PATHS)<=set(HISTORICAL_TOOLCHAIN['files'])
    actual={p:measured_file(p) for p in HISTORICAL_TOOLCHAIN['files']}
    for p,h in HISTORICAL_TOOLCHAIN['files'].items():
        if p not in VARIABLE_EPOCH_PATHS and actual[p]['sha256']!=h:raise RuntimeError('nonpermitted toolchain change '+p)
    expected=copy.deepcopy(HISTORICAL_TOOLCHAIN)
    for p in VARIABLE_EPOCH_PATHS:expected['files'][p]=actual[p]['sha256']
    data=dict(format='patricia-prebuild-live-cohort-v1',run_id=os.environ['GITHUB_RUN_ID'],image=os.environ['ImageVersion'],allowed_variable_paths=list(VARIABLE_EPOCH_PATHS),expected_toolchain=expected,files=actual)
    LOCK.parent.mkdir(exist_ok=True)
    with LOCK.open('x') as f:json.dump(data,f,sort_keys=True,indent=2)
    with open(os.environ['GITHUB_ENV'],'a') as f:f.write('PATRICIA_PREBUILD_LOCK_SHA256='+digest_path(LOCK)+'\n')
    print('Frozen 80 toolchain files; only three predeclared paths may differ from historical cohort.')
def read_lock():
    if digest_path(LOCK)!=os.environ.get('PATRICIA_PREBUILD_LOCK_SHA256'):raise RuntimeError('prebuild lock changed')
    lock=json.loads(LOCK.read_text())
    if lock['format']!='patricia-prebuild-live-cohort-v1':raise RuntimeError('unknown lock format')
    if lock['run_id']!=os.environ['GITHUB_RUN_ID'] or lock['image']!=os.environ['ImageVersion']:raise RuntimeError('wrong cohort identity')
    if lock['allowed_variable_paths']!=list(VARIABLE_EPOCH_PATHS) or set(lock['files'])!=set(HISTORICAL_TOOLCHAIN['files']):raise RuntimeError('unknown inventory')
    expected=copy.deepcopy(HISTORICAL_TOOLCHAIN)
    for p in VARIABLE_EPOCH_PATHS:expected['files'][p]=lock['files'][p]['sha256']
    if lock['expected_toolchain']!=expected:raise RuntimeError('unapproved toolchain delta')
    return lock
def verify_all_locked_files():
    lock=read_lock()
    for p,row in lock['files'].items():
        if measured_file(p)!=row:raise RuntimeError('prebuild file changed '+p)
if sys.argv[1:]==['--freeze-prebuild']:
    freeze_prebuild();raise SystemExit(0)
if sys.argv[1:]:raise RuntimeError('unexpected arguments')
prebuild_lock=read_lock()

ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence'; OUT.mkdir(exist_ok=True)
def load(path):
    m=types.ModuleType(path.stem);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
pins={'old':'d8325d909c249fd82d4ad6173d44d8818cc6f8bf','new':'ee495d5783fca3c26a3c0e659ebeac1bab76a37d'}
BASE={'old':'old','new':'new','old_swap':'old','new_swap':'new'}
DONOR={'old_swap':'new','new_swap':'old'}
surface='libraries/mlf-frontend/Bootstrap/Surface.hs'
literal='bootstrap/MLF/BuiltinPreludeData.hs'
expected_identity={'old_swap':'builtin-source-v1:b43c5ddf9224142d296b984833de88528272e318f53fa6203614cd9576c7abae','new_swap':'builtin-source-v1:3e12091e64154a07bfd2e0423383cdcedcd509f980c656ca5352a7b481faaa21'}
surf_blobs={'old':'3e8082684587d25915d7f209bbf74d32e7c3dcc7','new':'a11262a585792e391d02e379e11e233af627fff0'}
roots={k:(ROOT/k).resolve() for k in BASE}
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
H=load(roots['new']/'tools/performance/a1-private-index/helper.py')
limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
record={'complete':False,'scope':'type-only bounded same-runner diagnosis; not semantic or speed qualification','pins':pins,'limits':limits,'legs':[],'host':H.host()}
def save(): (OUT/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
save()
fixture=None
for label,root in roots.items():
    head=git(root,'rev-parse','HEAD');base=pins[BASE[label]]
    if label in DONOR:
        assert git(root,'show','-s','--format=%P',head)==base
        assert git(root,'diff','--name-only',base,head).splitlines()==sorted([surface,literal])
        assert git(root,'rev-parse','HEAD:'+surface)==surf_blobs[DONOR[label]]
    else:assert head==base and git(root,'rev-parse','HEAD:'+surface)==surf_blobs[label]
    assert git(root,'status','--porcelain','--untracked-files=no')==''
    assert not git(root,'diff','--name-only','HEAD')
    producer=root/'.mlf-build/shared-ghc'
    H.authenticate(producer,root)
    if label in DONOR:
        fresh=OUT/(label+'-generated-literal.hs')
        gr=json.loads((OUT/(label+'-generation-receipt.json')).read_text())
        vr=json.loads((producer/'builtin-verification'/'receipt.json').read_text())
        assert gr['complete'] and gr['generation_succeeded'] and gr['immutable_inputs_verified_after']
        assert gr['source_identity']==vr['source_identity']==expected_identity[label]
        assert vr['complete'] and vr['exact_regeneration'] and vr['candidate_verified']
        assert fresh.read_bytes()==(root/literal).read_bytes() and gr['commands'][0]['stdout']['sha256']==sha(fresh)
        assert vr['canonical']['sha256']==vr['commands'][1]['stdout']['sha256']==sha(fresh)
    text,wanted,_,_=load(root/'tools/performance/patricia/run_native.py').fixture('rank-views')
    if fixture is None: fixture=text
    assert fixture==text
    record[label]={'binary_sha256':sha(producer/'bin/emlf'),'receipt_sha256':sha(producer/'receipt.json')}
entry=OUT/'Main.hs';entry.write_text(fixture);record['fixture_sha256']=sha(entry);save()

# No compiler or fixture changes. Both control legs must reproduce before observation.
import inspect,time,resource
ref_bins={'old':'d90ecca441c0c1a00c224639b335124ec4802d97f99e7d44eea9ccce3a715c8d','new':'8845fbb4729e555157c2cd3ca45d2981741bf8308bbdbef6ece74c85a5d90245'}
assert record['fixture_sha256']=='e7bc0d6bdd6ec6ac1a7d9b2cd6f71cb398c430f3029c870057d096efff2aaa82'
locked_inputs={"old":{"object_inputs":"3d4e55562e15482eb19265820d648d8f7fe261e4700c585bdd4fe02228d7b779","resolved_modules":"dc980d404188953009eba29c04a7fa856be709708e04923fcfd6416e73da7ae8","resolved_host_modules":"f6bb370236c702e1282baca2ada46b5944df522bb1eca16a28ca5f4980d35d7f","configuration_inputs":"ec04b1382d64c5b43ffa6ffd2b663e1d94e216006526695fef1d28869cb36501","shared_inputs":"1c1b747c167c5936b8856e89d0280789622d4538173a93306464a2ae04b8d2f0","host_inputs":"a8a09986e2e01b941741151e12e7a2cbf8665996bb6d53f78561b556cfa28e04","flags":"50e344ad68ebb24127b0b8e73be203817bc964f033bcf3fbcf1d43afe166258f","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"ac75b1bd6f94190ba6e09c5d687876f57d229bf992a3678fe2104e311814ddfa"},"new":{"object_inputs":"26215720f9596e5462c611c0254498fd8c1a4ede4b6b9281666c28d40c41243a","resolved_modules":"2a65c9034307623cc7d411925648209d56021b9657e01341b9768259b6f46a6a","resolved_host_modules":"7d6328f49a88fc532323ac3be760d3ff3fa37bcee9fb50bd395650d664de8b1e","configuration_inputs":"d14ae947e683961893ca57020002c71042fa797a69dd1a63eb890994aa5179cd","shared_inputs":"36c769215036a3f72d32d82b54193304a291930b2e967dff63cbc10509927bdb","host_inputs":"ea210294596583ac33ff4dbedb5d5e82a0c4c30d7a48cf9d31a962f2bd9c3694","flags":"0f373f3be1a95bf7d1a0a00fcd9e8dc6be3435188249f2f67ad23208db703e8c","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"ac75b1bd6f94190ba6e09c5d687876f57d229bf992a3678fe2104e311814ddfa"}}

import re
# This is an independent new-host experiment, not the historic executable cohort.
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def file_sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
current_epoch_files={p:prebuild_lock['files'][p]['sha256'] for p in RUNTIME_PATHS}
def runtime_manifest(exe):
    # Use the trusted, just-built program and clean loader environment. Identify ELF interpreter and ELF runtime closure.
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise RuntimeError('nonempty loader override')
    env=dict(os.environ,LC_ALL='C'); listing=subprocess.check_output(['/usr/bin/ldd',str(exe)],text=True,env=env,timeout=15)
    if 'not found' in listing:raise RuntimeError('unresolved dependency')
    files={}
    for line in listing.splitlines():
        line=line.strip()
        if not line or line.startswith('linux-vdso.'):continue
        v=line.split('=>',1)[-1].strip().split(' (0x',1)[0]
        if not v.startswith('/'):raise RuntimeError('unexpected ldd row')
        p=pathlib.Path(v).resolve(strict=True)
        files[str(p)]={'sha256':file_sha(p),'bytes':p.stat().st_size}
    ph=subprocess.check_output(['/usr/bin/readelf','-lW',str(exe)],text=True,env=env,timeout=15)
    ld=re.search(r'Requesting program interpreter: ([^]]+)\]',ph)
    if not ld or str(pathlib.Path(ld.group(1)).resolve(strict=True))!=VARIABLE_EPOCH_PATHS[0]:raise RuntimeError('missing interpreter')
    if set(files)!=RUNTIME_PATHS:raise RuntimeError('unknown runtime dependency topology')
    for path,expected in current_epoch_files.items():
        if files[path]['sha256']!=expected or measured_file(path)!=prebuild_lock['files'][path]:raise RuntimeError('frozen same-host epoch file differs: '+path)
    return {'binary_sha256':file_sha(exe),'interpreter':str(pathlib.Path(ld.group(1)).resolve()),'loaded_elf_dependencies':files}
cohort={'epoch':'live prebuild frozen libc/libm/loader cohort; independent, not a historical runtime identity','image':os.environ.get('ImageVersion'),'run_id':os.environ.get('GITHUB_RUN_ID'),'members':{}}
if not cohort['image'] or not cohort['run_id']:raise RuntimeError('missing environment identity')
expected_epoch_native_elf={'old': 'fbc253d428204532bff22c36c1361969c8f4e73174bf15945127c6ca030e1467', 'new': '50892889234f62276128a542a718f0c74ce7cdf9f06cd62fa094adf18faa0677'}
for l in locked_inputs:locked_inputs[l]['toolchain']=canon(prebuild_lock['expected_toolchain'])
for l,r in roots.items():
    receipt=json.loads((r/'.mlf-build/shared-ghc/receipt.json').read_text())
    if receipt['toolchain']!=prebuild_lock['expected_toolchain']:raise RuntimeError('producer full toolchain does not match prebuild lock: '+l)
    actual={k:canon(receipt[k]) for k in locked_inputs[BASE[l]]}
    if l not in DONOR:
        if record[l]['binary_sha256']!=expected_epoch_native_elf[l]:raise RuntimeError('new epoch native executable differs: '+l)
        if actual!=locked_inputs[l]:raise RuntimeError('pinned native intermediate mismatch: '+l)
    else:
        base=BASE[l];donor=DONOR[l];baseline=json.loads((roots[base]/'.mlf-build/shared-ghc/receipt.json').read_text())
        donor_receipt=json.loads((roots[donor]/'.mlf-build/shared-ghc/receipt.json').read_text())
        def normalized(x,root):return json.loads(json.dumps(x,sort_keys=True).replace(str(root)+'/', '<worktree>/'))
        for k in ['resolved_modules','shared_inputs','configuration_inputs','resolved_host_modules','host_inputs','flags','ghc','cc','installed_dependencies','toolchain']:
            bx=normalized(baseline[k],roots[base]);vx=normalized(receipt[k],r)
            if k in ('resolved_modules','shared_inputs'):
                bx['MLF.BuiltinPreludeData']['sha256']=sha(r/literal)
                bx['Bootstrap.Surface']=normalized(donor_receipt[k]['Bootstrap.Surface'],roots[donor])
            if bx!=vx:raise RuntimeError('hybrid admitted inputs mismatch '+l+' '+k)
        if set(receipt['object_inputs'])!=set(baseline['object_inputs']):raise RuntimeError('object membership mismatch')
    record[l]['git_head']=git(r,'rev-parse','HEAD')
    if l in DONOR and record[l]['binary_sha256']!={'old_swap':'b1abe0a8b7f58d502c488fcd734436dbd5fd5ec7a9c34731fdaa102f921d1c7b','new_swap':'45e3f63b7019233201e60a42863e3a9b493b1672b1e11c83137577bf35f7f7a5'}[l]:raise RuntimeError('hybrid ELF changed')
    ex=r/'.mlf-build/shared-ghc/bin/emlf'
    m=runtime_manifest(ex)
    if m['binary_sha256']!=record[l]['binary_sha256'] or m['binary_sha256']!=receipt['outputs']['emlf']['sha256']:raise RuntimeError('unverified executable')
    cohort['members'][l]={'runtime':m,'package_database_sha256':receipt['package_database_sha256'],'receipt_sha256':record[l]['receipt_sha256'],'intermediate_sha256':actual}
a,b=cohort['members']['old'],cohort['members']['new']
if a['runtime']['loaded_elf_dependencies']!=b['runtime']['loaded_elf_dependencies'] or a['package_database_sha256']!=b['package_database_sha256'] or a['runtime']['binary_sha256']==b['runtime']['binary_sha256']:raise RuntimeError('mismatched shared runtime or non-distinct producers')
for member in cohort['members'].values():
    if member['runtime']['loaded_elf_dependencies']!=a['runtime']['loaded_elf_dependencies'] or member['package_database_sha256']!=a['package_database_sha256']:raise RuntimeError('inconsistent 4-build runtime')
manifest=OUT/'new-epoch-cohort.json';manifest.write_text(json.dumps(cohort,indent=2)+'\n');frozen=sha(manifest)
def verify_frozen(l):
    read_lock()
    if sha(manifest)!=frozen:raise RuntimeError('mutated manifest')
    ex=roots[l]/'.mlf-build/shared-ghc/bin/emlf'
    if runtime_manifest(ex)!=cohort['members'][l]['runtime'] or sha(roots[l]/'.mlf-build/shared-ghc/receipt.json')!=cohort['members'][l]['receipt_sha256']:raise RuntimeError('changed executable, dependency or receipt')
record['epoch_manifest_sha256']=frozen;save()

helper=roots['new']/'tools/performance/a1-private-index/helper.py'
assert subprocess.check_output(['git','hash-object',str(helper)],text=True).strip()=='1feffe5d9f360a8fbb9f27868985d4a1a97ab010'

record['scope']='Independent ordinary 6GiB reciprocal historical Surface + necessary freshly generated canonical literal swaps. Binary cohort is not historical ELF. No compiler probes or RSS/time speed conclusions.'
record['schedule']=['old','new','new_swap','old_swap']
smoke=OUT/'SurfaceSmoke.hs';smoke.write_text('''-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
identityInt x = x;
choose flag = case flag of { True -> identityInt 7; False -> identityInt 0 };
main = do { printInt (choose True); printInt (choose False) };
}
''');record['smoke_fixture_sha256']=sha(smoke);record['smoke']=[]
for i,label in enumerate(record['schedule']):
    verify_frozen(label);r=roots[label];dest=OUT/('leg-'+str(i)+'-'+label)
    if label in BASE:
        sd=OUT/('smoke-'+label)
        try:H.Runner(OUT,dict(limits,wall_seconds=45)).run([r/'.mlf-build/shared-ghc/bin/emlf','--run',smoke],r,sd,expected_exit=0)
        except RuntimeError as err:record['last_runner_exception']=repr(err)
        verify_frozen(label);rec=sd/'command.json'
        ok_smoke=False
        if rec.exists():
            v=json.loads(rec.read_text());ok_smoke=bool(v.get('complete') and v.get('exit_code')==0 and v.get('reason') is None and v.get('terminal_live_descendants')==[] and (sd/'stdout').read_bytes()==b'7\n0\n' and not (sd/'stderr').read_bytes())
        record['smoke'].append({'label':label,'passed':ok_smoke});save()
        if not ok_smoke:record['stop_reason']='same-cohort semantic smoke failed';save();break
    expected=251 if BASE[label]=='new' else 0
    try:H.Runner(OUT,limits).run([r/'.mlf-build/shared-ghc/bin/emlf','-i',r/'libraries/mlf-foundation','--type',entry],r,dest,expected_exit=expected)
    except RuntimeError as err:record['last_runner_exception']=repr(err)
    verify_frozen(label)
    if not (dest/'command.json').exists():record['stop_reason']='missing receipt';save();break
    j=json.loads((dest/'command.json').read_text());ec=j.get('exit_code')
    ok=(ec==0 and (dest/'stdout').read_bytes()==b'IO ()\n' and not (dest/'stderr').read_bytes())
    oom=(ec==251 and (dest/'stderr').read_bytes()==b'emlf: out of memory\n' and not (dest/'stdout').read_bytes())
    accept=bool((ok or oom) and j.get('reason') is None and j.get('terminal_live_descendants')==[] and j.get('limits')==limits and j.get('logs') and all(sha(pathlib.Path(k))==v for k,v in j['logs'].items()))
    if i<2:accept=accept and bool(j.get('complete')) and ec==expected
    record['legs'].append({'label':label,'exit':ec,'output':'IO ()' if ok else 'emlf: out of memory' if oom else 'unexpected','accepted':accept,'rss':j.get('max_individual_child_rss_bytes')});save()
    if not accept:record['stop_reason']='required baseline, outcome or safety rejected';save();break
verify_all_locked_files()
record['prebuild_lock_sha256']=digest_path(LOCK)
record['final_full_toolchain_verified']=True
record['complete']=len(record['legs'])==4 and all(x['accepted'] for x in record['legs'])
save()
