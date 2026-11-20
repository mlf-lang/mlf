"""Authenticate PR43 reconciliation before reversible historical source projection."""
from functools import lru_cache
import hashlib
import json
import os
import stat
from pathlib import Path
import subprocess
import tarfile
import tempfile
import types

PREDECESSOR = '4fd6730d35b6ecaf8e169ad228ac3c7a3ed56160'
PREDECESSOR_TREE = '1c60d3daca5162bd24658d295169f601593345ef'
PREDECESSOR_MANIFEST = '69bc6cc39ec70a0209a6011f4ce7fef0aaf5039d903fa1b8477ee4a2bc46dcd8'
MANIFEST = 'pr43-reconciliation-migration.json'
MANIFEST_SHA256 = 'f6dc403850e02f33edabba309da1d410ad61663a365e7694efbcf6268190ca17'
MANIFEST_BYTES = 161230
INFERRED_CHAIN_MANIFEST_SHA256 = 'f611478915e5da8a47ee1d065f17ab26152029efb847418e0d6e0580b23cca74'
COMPILER_SOURCE_EDGES = [
    '119554684dde21433b8068a044ca7155a9a9fe7b42c6f484025730deaefbaf23',
    '8ea021f075aebc58394ac3e317e11a504f46efe5fbea432ccc30fb72dd2b5874',
    '5e7780d90e30581a5d5ee75413ff88f5157b0289347a6cd408ea52cb4fb5986a',
    '5153b754ad34b79a92f50c5c6b4fffccecb40159aae9bd80cbdc687dfb18892e',
    '6a0dfd2b44d1317e92940779e1cd9034ecb7e4c7b87c56b7cdca0d735a5e8446',
    '110168e3fa536e65cb01d471f4f3c3f47ec45c708e5d88e4ba94ff4c7e638dca',
    '91ede30a8620dddabf6c64221574b828ffa55e386e14c15986500ae372e1be3d',
    'b7ddd603409f79dff84f3624b66f676dffcd3ff63b4479ace0136f96441f8613',
    '904d3e0317c57779234faade1d81d5731b672df019424b4f7372e32d66b2cf08',
    '389a08d6d534f529f860cf007281fbe8dbfe3c5c61ca4a5316e0323dfdf61f1f',
    '930d2c7d579fc63151431d7b16ee5555cfcc9cf59c6c1200053d9341d7cfcb49',
    'b9cc16e899681f6ab65eb0aeca2498b4929ee488aacaf450d5e3a61c97d8dfd7',
    '0cdf400cdd84932e48a72866db44a85dcad9113db04a3cff5518a97c16506117',
    'e1f51a17b8b58c1695dca177ace660b33a792839b1dfaf668ab6342984854fab',
    '7bc1e2562a53d05b86b3ea5652d1382cf57ec3eec45f71cfcf74d2f64cdb2df5',
    '4b2a82f2db8a5af39818e66129ae9adaf0c9aa6ef8761fa1bee9be9f4e0bae55',
    '856baa3fb4d32cb2d90860a18abece8f42e2cdcd48f59e70687909651fc77687',
    '7553f60c7756851b4f1f623c9065ddc473f3e7f5e6511c6068feb917c260a84c',
    '1b0f978dd17065f55333083c9a909be88486698a3cba356f3e1235b0461473b7',
    '3046fe708d64edae4b371b1362cd090641b122c85043ad2bf493ed7fd89d70f3',
    'e1783747922c0b0ab09b5d0c122fdc08e4b653af9899f97f9ef8c755fde929f0',
    '4843a4f2fe3a1df6e9aa886f9142addf71fae8996c8264ae6350bbaca9b6ee01',
    '8e589b27d8570c3134a3b9a1d8d639df76c152f03ab114d2b856d8444ee44ab8',
    '3b354b49b04e74e35a70ce8c35ec9532c17b6f50c46c95f79371261363d35542',
    'f1f605253b02b73df91e0ec077183221c22ae2a11936ffc78523b84b33057ba2',
    '55fd50d61f9968bd921e4a18386fa0501c2f91a9e7a79e5907a4eb11ffac4560',
    'd6f6d178ab0f080196da5e0e4c5a8654f8158ecf7cbf78249c3c16aae14c2d81',
    'e0d0beb24fe1c291e088e5e7977044a285af64d55af21f698b4bc61190485ebe',
    '397c5122c9e069e93b909a86ecccaa3764f3960c32df71c972ef7ae8459761aa',
    '4c35cf824cc1fd8dbd23b1eaf0b60c9faabdd0152c7e7e89ef1bd18275b50038',
    '6981499e4929e37b59f1ab02d8a984b9d1babcc0ae5c1ccc06d3201422687651',
    '7f1c3ecf84d686f8e5ec36907635a1ce80b2e437d6d8fac902971703ab899ada',
    'c5d6b0468ba097ee33f4428bf1df7e47bf21d3a059eb3f7223806bfb8a12adc6',
    '047fef08617b4165d150a46923d1419cbb9835074be1321d76a1ea716c8c1316',
    '3f693e1d8290c8b73cc6b03028f901f773d991eda770b63fdcd1ca5c24dd52ac',
    '775d99db299794843a244a473f4eced6cf08e0e21b6c90b1dc6ef84426de43aa',
    'a2a6f14ee2986a04e99aa8ff61a28d24d56bb97f2edfd395e8f4ee8c2da15101',
    'df5e55f7cb588236236bf8e0fa70f41e103e618980b4f3e73bcd7de0e745a1e8',
    'fa5b0426c7647c7815ccf29f3bfc742fea74128fd904221b65ed7c17928ac24c',
    '538e4d6d40d3bacda6ac3aaecd71168ed39bbc55dd30e820ac1ade5ca5558989',
    '29e3ca5ff94b8d836cf117d7b32fb01ac466a81c0e564784e13b33be98f9524a',
    'f1d2879591796d4d7d1dfac9c2c17968c91fd70bfdc8ca1f3895cc1cf8063a40',
    '64127a62d430b8b8ad4e3e92e16556ffcfdd18d867ee45196ec81866f426c9c3',
    'd603cda3229a4adc914e45013c78494bb12c5750435cf80bf5b4265f6eaa92b0',
    '1b958294a424bc5b7df6883130c06344af0db7cdbc391d2dfe211d50b713b32d',
    '35b64b984ea4aab5ba876fc1ab5363805b3d2f4727f7c87490f4c2afb48b28be',
    'c6cf7cc331fa02b2f236804713b0eb8d4f899951742c6406241edbf140a2f8fd',
    'c6b629096fbd04abdea0e6e543cc7f8d0ed84feb16f0013989f0a30b00745fdd',
    '51739b6b3794e824f32fd5436c7cca543764ebf394eadac6aa96d2e4d86c28b3',
    '01f03fca2519068db67e0af11192e66dc99ff0fda817d1dae76efa1b71aed2a3',
    '7ce26f150b3bd9e26dfdc23f1ae31b5e20274edbab8c23e4f817638c69e6c7db',
    '2842d3106fbb9b12795ad82009c6bdfa38b36e21124820fa749bb99125bd0c27',
    '51a38c1aae1a3804068c9c841152e37522ce231f1ca44e67bbfa7eae3d0fef68',
    '5886f23031c3c3b1190b72a3f114eed459a713fd54b0d1a163222b41ca862b44',
    'ba7858728f2206747c91b600943b37a4e8464c0690177ac28c960442933beffa',
    'd1e1ee0cd213e2780913f725eac58d4c16957091e5795c734c6f5657f149af3c',
    'ea7b6600d571dc91fd59f0b03c0f01e24c8e766a9ee73258b9e10006147e7783',
    'b8f8779acfbc6f2158d04074d0249640a4a4582d2da16696de1d833db7831b0d',
    '9ef72726f1311b695d24355bab057ebf4a9cf91be494223e0a2c928ed22f357e',
    '38bbaa537132814c0ddcf0eafbb0ba5834f64bfcac5e29d37c10282b77ade591',
    '457c910c9d9499afe85755493035f3432426b27cf041df2117de5846a7fd9e17',
    '11158596ed7faff1d74888127f8e4b6416246eaa151bca976d98feb74730b9f8',
    '898f96bb883686fc06a9955c5b88d7c8fa8d798ef47b08c7f03e23caaebd1fbf',
    '60bb1ac651bfb1f6035a68056e35788291c44366eab9da0a12af4e79f0a5c508',
    '904e2cafdccbd5d988dfe3ff46c7e3526922e82b4b47ca54a914c0857e5a1522',
    'e26b2137bb6188e4bf9594a6dc1f0c076ad08c683763d82b9a29383ef99b9a9b',
    '39ba052050c352b09e24a061ce02a3f4575a682fb59e19c67b1fa7eb04ae6ae9',
    '57d41ecc46238a3dffba1248ae9eba126351ae8222950832882d914f78ee6f4f',
    'cf2f5b829136625f9e35272709be48254e31aaac52bf1fca433165da3c7132e8',
    'd35274708a2705aa5f759df6d084c505b7ad4d7daab9a431dc13e97c43287c04',
    '02d93ae1130fd318b2a7a78253a29f2d38e71948ab04fff82e577030d7cbb20f',
    '9c6ded999bc4e7e98f5419ba46b5529eb569fcc9f589c3d283d43f8f682779dc',
    '60a3d5f0ee34a9816eca5b4632257e04fc21f754265885ceaf0217542428c8f6',
    '919ec4391ef242afc31be187fa054fcdcf33d7be4fed87b7f32b89bf1bf6417e',
    '60f89a1c955c777b1a739f4689f82cac332f9a876f25b2341aabddfd8d764703',
    'f1a64b0fb2a8695bc581fa3b1495c05719517e0e868c066ce9849175a56f628a',
    'cc5857ecdd3034a1fe30af07f590abedce04ba08707ffd1e320e0225fa5bec31',
    'd3358fbcf53f505e6b573702c20d9ca9533d18c60ef0ff16f1d20bd16554da0f',
    'a5320a25bbd6e07e516a7a5a9db418d856880de6be51f49ffe7e899971f11cfe',
    'f91b22003aae1f235e1ff94c54f2fcd63a4aeee7b80dfa32ffea70ed115d79a2',
    '2e3ec3185b26b6178ba2b24c32e7fb433a9f13ef88209d96000fad064e48409f',
    '8429f8221515a3243f8f177fa5bc027f82c913f62c0f1b401aad32225792e7f5',
    '3bada8a765d42ebbccdce82975671d938f616e07b7d6c6979c6a9facd22ed77b',
    '4c9358b29afc132df8ad1d9de734f25a96b731f41bc0da209523f697b30520d2',
    'f09205bfa66e33778f014e2f5d14e0f91c459a4572d0dc6cc588277f384d9dc6',
    'ca14fc5e6ee0fb43d18fc0a9832a6c124d954c140ba724407c7d15223eb3b857',
    '67e232f51ede19fddd67be3d97e4f9e4130dd8b91631ccc14871f5d8e346d6ab',
    'a42bee5733e496290ed32cd0fec86806bbd9ee6ed9e57f411c87c01df7d8a688',
    '91e6cbd6bb4325a6f2d8d842f1cd86f217c3877894833277b95b39cd3f86a352',
    '3a9d8e884e558a8ec50c3086147f208c284c33479c4c6862f751189a4f399413',
    '7a7af5fda426674c919cae2da93a0b335fdae51ab1f3be07f7ae744e8a698fc1',
    'e52a450343edae9afcafd74026c5d6095a26e07830da34aa0d725cba29305051',
    'db897dbdf4ad2b00a6a99ec6aa7a2e74dcc97dbe051e9aacb7b8b6c808f126a4',
    'e9956d5591c5c76e7f46fa825e7ea29911b81c6d6854b264a17d1fc5565dd205',
    'bc26b5662451fed0b245ae75f9e01b28cd7f1d2389a319d9fe2fd4e769bd6139',
    '913ee315d76e66272aca023477250bac2b0247232e22be89d4877d56b763eceb',
    'd816dcb6b0ef15a485d5a6b4ad47f0f01b8899fd9d45e213680e2e2b8f9d2c5e',
    '4d73fba73c90970847c56757d293d480aff1350d1d80d5f6cffc358479082d5f',
    'd5ae9273341d829bb8df91dc0a695a78679e7488f4ed8c5a0d31627ff061c193',
    '65d757683ab0dd34f27adcd1d34cd609032258e1e1c687769f8dbb71e17c0160',
    'a8ad2b585f193f71defea49b0cb968dd1f31effab589e851b086bd9ad1b6cfd0',
    'c8df79d4c5d3ef3be5b66a0189e8f1dd7d8f87f5037a8953f616579ceff54447',
    'e000b8a3c9115bb2fe26ed9b39a61a0124b5cdcb192132e5ad4479c84430c440',
    '485403a098e3cf7ef1b86fd5c6be4e7d75e93939420e210987d2ceec3f64db86',
    '0d1295e0a6799c3ac37a2c49eacb97843efb7d27f111d892040062874c54f40f',
    'bfc0a2195923309e671c442eb9c8116056fd616ce7cc8404f2fcd871ca9ebb2f',
    '2852e03a59122ff914730be2cf77a281ebb4419420447e76db63468b6b43bee8',
    '84d9286edc2777eaf500a8164af57299b1e0368d3a6746923267bb7e673eeb0b',
    '892a5851ae492a9448df3c34083e965385c84ce9671069cbc09dfb9d8aa1155d',
    '63b6f66ecb48c21546258fbe87f3628516bdd8f3f778e3a7edb2eda1f0bc84e0',
    '93bd565422532ca3f76dde0cbe4eb385ad78dcb4edee7fdb98362773b5419272',
    'd32c4b17170710c2a25144b10c06944868204569eb3bee82ee18aab4c65a628e',
    '357d415d2c6327f2b7526872bfea88da89f8c06534208f383b8c4a6ded5bb7d7',
    '70030d5a7b9518f6cf5e1fbb905bcc3e61d69c270798aee0e57abacde89f26a4',
    'd59e811b747751b9c8cbf6abe921605c2fd729bf8b0766ce10aa7235771299c0',
    '2cac46e5a1cbe56659fdc6c8e137399e99fb230abfacb51423e99b00d7fbb9a2',
    '61f06db4310c1538094c84e2de24bdbb5eb88db3b692ecfb6a401b5050bad6e8',
    'e286aa62542f6e88995d738c35d82ea32a7371d1b43aa374e46dbe387a9fd4cf',
    'ba0ad3d248c20d36f16175206bbc03b3f3d6c628ac36f1a13c1dc96002d91909',
    'b278f0b1eb37147faaa36ed03a3c3e2ebe713e5de5684a954676cbdefa335a52',
    '7dc5de66f38d0a0c45da51aca631976a5ba0aaa4aa429572dc2a2592ca8a6a9e',
    '96cae847863f78d5c806bb071f316fa01400dadb6b4917af92bf4b19daaf1502',
    'c11f93c64979395ba87372ebca32b329d60f62585d382a4c65a10890a14fd05c',
    '09cbb45e24a8b1486a26c4da20c60d73daf23571746534ea3e6b4564da1b5c2f',
    '3bc67a7070c1c539b2242ae22269de4bf028ba240c8bf7ba8c3225d7c233ee77',
    '413217b52dd251833bd8fc9e3d4fde10eb8579ffdab94e4203d3d7f363f8da06',
    'd9aedc60659300ca66403f6954e964c5f43fe61a724fcaeeaeff7c54ebb3a97b',
    '06d4b44116c40763e9490017110c2569f89ed58573a305737f5c536e43cf4147',
    '24c292e6ae038f282a41205ff587dc4327ccfd75021eff495b74095925aea17d',
    '7187c0eaf97ec4a6780bc41e2f4e39fe38d1404230f976af8097dffc92f79299',
    '8107783d909a49d577d71398d2a97f898e201de112d8230597e86bbfb0ea041e',
    '1633c826248a1a935a96ad15ba88a9631dd762ab60eb68e0a2253d133cc9d073',
    'e6a3e287ed8fc5dfb0f8a9d0b9a72365fcac2a8d36eb8f84f026b1b68fcf3217',
    '7ff3d910b111f3dd487142ecdf5a52a9190c68089e8c8fa73e682550220029f4',
    '5bcbe4e228ce1c9ebf4d1328e81efa4e2eddc431559f7701f6fbee7e338e1d76',
    'f04ba2140ff3ad232f5a4514b65e48d7014ed7c9f0c30f5a44adf8e57e6bd172',
    'd374b22a354f70aec8da8c560dba8a3af694b76576716659271ee8b4fcda593f',
    'd440e11ce54e18c1e1d5b729570c55d3ac43b2e993b6291a3bc677aecd36381a',
    '3966c90327a8c01e48b9c006c95fe0179e664efb2bbcf31fa662990cdf8a305b',
]
ADAPTER_MANIFEST_SHA256 = '6bbc1da597cb7eaaeab16aff52e8b44e2d4dc11ff10997679a45b3405bf0be98'
CHAIN_EDGE_SHA256 = '5acc941d400b8b194ca97ca6a3c3ad6322e199279191bbf7b2d5816dab59841c'
PREDECESSOR_IMPLEMENTATION = '7cacadad979f3db29da9067b5fe0ca8e1634d960dbf978ad6d5cae39ba338794'
LIVE_PREDECESSOR = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
LIVE_PREDECESSOR_TREE = '3148203097e7622ced1b272e606bfa892fad746b'
LIVE_PREDECESSOR_MANIFEST = '63598306f049a050def3fd21ddf21878a7f4f882b59a48a86c53a3398624e9c5'
LIVE_TRANSITION_PATH = 'tools/shared/build.py'
LIVE_PREDECESSOR_SOURCE = 'eff291112f318206ce0f7ab85cb8a2e474be41489441204696630a395f4ca3df'
PERFORMANCE_BASE = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'
PERFORMANCE_TREE = '386f0b41ab5f9b39fca273f3040f51d73df924a1'
PERFORMANCE_BASE_MANIFEST = 'ebe5671476447cd4b256784e7d898ed6095c7c54cc9286c6869ca4909b2b708b'
PERFORMANCE_MAINTENANCE_PATH = 'patricia/test_adapters.py'
ADAPTER_BASE = '08a08aa98c01f4f07b6efb01a250a0d86f387811'
ADAPTER_TREE = 'eec52972c0028a7f1d20da0ac15f867664c2c918'
ADAPTER_BASE_MANIFEST = '82b9b045993ff9ac2d14a5b67dbfd35288004a79ae08303a1047f81de438d009'
ADAPTER_PATH = 'patricia/adapt_oracles.py'
ADAPTER_OLD_SHA = '45ce4b0fac779be59272e1a9ae377115c1c91a7e03f6acf77588c41aea40af0e'
ADAPTER_OLD_DECLARATION = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller) where {'"
ADAPTER_NEW_DECLARATION = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller,\\n    CompiledCrate, compiledObject, compiledInterfaces, compileSpecFileRetainedUsingInstaller) where {'"
PERFORMANCE_PATHS = {
    'bootstrap/MLF/BuiltinPreludeData.hs',
    'bootstrap/MLF/Entry/Emlf.hs',
    'bootstrap/MLF/PreparedCompiler.hs',
    'host/ghc/MLF/Host/Base.hs',
    'host/ghc/MLF/Host/IO.hs',
    'host/ghc/MLF/Primitive.hs',
    'host/ghc/cbits/host.c',
    'libraries/mlf-crates/Bootstrap/ArtifactStructure.hs',
    'libraries/mlf-crates/Bootstrap/Bitstream.hs',
    'libraries/mlf-crates/Bootstrap/BuiltinPreludeContext.hs',
    'libraries/mlf-crates/Bootstrap/BuiltinPreludeLiteral.hs',
    'libraries/mlf-crates/Bootstrap/Crate.hs',
    'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
    'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
    'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
    'libraries/mlf-crates/Bootstrap/CrateSession.hs',
    'libraries/mlf-crates/Bootstrap/InferenceUnit.hs',
    'libraries/mlf-crates/Bootstrap/OpenFragment.hs',
    'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
    'libraries/mlf-crates/Bootstrap/Separate.hs',
    'libraries/mlf-crates/Bootstrap/SourceEquality.hs',
    'libraries/mlf-crates/Bootstrap/SourceInference.hs',
    'libraries/mlf-foundation/Bootstrap/Fresh.hs',
    'libraries/mlf-foundation/Bootstrap/Host.hs',
    'libraries/mlf-foundation/Bootstrap/Map.hs',
    'libraries/mlf-foundation/Bootstrap/Types.hs',
    'libraries/mlf-frontend/Bootstrap/Layout.hs',
    'libraries/mlf-frontend/Bootstrap/Lexer.hs',
    'libraries/mlf-frontend/Bootstrap/Module.hs',
    'libraries/mlf-frontend/Bootstrap/Parsec.hs',
    'libraries/mlf-frontend/Bootstrap/Parser.hs',
    'libraries/mlf-inference/Bootstrap/Classes.hs',
    'libraries/mlf-interpreter/Bootstrap/Runtime.hs',
    'libraries/mlf-language-core/Bootstrap/Primitive.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Codegen.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Library.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs',
    'libraries/mlf-package-core/Package/Build.hs',
    'libraries/mlf-package-core/Package/Scheduler.hs',
    'mlf-shared.cabal',
    'mlf.lock',
    'runtime/mlf_build_runner_hash.h',
    'runtime/mlf_runtime.c',
    'runtime/mlf_runtime.h',
    'shared-sources.json',
    'tests/shared/MLF/Tests/SharedFrontend.hs',
    'tools/shared/build.py',
    'tools/shared/test_direct.py',
}


def require(condition, message):
    if not condition:
        raise ValueError('PR43 reconciliation source migration: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def archived_checkout(repository):
    """This process owns one immutable, SHA-addressed physical predecessor for the old reader."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', PREDECESSOR + '^{tree}'], text=True).strip()
    require(tree == PREDECESSOR_TREE, 'pinned predecessor tree')
    directory = tempfile.TemporaryDirectory(prefix='mlf-pr43-previous-')
    with subprocess.Popen([*git, 'archive', PREDECESSOR, 'libraries', 'bootstrap', 'host', 'runtime',
        'tools/performance', 'tools/shared', 'shared-sources.json', 'mlf.lock',
        'mlf-package.json', 'mlf-shared.cabal', 'cabal.project', 'tests', 'testing', 'package'], stdout=subprocess.PIPE) as archive:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(directory.name, filter='data')
        require(archive.wait() == 0, 'cannot read pinned predecessor')
    return directory


def module_at(path):
    require(path.is_file() and not path.is_symlink(), 'predecessor implementation file')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536 and sha(raw) == PREDECESSOR_IMPLEMENTATION, 'predecessor implementation SHA')
    return module_bytes(path, raw)


@lru_cache(maxsize=1)
def module_bytes(path, raw):
    # module_at revalidates the immutable implementation on every call. Reuse
    # only identical pinned bytes so its original predecessor cache is shared.
    result = types.ModuleType(path.stem)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def manifest_bytes(directory):
    path = directory / MANIFEST
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                         getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MANIFEST_BYTES,
                'bounded regular successor manifest')
        # Short inputs cannot match the pin. Preserve the identity diagnostic.
        require(info.st_size == MANIFEST_BYTES, 'successor manifest SHA')
        raw = os.read(descriptor, MANIFEST_BYTES + 1)
        require(len(raw) == MANIFEST_BYTES, 'successor manifest byte bound')
        return raw
    finally:
        os.close(descriptor)


def validate_macos_transition(spec, repository, core):
    """Admit only the declared build-driver repair after the fixed main endpoint."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', LIVE_PREDECESSOR + '^{tree}'], text=True).strip()
    require(tree == LIVE_PREDECESSOR_TREE, 'pinned live predecessor tree')
    raw = subprocess.check_output([*git, 'show', LIVE_PREDECESSOR +
                                   ':tools/performance/artifact-binary/' + MANIFEST])
    require(len(raw) <= core.MAX_METADATA_BYTES and sha(raw) == LIVE_PREDECESSOR_MANIFEST,
            'pinned live predecessor manifest')
    prior = core.strict_json(raw)
    old = subprocess.check_output([*git, 'show', LIVE_PREDECESSOR + ':' + LIVE_TRANSITION_PATH])
    require(len(old) <= core.MAX_SOURCE_BYTES and sha(old) == LIVE_PREDECESSOR_SOURCE and
            prior['changes'][LIVE_TRANSITION_PATH][1] == LIVE_PREDECESSOR_SOURCE,
            'pinned live predecessor source')
    row = spec['changes'].get(LIVE_TRANSITION_PATH)
    require(type(row) is list and len(row) == 2 and row[1] != LIVE_PREDECESSOR_SOURCE,
            'changed live build endpoint')
    transition = {
        'predecessor': LIVE_PREDECESSOR,
        'predecessor_tree': LIVE_PREDECESSOR_TREE,
        'predecessor_manifest_sha256': LIVE_PREDECESSOR_MANIFEST,
        'changes': {LIVE_TRANSITION_PATH: [LIVE_PREDECESSOR_SOURCE, row[1]]},
    }
    # Preserve the original PR43 endpoints, every other current endpoint,
    # additions, registry ownership and historical maintenance records verbatim.
    expected = {**prior, 'changes': {**prior['changes'], LIVE_TRANSITION_PATH:
                                  [prior['changes'][LIVE_TRANSITION_PATH][0], row[1]]},
                'live_transition': transition}
    require(spec == expected, 'only the declared live build endpoint may change')


def validate_performance_transition(spec, repository, core):
    """Pin the performance follow-on while retaining the earlier exact transition."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', PERFORMANCE_BASE + '^{tree}'], text=True).strip()
    require(tree == PERFORMANCE_TREE, 'pinned performance predecessor tree')
    raw = subprocess.check_output([*git, 'show', PERFORMANCE_BASE +
                                   ':tools/performance/artifact-binary/' + MANIFEST])
    require(len(raw) <= core.MAX_METADATA_BYTES and sha(raw) == PERFORMANCE_BASE_MANIFEST,
            'pinned performance predecessor manifest')
    prior = core.strict_json(raw)
    validate_macos_transition(prior, repository, core)
    changes = spec.get('performance_transition', {}).get('changes', {})
    require(set(changes) == PERFORMANCE_PATHS, 'exact performance source paths')
    expected = {**prior, 'changes': dict(prior['changes'])}
    for path in sorted(PERFORMANCE_PATHS):
        old = subprocess.check_output([*git, 'show', PERFORMANCE_BASE + ':' + path])
        require(len(old) <= core.MAX_SOURCE_BYTES, 'performance predecessor source bound')
        row = changes[path]
        require(type(row) is list and len(row) == 2 and row[0] == sha(old) and row[0] != row[1],
                'performance transition ' + path)
        previous = prior['changes'].get(path, [row[0], row[0]])
        require(previous[1] == row[0], 'performance predecessor endpoint ' + path)
        expected['changes'][path] = [previous[0], row[1]]
    # This one live boundary test follows the performance source transition.
    # Authenticate its physical intermediate endpoint, not just a mutable row.
    maintenance = spec.get('performance_transition', {}).get('maintenance', {})
    name = PERFORMANCE_MAINTENANCE_PATH
    require(type(maintenance) is dict and set(maintenance) == {name},
            'exact performance maintenance paths')
    old = subprocess.check_output([*git, 'show', PERFORMANCE_BASE + ':tools/performance/' + name])
    row = maintenance[name]
    previous = prior['maintenance'][name]
    require(len(old) <= core.MAX_SOURCE_BYTES and sha(old) == previous[1],
            'performance predecessor maintenance source')
    require(type(row) is list and len(row) == 2 and row[0] == sha(old) and
            type(row[1]) is str and len(row[1]) == 64 and
            all(c in '0123456789abcdef' for c in row[1]) and row[0] != row[1],
            'performance maintenance transition')
    expected['maintenance'] = {**prior['maintenance'], name: [previous[0], row[1]]}
    expected['performance_transition'] = {
        'predecessor': PERFORMANCE_BASE, 'predecessor_tree': PERFORMANCE_TREE,
        'predecessor_manifest_sha256': PERFORMANCE_BASE_MANIFEST, 'changes': changes,
        'maintenance': maintenance,
    }
    require(spec == expected, 'only the declared performance endpoints may change')


def validate_adapter_successor(spec, prior_raw, old_source, current_source, tree, core):
    """One reversible test-header edit, after an immutable complete predecessor."""
    require(tree == ADAPTER_TREE, 'fixed adapter predecessor tree')
    require(sha(prior_raw) == ADAPTER_BASE_MANIFEST, 'fixed adapter predecessor manifest')
    require(sha(old_source) == ADAPTER_OLD_SHA, 'fixed adapter predecessor source')
    require(old_source.count(ADAPTER_OLD_DECLARATION) == 1 and
            ADAPTER_NEW_DECLARATION not in old_source, 'unique previous adapter declaration')
    expected_source = old_source.replace(ADAPTER_OLD_DECLARATION, ADAPTER_NEW_DECLARATION)
    require(current_source == expected_source and current_source.count(ADAPTER_NEW_DECLARATION) == 1 and
            current_source.replace(ADAPTER_NEW_DECLARATION, ADAPTER_OLD_DECLARATION) == old_source,
            'exact reversible adapter header change')
    prior = core.strict_json(prior_raw)
    require(ADAPTER_PATH not in prior['maintenance'], 'unchanged adapter at predecessor')
    row = [ADAPTER_OLD_SHA, sha(current_source)]
    expected = {**prior, 'maintenance': {**prior['maintenance'], ADAPTER_PATH: row},
        'adapter_successor': {'predecessor': ADAPTER_BASE, 'predecessor_tree': ADAPTER_TREE,
            'predecessor_manifest_sha256': ADAPTER_BASE_MANIFEST, 'maintenance': {ADAPTER_PATH: row}}}
    require(spec == expected, 'only declared adapter successor may change')
    return prior


def validate_adapter_transition(spec, repository, core, history_root=None):
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', ADAPTER_BASE + '^{tree}'], text=True).strip()
    prior_raw = subprocess.check_output([*git, 'show', ADAPTER_BASE + ':tools/performance/artifact-binary/' + MANIFEST])
    old_source = subprocess.check_output([*git, 'show', ADAPTER_BASE + ':tools/performance/' + ADAPTER_PATH])
    require(len(prior_raw) <= core.MAX_METADATA_BYTES and len(old_source) <= core.MAX_SOURCE_BYTES,
            'adapter predecessor byte bounds')
    current = core.read_file(Path(history_root) if history_root is not None else Path(repository) / 'tools/performance', ADAPTER_PATH)
    prior = validate_adapter_successor(spec, prior_raw, old_source, current, tree, core)
    validate_performance_transition(prior, repository, core)


def canonical_manifest(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def rewind_sources(current, delta):
    changes = dict(current)
    for path, (old, new) in delta.items():
        # A return to the original bytes disappears from the cumulative table.
        first, last = changes.get(path, [new, new])
        require(old != new and last == new, 'compiler source endpoint: ' + path)
        if first == old:
            changes.pop(path, None)
        else:
            changes[path] = [first, old]
    return changes


def compiler_history(spec):
    """Reconstruct complete manifests back to the published inferred-chain merge."""
    edges = spec.get('compiler_source_transitions')
    require(type(edges) is list and [sha(canonical_manifest(edge)) for edge in edges] == COMPILER_SOURCE_EDGES,
            'fixed compiler source transitions')
    history = [spec]
    for index in reversed(range(len(edges))):
        edge = edges[index]
        current = history[-1]
        prior = {**current, 'changes': rewind_sources(current['changes'], edge['changes'])}
        if 'maintenance' in edge:
            prior['maintenance'] = rewind_sources(current['maintenance'], edge['maintenance'])
        if index:
            prior['compiler_source_transitions'] = edges[:index]
        else:
            del prior['compiler_source_transitions']
        require(sha(canonical_manifest(prior)) == edge['predecessor_manifest_sha256'],
                'complete compiler source predecessor')
        history.append(prior)
    require(sha(canonical_manifest(history[-1])) == INFERRED_CHAIN_MANIFEST_SHA256, 'published inferred-chain manifest')
    return history


def chain_predecessor(spec):
    prior = dict(spec)
    edge = prior.pop('inferred_chain_transition', None)
    require(sha(canonical_manifest(edge)) == CHAIN_EDGE_SHA256, 'fixed inferred-chain transition')
    prior['changes'] = rewind_sources(prior['changes'], edge['changes'])
    require(sha(canonical_manifest(prior)) == ADAPTER_MANIFEST_SHA256, 'entire adapter endpoint')
    return prior


def adapter_endpoint(spec):
    """Recover the exact adapter manifest without requiring a checkout."""
    return chain_predecessor(compiler_history(spec)[-1])


def validate_live_transition(spec, repository, core, history_root=None):
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    manifest_path = 'tools/performance/artifact-binary/' + MANIFEST

    def at(commit, path, limit):
        data = subprocess.check_output([*git, 'show', commit + ':' + path])
        require(len(data) <= limit, 'compiler source byte bound: ' + path)
        return data

    history = compiler_history(spec)
    for current, previous in zip(history, history[1:]):
        delta = current['compiler_source_transitions'][-1]
        commit = delta['predecessor']
        tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
        require(tree == delta['predecessor_tree'], 'compiler source predecessor tree')
        require(at(commit, manifest_path, core.MAX_METADATA_BYTES) == canonical_manifest(previous),
                'archived compiler source manifest')
        for path, (old, _) in delta['changes'].items():
            require(sha(at(commit, path, core.MAX_SOURCE_BYTES)) == old, 'archived compiler source: ' + path)
        for name, (old, _) in delta.get('maintenance', {}).items():
            require(name == PERFORMANCE_MAINTENANCE_PATH and
                    sha(at(commit, 'tools/performance/' + name, core.MAX_SOURCE_BYTES)) == old,
                    'archived compiler maintenance source: ' + name)

    spec = history[-1]
    prior = chain_predecessor(spec)
    validate_adapter_transition(prior, repository, core, history_root)
    edge = spec['inferred_chain_transition']
    base, measured = edge['predecessor'], edge['measured']
    for role, commit in [('predecessor', base), ('measured', measured)]:
        tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
        require(tree == edge[role + '_tree'], 'inferred-chain ' + role + ' tree')
    base_raw = at(base, manifest_path, core.MAX_METADATA_BYTES)
    measured_raw = at(measured, manifest_path, core.MAX_METADATA_BYTES)
    require(sha(base_raw) == edge['predecessor_manifest_sha256'] == ADAPTER_MANIFEST_SHA256 and
            core.strict_json(base_raw) == prior, 'complete inferred-chain predecessor')
    require(sha(measured_raw) == edge['measured_manifest_sha256'], 'measured source manifest')
    before = prior['changes']
    after = core.strict_json(measured_raw)['changes']
    require(before.keys() <= after.keys(), 'inferred-chain source removed')
    changed = {path for path in after if before.get(path) != after[path]}
    require(changed == set(edge['changes']), 'exact inferred-chain source paths')
    for path in changed:
        old = sha(at(base, path, core.MAX_SOURCE_BYTES))
        new = sha(at(measured, path, core.MAX_SOURCE_BYTES))
        first, last = before.get(path, [old, old])
        require(last == old and old != new and edge['changes'][path] == [old, new] and
                after[path] == [first, new], 'inferred-chain source transition: ' + path)
    require(after == spec['changes'], 'exact measured compiler source endpoints')


class Contract:
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        self.directory = Path(directory).resolve(strict=True)
        self.source_root = Path(source_root or Path(history_root).parents[1]).resolve(strict=True)
        require(manifest_sha256 == MANIFEST_SHA256, 'expected independently pinned successor manifest')
        require(sha(manifest_bytes(self.directory)) == MANIFEST_SHA256, 'successor manifest SHA')
        # A relocated source/metadata bundle can still use the current caller's
        # Git object database. In both cases the same commit and tree are required.
        for location in (history_root, Path.cwd()):
            repo = subprocess.run(['git', '-C', str(location), 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True)
            if repo.returncode == 0:
                location = repo.stdout.strip()
                tree = subprocess.run(['git', '--no-replace-objects', '-C', location, 'rev-parse', PREDECESSOR + '^{tree}'],
                                      capture_output=True, text=True)
                if tree.returncode == 0 and tree.stdout.strip() == PREDECESSOR_TREE:
                    break
        else:
            raise ValueError('PR43 reconciliation source migration: full Git history required for pinned predecessor')
        self.archived = Path(archived_checkout(location).name)
        # Only the immutable tree supplies executable predecessor code. The caller's
        # bundle supplies its metadata, which the old constructor authenticates.
        old_dir = self.archived / 'tools/performance/artifact-binary'
        previous_type = module_at(old_dir / 'declid_contract.py').Contract
        self.previous = previous_type(self.directory, PREDECESSOR_MANIFEST,
                                      self.archived / 'tools/performance', self.archived)
        self.core = self.previous.core
        self.manifest_sha256 = manifest_sha256
        raw = self.core.read_file(self.directory, MANIFEST, self.core.MAX_METADATA_BYTES)
        require(sha(raw) == manifest_sha256, 'successor manifest SHA')
        spec = self.core.strict_json(raw)
        require(set(spec) == {'format', 'predecessor', 'changes', 'additions', 'maintenance', 'live_transition', 'performance_transition', 'adapter_successor', 'inferred_chain_transition', 'compiler_source_transitions'} and
                spec['format'] == 'pr43-reconciliation-source-migration-v1' and spec['predecessor'] == PREDECESSOR,
                'successor manifest schema')
        validate_live_transition(spec, location, self.core, history_root)
        self.changes = spec['changes']
        self.maintenance = spec['maintenance']
        files = dict(self.previous.value['current_files'])
        for name, row in self.changes.items():
            require(len(row) == 2 and files[name] == row[0] and row[0] != row[1], 'source transition ' + name)
            files[name] = row[1]
        for name, digest in spec['additions'].items():
            require(name not in files, 'added path already owned: ' + name)
            files[name] = digest
        self.core.hash_map(files, 'PR43 reconciled files')
        self.value = {'current_files': files}
        self.live_source_inventory(self.source_root)
        registry = self.core.strict_json(self.core.read_file(self.source_root, 'shared-sources.json'))
        paths = {row['module']: row['path'] for row in registry['modules']}
        require(len(paths) == len(registry['modules']), 'duplicate module')
        old_paths = self.previous.value['module_paths']
        require(all(paths.get(n) == p for n, p in old_paths.items()), 'changed or removed module owner')
        added = {n: p for n, p in paths.items() if n not in old_paths}
        require(set(added.values()) == set(spec['additions']), 'added module and source inventories differ')
        self.value.update(module_paths=paths, current_registry={n: files[p] for n, p in paths.items()})
        self.added_modules = {**self.previous.added_modules, **added}
        self.parent = self.previous.parent
        self.maintenance_parent = self.previous.maintenance_parent
        self.evidence_source_root = self.previous.evidence_source_root
        self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, 'reconciliation_contract.py')
        self.added_paths = sorted(set(self.previous.added_paths) | set(spec['additions']))
        for path in self.previous.metadata_paths:
            if path != 'source_migration_adapter.py':
                require(self.core.read_file(self.directory, path) == self.core.read_file(old_dir, path),
                        'predecessor metadata changed: ' + path)
        # The successor must preserve every frozen tool/oracle identity the old
        # constructor read, including when the caller supplies a relocated tree.
        history_names = set(self.parent['frozen_history']) | set(self.maintenance_parent['files'])
        require(set(self.maintenance) <= history_names, 'unexpected maintenance owner')
        for name in history_names:
            raw = self.core.read_file(history_root, name)
            old = self.core.read_file(self.archived / 'tools/performance', name)
            if name in self.maintenance:
                require(self.maintenance[name] == [sha(old), sha(raw)] and raw != old,
                        'maintenance transition ' + name)
            else:
                require(raw == old, 'undeclared historical change ' + name)

    def _require_raw_map(self, value, expected, label):
        require(type(value) is dict and set(value) == set(expected), 'complete raw ' + label + ' paths')
        for path, raw in value.items():
            require(type(raw) is bytes and len(raw) <= self.core.MAX_SOURCE_BYTES and
                    sha(raw) == expected[path], 'complete raw ' + label + ' SHA: ' + path)

    def live_source_inventory(self, root):
        actual = {p: sha(self.core.read_file(root, p)) for p in self.value['current_files']}
        require(actual == self.value['current_files'], 'whole live source inventory differs')
        return actual

    def live_registry(self, root):
        require(sha(self.core.read_file(root, 'shared-sources.json')) == self.value['current_files']['shared-sources.json'],
                'module registry bytes')
        registry = {n: sha(self.core.read_file(root, p)) for n, p in self.value['module_paths'].items()}
        self.require_registry(registry, 'current')
        return registry

    def require_registry(self, value, side):
        if side == 'parent':
            return self.previous.require_registry(value, side)
        require(side == 'current' and value == self.value['current_registry'], 'exact complete current registry')

    def _older_bytes(self, raw, path):
        require(type(raw) is bytes and sha(raw) == self.value['current_files'].get(path), 'source SHA ' + path)
        if path not in self.previous.value['current_files']:
            return None
        if path in self.changes:
            old = self.core.read_file(self.archived, path)
            require(sha(old) == self.changes[path][0], 'predecessor SHA ' + path)
            return old
        return raw

    def restore_path(self, raw, path):
        previous = self._older_bytes(raw, path)
        return None if previous is None else self.previous.restore_path(previous, path)

    def project_owner(self, raw, module):
        require(module in self.value['module_paths'], 'unknown source owner')
        return self.restore_path(raw, self.value['module_paths'][module])

    def advance_registry(self, parent):
        self.previous.advance_registry(parent)
        return dict(self.value['current_registry'])

    def added_source_bytes(self, root):
        result = {n: self.core.read_file(root, p) for n, p in self.added_modules.items()}
        self.registry_to_parent(self.value['current_registry'], result)
        return result

    def registry_to_parent(self, current, additions):
        self.require_registry(current, 'current')
        require(type(additions) is dict and set(additions) == set(self.added_modules), 'full added source inventory')
        old = {n: self._older_bytes(additions[n], p) for n, p in self.added_modules.items()}
        return self.previous.registry_to_parent(self.previous.value['current_registry'],
                                                {n: old[n] for n in self.previous.added_modules})

    def live_host_inventory(self, root):
        actual = {p: sha(self.core.read_file(root, p)) for p in self.parent['host_inventory']}
        require(actual == {p: self.value['current_files'][p] for p in self.parent['host_inventory']},
                'complete live host inventory')
        return actual

    def legacy_host_subset_to_parent(self, current):
        require(type(current) is dict and set(current) <= set(self.parent['legacy_host_bridge']) and
                current == {p: self.value['current_files'][p] for p in current}, 'exact live host subset')
        return self.previous.legacy_host_subset_to_parent({p: self.previous.value['current_files'][p] for p in current})

    def advance_legacy_host_subset(self, parent):
        previous = self.previous.advance_legacy_host_subset(parent)
        return {p: self.value['current_files'][p] for p in previous}

    def restore_maintenance(self, raw, name):
        if name in self.maintenance:
            old = self.core.read_file(self.archived / 'tools/performance', name)
            require([sha(old), sha(raw)] == self.maintenance[name], 'maintenance source identity')
            raw = old
        return self.previous.restore_maintenance(raw, name)

    def _newer_bytes(self, raw, path):
        require(sha(raw) == self.previous.value['current_files'].get(path), 'predecessor path SHA')
        if path not in self.changes:
            return raw
        new = self.core.read_file(self.source_root, path)
        require(sha(new) == self.changes[path][1], 'successor path SHA')
        return new

    def advance_path(self, raw, path):
        return self._newer_bytes(self.previous.advance_path(raw, path), path)

    def restore_previous_lock(self, raw):
        return self.previous.restore_previous_lock(self._older_bytes(raw, 'mlf.lock'))

    def advance_lock(self, raw):
        return self._newer_bytes(self.previous.advance_lock(raw), 'mlf.lock')

    def project_tree_bytes(self, current):
        self._require_raw_map(current, self.value['current_files'], 'DeclId current')
        previous = {p: self._older_bytes(raw, p) for p, raw in current.items()}
        return self.previous.project_tree_bytes({p: previous[p] for p in self.previous.value['current_files']})

    def advance_tree_bytes(self, parent, additions):
        self._require_raw_map(additions, {p: self.value['current_files'][p] for p in self.added_paths},
                                       'DeclId additions')
        old = {p: self._older_bytes(additions[p], p) for p in self.previous.added_paths}
        previous = self.previous.advance_tree_bytes(parent, old)
        result = {p: self._newer_bytes(raw, p) for p, raw in previous.items()}
        result.update({p: raw for p, raw in additions.items() if p not in previous})
        require(self.project_tree_bytes(result) == parent, 'full historical round trip')
        return result

    def host_inventory_to_parent(self, current):
        paths = self.parent['host_inventory']
        require(current == {p: self.value['current_files'][p] for p in paths}, 'complete host inventory')
        return self.previous.host_inventory_to_parent({p: self.previous.value['current_files'][p] for p in paths})

    def advance_host_inventory(self, parent):
        previous = self.previous.advance_host_inventory(parent)
        return {p: self.value['current_files'][p] for p in previous}

    def runtime_inventory_to_parent(self, current, header):
        names = [p for p in self.value['current_files'] if p.startswith('runtime/')]
        require(current == {p: self.value['current_files'][p] for p in names}, 'complete runtime inventory')
        return self.previous.runtime_inventory_to_parent({p: self.previous.value['current_files'][p] for p in names},
                                                         self._older_bytes(header, 'runtime/mlf_byte_file.h'))

    def advance_runtime_inventory(self, parent):
        previous = self.previous.advance_runtime_inventory(parent)
        return {p: self.value['current_files'][p] for p in previous}
