#!/usr/bin/env python3
"""Portable, finite A1 controls. Experimental correctness evidence, never a speed claim.
Requires a complete maintained O2 GHC 9.14.1 producer for this exact registered source.
Only the fresh --output tree is written. See CONTROL-SCOPE.md for limits/provenance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types

OWNER_SHA = '8900a34bf977eaec0d44948be816ca2b5ddb8955170908e7df8fa93967d179df'
KERNEL_SHA = '34bd191f60df38d6bd0229d360d6afbba5e32652f5a43de58b7ec912d5c3be41'
OLD_HEADER = b'module Bootstrap.CrateSession (compileSpecFile) where {'
NEW_HEADER = b'module SessionUnderTest where {'
BUILTIN_HASHES = {'.mlfci': 'e7e79d5aba844f4eeb426bb65c65a4a52831b5274df4bd217ced55a9703f099b',
                  '.mlfco': '3d0e214228cb180d8cee9fb3fd21c5ec6abd8348e1ddd131517831d1f5c2d799'}
TEST_MODULES = {'FrozenMap', 'FrozenIntMap', 'FrozenIntSet', 'FrozenGraph',
                'FrozenSolver', 'FrozenConstraint', 'SessionGraftFixtures',
                'SessionFieldFixtures', 'SessionOracle', 'SessionUnderTest', 'SessionTests'}

# Literal independently authored controls: never regenerate these from the candidate.
CONTROL_HASHES = {'AdmissionTests.hs': '8558f9544bbdf0ea44e9a9364bf910c9187165a477eac955a2821aaa4326f6fb',
 'FileMain.hs': 'a8328405ecb3ada199bf5b479943d99d1989d90dacd3bb16b34c9b7822002a66',
 'FrozenConstraint.hs': '06f363fac6852114e05153eeefb2df42a52dedd6e10100cfa0c0873a0d40334d',
 'FrozenGraph.hs': 'b0729713649072696451523a459efbfa5a528a4f0a71a8421f7daa268f5f9faa',
 'FrozenIntMap.hs': '9e4747f2dc860d706a5f22c0f14d5af582e8f5ad7642a75dca23499b8a697947',
 'FrozenIntSet.hs': 'c4a62314cf86cb2dae81c96ac70790197d2b57a85448d2cc2dd19d90be820c3b',
 'FrozenMap.hs': '0cdeb2b572f38a59e82e5a91d3c47b118b5dc0928292a66849115e1679d18e31',
 'FrozenSolver.hs': '19382b95b1a7deb682166c289f7e74edd9fd73eeda1135c36574fa056c7d548d',
 'SessionFieldFixtures.hs': 'b21593de3186697ec981c8b0b404c7c8387ef48a83ea6350f05effe1f03a615a',
 'SessionGraftFixtures.hs': '91f43ee2c9a865f37e4a510a4c4c1da9fbd4b1c96f8c866d3bcf28b553fc57b8',
 'SessionOracle.hs': 'bafacf6febf934df487b399b08e3c992a7d1f05392f5c5c2b6cd36f7db12660e',
 'SessionTests.hs': '718a05cacb3d52760058a1f57901e9fc37135b7098bd2bd9240428eded06c16f',
 'admission.expected.stdout': 'ea2131a7837992ec56779587749bdc299fb8f7cc4b33efc3e9246551ddd72234',
 'file-cases.json': 'b7878c17609b3c7bf59e4b9a8942b0df61ea2d691edab7de97b102fabe1a94f8',
 'materialize_file_cases.py': '86949be9896ec7530541c62620cfbaa2cc2febd3ec46bbfe78f5a3f74122e241',
 'negative/OpenSession.hs': '33e677aea0e580cb84ce26ac5fb0946230854299bb47505af85bbb3274b760fc',
 'negative/RawSolverRebind.hs': '852b799c94e0ddf5f72b4b1766c5333ec33969ea886003615615568610b647fc',
 'negative/SessionConstructor.hs': 'f724c0e338ab9fc37512fdb64db785f109692ba80adb205360f76cf13a04b8bf',
 'negative/SolvePrepared.hs': '3bdfca1be4694c9dd8a6755096cd9971bc597759a8a0268222f180be2b3a6130',
 'oracle-provenance.json': '78f804385950e45e93b1f29c78869f1aa28962810297ec90bbf30fb0281fb736',
 'session.expected.stdout': '8d478762485f0c3ef50566a9820461f224e1c6d144db71d1dcca6eda3e4f5d19'}

SHARED_HASHES = {'Async.Process': '482169c6d92a16b5a3071088ec24ee7206324995f8e69f6df073cc24559fcb73',
 'Async.Process.Internal': 'ef551f51dcf7da4b48e49f2807e2d5efe84c009cfa911913402c493fce7a25bc',
 'Async.Task': 'cce3de39e4e4fe7537944da1f6b000a8146737340bd0d05ba03fc7e3550acd3b',
 'Async.Task.Core': '0a75da421779203053d535e09367bce368e245e3608b12cad23507358dedf1af',
 'Async.Task.Internal': 'a87ab11e316ec7c4ff28a5f9974b61ecb58aebeeb3f3227646d02ed3e7416e00',
 'Bootstrap.BuiltinPreludeContext': '35d97dc2dac3ef247f593a3b994d33b34770ac1f307de0ed700b46e5a9f17f00',
 'Bootstrap.BuiltinPreludeLiteral': 'e70f9137be94c940548a99d8a4e9fa5eb2954da6e93397405657b37e2abfdb1f',
 'Bootstrap.ClassDemand': '160ccb4889adcb562adf7d99263197d2436b21f5a110c76df6e6ab3b47ead957',
 'Bootstrap.Classes': '3f685123f17509b53cdb2a28dde74d8b54e7459002f7b19c4eb698abef8273dd',
 'Bootstrap.Compiler': '4be4826aca738600a07bd78d7319f05e7e4ffb65d50fe3fd5287890286c7ab1c',
 'Bootstrap.CompilerCore': '00b0274c05dc10f65e5fd2c1df13acdf0382d352c2dd07aa74e79f7c2cdcb8e2',
 'Bootstrap.Constraint': 'e60312de0d78b7604f274d82916bc6f4c87dfb45c2dffefdc89387be37602a90',
 'Bootstrap.Crate': '594af7881473256dcf2bdbb5f57289cfd8cb6cfd471f95f088748d63b1f6150a',
 'Bootstrap.CrateArtifact': 'a1c1668c89707c056737237b213fe4b0b1fe86548db71ae1262c9ad7d6cbcc9e',
 'Bootstrap.CrateCodegen': '3b965481dec681849dbc2fb5172a31fc2b703609a7d379195a2c3338e92011ad',
 'Bootstrap.CrateQuery': 'cf29431eb01eaeb287b89444f80b45fc88de79a2d43f006411821c180647f8eb',
 'Bootstrap.CrateSession': '8900a34bf977eaec0d44948be816ca2b5ddb8955170908e7df8fa93967d179df',
 'Bootstrap.Data': '30c7d22d4640afc393a136eccb24cce84f81f00ff6d92067d2bd56054dca8d16',
 'Bootstrap.Dependency': '5d0082ace3184c213c53f34d9259437506fa3db368d646b3599162018f7db27d',
 'Bootstrap.Desugar': '087d3e310dbd218800d56a77bce8f861981542089f5cd260c04264bf3c33c388',
 'Bootstrap.Elaborate': 'c061b8a6ff668acd5f362c180d8c6ad24c9bb54c219108ea793d968ee4f43c58',
 'Bootstrap.Evidence': 'c533ce20b23c9580f2bddf7e340cb3e8fb813a197e46cc4ea173f705177a9bcd',
 'Bootstrap.EvidenceBoundary': 'fce5aa8a9bfd7b971d8a113f4ddc23379873f0d13ca9c94427139477d6e23f59',
 'Bootstrap.Fresh': '0ed2f1b6d2ffb2a0ea8f1af85acc136470028ab882330b71e9a0194c2f5d63ad',
 'Bootstrap.Graph': 'e631e6031e81aa753ef80ab395bca55a7b4d7a375d76c3e5d588ac3edc4b9fec',
 'Bootstrap.Graph.IndexStore': '34bd191f60df38d6bd0229d360d6afbba5e32652f5a43de58b7ec912d5c3be41',
 'Bootstrap.Graph.Solver': '604662746593712ec29ed968cee7344910c083e57e15965bbf39f3df141d960e',
 'Bootstrap.Host': 'eef45272b5a0c96d651be5e7114470d49a2cb3f1073e3d7aa8e26f9fa70b9ba5',
 'Bootstrap.ImportParameters': '16efe338a956ef66deda14c67251b999dc7934cbe5bd7dfffebbec8b03a2fbcf',
 'Bootstrap.ImportedRoot': '980870a7a9b04b6227b6852ca5ff44a9f54053ea855e95f4728b6d2a6a5bd196',
 'Bootstrap.InferenceUnit': '2f71e6d2ff12f48a2c1ae9f092159163322b15c98a637853e8cd78591ece2a6b',
 'Bootstrap.IntMap': '2bd9dae62e6d44e611e5b4adb216efffe9d275c05d249f2904f2e076d12b23de',
 'Bootstrap.IntSet': '324d2bfd384485c0008c80f6567862d572afeae0da4d839cbbbe8cba7748d1d6',
 'Bootstrap.Kind': '453aebe46c80250d50a32ae84b9f5d1bb56f2effbe94018d0e67742fbffb4f3b',
 'Bootstrap.Kinding': 'c0188208294013e2c2645e01bc1dedf6a8dcf10f4a35b1a128b82bb485cc960c',
 'Bootstrap.LLVM': '7429fbc5391cef1f5fd3f507e0381f7a8eacbf19637a247398ca269e966f6fb7',
 'Bootstrap.LLVM.Analysis': 'b10dbe9ea529646a375f50144ffb4dbac5b2c3ac5453e02170334f78fd57e65e',
 'Bootstrap.LLVM.Argument': '8d8a897eb4019ad40fe5cb756a30fd8c789e4c745205e654254bbf702d12710b',
 'Bootstrap.LLVM.Build': '267c95569175161aeb8944aabbef85ea1f77ead11ba48146a7c3a17ad6d950d1',
 'Bootstrap.LLVM.Codegen': 'd92907fe8eb08163a430cd6a52b6ea3a420d04d3a2817b56fa2d809a1d96d08b',
 'Bootstrap.LLVM.Kernel': '46ae5be45d9c6f58a61a1c52856bd11befeb3b6fa4ed7c7b09118a9226948642',
 'Bootstrap.LLVM.LazyProducer': '88d750f0671a228da67403a555a43b71054dee8307da88e5070752474e1cf7c8',
 'Bootstrap.LLVM.Native': '782a711fe63b372c575748dfe315e85d2c2f021a7e8f501285ab47315819e3ef',
 'Bootstrap.LLVM.Optimize': 'd84190afcae0fb9ad347e8116b6eb98f78ccdeaedd9491e6a6a47e1e119e9ff9',
 'Bootstrap.LLVM.Result': '792da71fe323dee4b2497b552c090e38e98f6f51d6997ee9da07286420f1396e',
 'Bootstrap.LLVM.StrictFields': '50c76597138b9fe9c7a4eeba22976f096b513038450c830f4e204059c2a91d9e',
 'Bootstrap.LLVM.StrictWrappers': 'b8e09c8fe3af9f14c7e7b6f6deae008ada04fc84923a41fa5c29d1e16857ed13',
 'Bootstrap.Layout': '9d602c1743537623ae64a34dc6d34ee79c367ee57cb4214dc7e2e8509a9de411',
 'Bootstrap.Lexer': '9c681c46059d62f430c71e783d77b74ed7e0898225a148b4116995a5a2155179',
 'Bootstrap.Map': 'd4d9ebfa39a14ae1cbaf48fa9d540eafa7b452aaa3cc73ffc624a34c15417bdb',
 'Bootstrap.Module': 'cc4c4d74e7a9a0bf3432f71d782044bf807d118ecbf82a07717ef54a5e0b9ca6',
 'Bootstrap.Parsec': '38cce5767b935e27292b0c0fb35f1750e3d02ff5ef5ef111c615b04001ebce90',
 'Bootstrap.Parser': 'd6fcd9881700b9dd91077ca2db863076f3d4974688fbb4dbe42d97b96b82872d',
 'Bootstrap.Prelude': '98bb607ff4732abe7a169a9ae6bd6e9a641ef5d2bce2b9c2584d2bf9c4779319',
 'Bootstrap.PreparedLibraries': 'a7a0e9cecb93931fa44d04b7fd57e768c03a2eea8c3802af509ac5abcf510c15',
 'Bootstrap.PreparedLibraryLiteral': 'f69507ec31c555af9bcd0fcc14f30770ad381a4bae6eee4fdb9073becd7a297d',
 'Bootstrap.Primitive': 'd5ab2e97d7c217143311ff81c09075f9f9adb96ecf9f0cfe285e274e28130e23',
 'Bootstrap.ProcessHost': '2fcd44e92c3b0a889e7ed16316ed68209f940f357fdb68b049c596f6d3a3dc24',
 'Bootstrap.Regex': '016cda4d5a9cd2ed0161976ab4150d74c1b2843cb6a5a046aef72eccc1945b0d',
 'Bootstrap.Runtime': '8a5186d9552bb947f67142c943446cf1c3b79faa4c3279e2f58022b8c1b5a577',
 'Bootstrap.ST': '64ec30dba979baefb17dd180ebef79179c9ddc60197562263cb0abd5e7f78ca2',
 'Bootstrap.Separate': 'febdf27bf8e4e37166461b8b0abeb89d95a7ef6de2a93d254a6f413cf8ee4abb',
 'Bootstrap.Set': 'c2222cc52e2ee750a92d563f8f513ecf4eb60b1afd534b91a37b7c5d5ba6e60f',
 'Bootstrap.SourceEquality': '031ca10290b4b6bce9526c65fc6cbcea096def8df17fd6e9333710480d52077a',
 'Bootstrap.SourceInference': '6d52680450b2a49b170033b0c7266565a9f7ad3c5ec2d24a61b328074e16f2a9',
 'Bootstrap.Standalone': '37f77c259d0b699ab49c5df5d6041485e726d392a0b4b3a6b8adcff3c0e2a027',
 'Bootstrap.Std': '0eb137b5935bdf13ed6807c2a4aa96bb558bfce37fd39c9fb08897bb63eedbff',
 'Bootstrap.Surface': '6722b465232d5e88692bea0fdddfa07c02eb1c5fa65476c7fdb922042a194ff8',
 'Bootstrap.Types': 'c8bf3c734fa5c7e4c9b1f546774fb7dbfac9cc872fc7194f18cacb53d332132a',
 'Bootstrap.Unicode': 'fb8a1f8a0147d416d3b5bfd637d53121e584de6f8856d2c380ec360d2df47adf',
 'Bootstrap.Version': '25472aacf1647006d271a72c72f6790252f6e4b6508cd9d7de29d2628fdb0479',
 'Bootstrap.X.Check': 'abaaab6552efcb096a3d26a05c552d7ac362c96467e7604eca7d1174f56797aa',
 'Bootstrap.X.Checked': '0cf5be5536d4fdf747050b6a610345868a8c7ff1b1beb7885f68cd677e0c04e1',
 'Bootstrap.X.Parser': '4f76dc195e444ceffbd2a84824b9b402deb560b52e854251ef8480b765d9126d',
 'Bootstrap.X.Pretty': 'd4840c8c31b8f6bb82587590a4ab48ed8d664c96ba22c9daf70ae19c5e8ad8d9',
 'Bootstrap.X.Syntax': '654d43b2739219704757cd3a3ee0e9f8106ae07ec931eb1a399dd004af1c0a9d',
 'Bootstrap.X.Type': 'f077d4ffccc9e194f017505aa1d592aace677219198a6a5c2190271db7816233',
 'MLF.BuiltinPreludeData': '78d4c5f399601472c971919c2171045494bee67c51e344f086e28c2cef677cd2',
 'MLF.Entry.BuiltinPrelude': '0130e6af538c4bcfd27aa3b4a223b63eb147e5b1eb30017288bceb1074a1abb1',
 'MLF.Entry.CompilerTests': '45d7fdabe9d3ed340442f4154a7e953ff7df7279b788570d7e976b1d22c41695',
 'MLF.Entry.Emlf': '6db4d30215283d554b8ee954d17c0c317f4a67ae7059044b33d1b5fa379b45c1',
 'MLF.Entry.Mlfpkg': '26dab5260f36e5d67ba85d4c74ab4cad6bd76b8772056ea1f22d7e9ea0264711',
 'MLF.Entry.TupleList': 'e817f6037216da8cff7d615e617adcccd58bf687b6e9dacc3155ad8e4a9f6bd8',
 'MLF.PreparedCompiler': '271caba2c443258fb4e0961be87d0750716c867ddb36ef6c85e8f77165423b10',
 'MLF.PreparedLibraryData': '7a2f084b10c7551690f37b697e7b3f46dca409316606015775636c033b716b23',
 'MLF.Tests.Async.ProcessMain': '02b89ab2a2bd6f28b9467a00556011a67553e6cc1fcaef07dc51bd3145249403',
 'MLF.Tests.Async.ProcessPanic': '8ac29bd22ba71fe3b1f0782f056f6f31809d509e81bec695d18f7f887ee4016e',
 'MLF.Tests.Async.TaskMain': '9226652954c07a9d66ba4449294a8c76db85853dc3c42a22984e5817bd7f3148',
 'MLF.Tests.Async.TaskProcesses': '7b267a43750ca73a288732d9ebaa23327a4911ab5675150d5c1a8dfa3e587770',
 'MLF.Tests.Async.TaskWaitGraph': '3158b5c76450655a33c83d5d8164143163f9e6f991a91735826a9e06f96dc998',
 'MLF.Tests.BuildReceipts': '076d24d34268981dcbe346759233dbdb7b1f20bb4de089282d05472d06939025',
 'MLF.Tests.ClassDemand': '585bc63568109dfc2dee9ddb5eb0cc4906c03f9ccc7772226eb85dc4da02c373',
 'MLF.Tests.PRQuickMain': '93ed93ca006a71ba54de6aafe3eb9ae0c921c5dca5c4cce9c03c0b0180bcb5bd',
 'MLF.Tests.SharedFrontend': '5bff1513b7f401241ebbff89888ad8790bd92d0ee7858d8148bc7cec334f735a',
 'Package.Benchmark': '089024c9213e36e5e591bffca6ba8605d127d518f4432164adf9ae9080669aa8',
 'Package.Build': '9df00f9622c9a1acafc2d6068980dadf56cafd33886c644b5bffb995a84152d8',
 'Package.Command': 'f8865613d8fb3b39dd1883fb9fe833e2db0b7fccdc61b2667d50688d9f65d0e4',
 'Package.Distribution': 'aa7b8731e88f838670374ca27a9bfbe26c22e4ff0d7021867c0d85f9e0ae88c8',
 'Package.Json': '90c6e3ad566b92c01bf58106c27a5d467a52f11586ddad9fa1e44c2a62165604',
 'Package.Manifest': '94cbf379adb03fb3f23bdf7c4fdb0b89d31a6f6c33313fcdac2ad112e0c1d111',
 'Package.OS': 'ff025ef05b6cb63c5591b756a78b898f50497cc5349bdc5d19812f47a6dadda2',
 'Package.Release': 'f8aa3f7fa140ac31d92d58f927d900c9923ba52c089122e9926107518e781377',
 'Package.Scheduler': 'd112b06cd45f41a0c752f663233b35c3c9fb66c1ea68dd3000561499961d570d',
 'Package.Verification': '5863313b16d6058ded44ff8b46840f1534ffb2db02ff420911c382b2b68ab301',
 'Test.Assert': 'd9bb577af733f709258a4947bde82c3bf3ecf456e628a856c237ee7302f6f90a',
 'Test.Case': 'b14985f9e1120413c91db2875b03cf714d3394150d1036d2d79b7db5095c285d',
 'Test.Descriptor': 'b8e92bc8e18463ed699cf93cdeb3082fc2c408edbcca6db90fdbf5c68c793557',
 'Test.Expectation': '14a7492852ff8db61fb05db9fce1454be55b29a5fdb58dbbc35508fac13b76f7',
 'Test.Outcome': 'fecc98b6da70df3bfb8bc03bb627cf71d103afe7a45f9f524fa17194c5c9059f',
 'Test.Registry': '0c3f623eb5ebb23de0f586f29b5c4a7b3470217778e8dfc5b2bd738de2ca2236',
 'Test.Runner': '92bbadd2ad1a076648c00c9d6d31dd519a1d5162ac040d502d50710dd48ed927',
 'Tests.BuildReceipts': '05a0d967492413b3fa68055202c7821c08355ede167ea264be1ad992b6d9b1c0',
 'Tests.Catalog': '9fbc4f7ef554a654e1b933a9bbb8335ad23834df168572c1cd737b3154625a78',
 'Tests.CompilerTests': 'f3f6c319a4a676e62b89aaca739dee1de5b2d46fba14eb95fe4aa12e89c034ca',
 'Tests.CorePartitions': 'b020a93ed6d93bf92766016f06ad6eb59f89b7c3b288b934b3568c28cc14284b',
 'Tests.Coverage': '38ac76ab4abe5d17a53f6c8e66dd52bf8b3b718920ccab99f25909680516e7ff',
 'Tests.IndependentCheck': '64800f6cf21e0d6dae65c02491ec4a56ce6a3f21056d73cd12c9693b45451757',
 'Tests.IndependentType': '04ce5f659b2a515cb89c32cbb5d3889545f90b91faae806f1792c1f48c794642',
 'Tests.Selection': '8a53a01a1af9b5c5d18eccb0dc7ab370f4a829dda73f09ebd3c420f7cb8967fd',
 'Tests.TestDrivers': '00689b5924b1b03d4dbedf228fad2a8735439a9df902870916fd538a11f2b511',
 'Tests.TestSources': 'f68293bcdd472babf62ff3ef201325af451079186290ea91efe1c0cb30d7893f',
 'Tests.TupleList': '2ff183466ff22c3627aa58f0b73d9503ef1dc979f7b0e9c1f7744cd9933996f8',
 'Tests.TupleListLegacy': '60176aca5512cf858f1c5fcde5819741a28073b4b504049a301a54f0492ab6b0'}

NEGATIVE_CASES = [{'category': 'production export privacy; no missing dependency or unrelated error accepted',
  'expected_error_count': 1,
  'expected_exit_code': 1,
  'module': 'OpenSession',
  'name': 'OpenSession',
  'required_error_fragments': ['does not export', 'openSession']},
 {'category': 'production export privacy; no missing dependency or unrelated error accepted',
  'expected_error_count': 1,
  'expected_exit_code': 1,
  'module': 'SolvePrepared',
  'name': 'SolvePrepared',
  'required_error_fragments': ['does not export', 'solvePrepared']},
 {'category': 'production export privacy; no missing dependency or unrelated error accepted',
  'expected_error_count': 1,
  'expected_exit_code': 1,
  'module': 'SessionConstructor',
  'name': 'SessionConstructor',
  'required_error_fragments': ['does not export', 'Session']},
 {'category': 'raw Solver cannot enter sealed file factory; authenticated interfaces only',
  'expected_error_count': 1,
  'expected_exit_code': 1,
  'module': 'RawSolverRebind',
  'name': 'RawSolverRebind',
  'required_error_fragments': ["Couldn't match", 'Solver', 'String']}]

def req(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify(pins):
    for path, digest in pins.items():
        req(sha(path) == digest, 'immutable input changed: ' + str(path))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def files_below(directory):
    req(not any(p.is_symlink() for p in directory.rglob('*')), 'no symlinked object inputs')
    return {str(p.relative_to(directory)): sha(p) for p in directory.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--builtin-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, build = args.source_root.resolve(strict=True), args.producer.resolve(strict=True)
    out = args.output.resolve()
    req(not out.exists(), 'fresh output required; retain failures and choose a new directory')
    req(not source.is_relative_to(out) and not build.is_relative_to(out) and
        not out.is_relative_to(build), 'output must not contain source/producer or modify producer')
    runner = Path(__file__).resolve()
    req(runner == source / 'tools/performance/a1-private-index/run_controls.py', 'runner/source-root binding')
    controls = runner.parent / 'controls'
    pins = {str(controls / rel): digest for rel, digest in CONTROL_HASHES.items()}
    verify(pins)
    req((controls / 'session.expected.stdout').read_bytes().count(b'PASS ') == 6,
        'six original finite session groups')
    original_cases = json.loads((controls / 'file-cases.json').read_text())
    req(original_cases['case_count'] == len(original_cases['cases']) == 9, 'nine literal file cases')
    bp = build / 'receipt.json'
    auth_file = source / 'tools/shared/test_direct.py'
    auth = types.ModuleType('a1_official_producer_auth')
    auth.__file__ = str(auth_file)
    exec(compile(auth_file.read_bytes(), str(auth_file), 'exec'), auth.__dict__)

    def authenticate():
        value = auth.authenticate_build(bp, build / 'bin', root=source)
        req(value['optimization'] == '2' and len(value['resolved_modules']) == 123 and
            len(value['inferred_shared_interfaces']) == 123, 'complete official O2 123-module producer')
        req({name: row['sha256'] for name, row in value['shared_inputs'].items()} == SHARED_HASHES,
            'exact registered experimental A1 production source snapshot')
        req(Path(value['build_driver']['path']) == source / 'tools/shared/build.py', 'producer source root')
        return value

    producer = authenticate()
    owner = source / 'libraries/mlf-crates/Bootstrap/CrateSession.hs'
    kernel = source / 'libraries/mlf-inference/Bootstrap/Graph/IndexStore.hs'
    req(sha(owner) == OWNER_SHA and sha(kernel) == KERNEL_SHA, 'exact controlled private implementation')
    raw = owner.read_bytes()
    req(raw.count(OLD_HEADER) == 1 and NEW_HEADER not in raw, 'sole sealed production header')
    copied_raw = raw.replace(OLD_HEADER, NEW_HEADER)
    req(copied_raw.count(NEW_HEADER) == 1 and copied_raw.replace(NEW_HEADER, OLD_HEADER) == raw,
        'byte-exact inverse of test-only module/export header change')
    links = [row for row in producer['commands'] if Path(row['log']).name == 'link-emlf.log']
    req(len(links) == 1 and links[0]['exit_code'] == 0 and links[0]['cwd'] == str(source),
        'one successful authenticated emlf link')
    prior = dict(argv=links[0]['argv'])
    expected_link = [producer['ghc']['path'], '--make', '-j1', *producer['flags'],
                     '-rtsopts=ignoreAll', str(source / 'host/ghc/app/emlf/Main.hs'),
                     str(build / 'host.o'), str(build / 'supervisor.o'), '-o', str(build / 'bin/emlf')]
    req(prior['argv'] == expected_link and producer['flags'].count('-i') == 1 and
        '-O2' in producer['flags'], 'unaltered maintained producer link and import-reset flags')
    inputs = {str(runner): sha(runner), str(auth_file): sha(auth_file), str(bp): sha(bp), **pins}
    for field in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers']:
        for item in producer[field].values():
            inputs[item['path']] = item['sha256']
    inputs.update({item['path']: item['sha256'] for item in producer['outputs'].values()})
    object_baseline = files_below(build / 'objects')
    req({'objects/' + rel: digest for rel, digest in object_baseline.items()} == producer['object_inputs'],
        'exact complete authentic Haskell object inventory, without unexpected extras')
    inputs.update({str(build / 'objects' / rel): digest for rel, digest in object_baseline.items()})
    c_objects = {}
    for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        path = build / (name + '.o')
        rows = [row for row in producer['commands'] if Path(row['log']).name == 'c-' + name + '.log']
        expected = [producer['cc']['path'], '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                    '-c', str(source / relative), '-o', str(path)]
        req(len(rows) == 1 and rows[0]['argv'] == expected and rows[0]['exit_code'] == 0 and
            rows[0]['cwd'] == str(source), 'authenticated C source/command/output binding: ' + name)
        req(path.is_file() and path.resolve() == path, 'regular resolved C object')
        c_objects[name + '.o'] = sha(path)
        inputs[str(path)] = c_objects[name + '.o']
    builtin_prefix = str(args.builtin_prefix.resolve())
    builtin_pins = {builtin_prefix + suffix: digest for suffix, digest in BUILTIN_HASHES.items()}
    inputs.update(builtin_pins)
    verify(inputs)
    contract = dict(expected_stdout=(controls / 'session.expected.stdout').read_text(),
                    admission_expected_stdout=(controls / 'admission.expected.stdout').read_text(),
                    materializer_stdout='PASS materialized nine independent parsed-file controls\n',
                    materializer_stderr='', admission_inventory=dict(hand_positive=8, exact_error=8,
                    counter_demand=3, local_ordering=3), negative_cases=[])
    for case in NEGATIVE_CASES:
        contract['negative_cases'].append({**case, 'source': str(controls / 'negative' / (case['name'] + '.hs'))})
    out.mkdir(parents=True)
    (out / 'tmp').mkdir()
    generated = out / 'test-source'
    generated.mkdir()
    test_copy = generated / 'SessionUnderTest.hs'
    test_copy.write_bytes(copied_raw)
    inputs[str(test_copy)] = sha(test_copy)
    req(test_copy.read_bytes().replace(NEW_HEADER, OLD_HEADER) == owner.read_bytes(), 'written copy inverse')
    save(out / 'test-copy-receipt.json', dict(complete=True, test_copy_not_production=True,
         original=str(owner), original_sha256=OWNER_SHA, copy=str(test_copy), copy_sha256=sha(test_copy),
         old_header=OLD_HEADER.decode(), new_header=NEW_HEADER.decode(),
         only_module_name_and_export_list_changed=True, byte_exact_inverse_verified=True))
    contract['module_sources'] = {name: str(controls / (name + '.hs'))
                                  for name in TEST_MODULES | {'FileMain', 'AdmissionTests'}}
    contract['module_sources']['SessionUnderTest'] = str(test_copy)
    objects = out / 'objects'
    shutil.copytree(build / 'objects', objects)
    req(files_below(objects) == object_baseline, 'exact authenticated production object copy')
    for suffix in ['.hi', '.o']:
        (objects / ('Main' + suffix)).unlink()
    immutable_objects = {str(p): sha(p) for p in objects.rglob('*') if p.is_file()}
    for name, digest in c_objects.items():
        shutil.copy2(build / name, out / name)
        inputs[str(out / name)] = digest
    # Preserve the original Linux UTF-8 control environment.
    env = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1',
           'TMPDIR': str(out / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
    for key in list(env):
        if key.startswith('MLF_DIAGNOSTIC_'):
            del env[key]
    receipt = dict(complete=False, all_controls_passed=False, qualified=False, goal_evidence=False,
                   experimental_not_accepted=True, official_producer_authenticated=True,
                   production_owner_sha256=OWNER_SHA, inputs=inputs, test_copy_only=True,
                   candidate_output_used_for_expectations=False, commands=[], file_cases=[],
                   source_root=str(source), producer=str(build), shared_builtin_prefix=builtin_prefix,
                   builtin_provenance='Exact path-independent frozen builtin pair; not rebuilt by this runner',
                   c_object_provenance='Successful authenticated producer C commands, actual local hashes pinned before/after; producer schema does not itself store C object digests',
                   c_object_sha256=c_objects)
    save(out / 'receipt.json', receipt)
    def run(label, command, cwd=source):
        before = time.perf_counter_ns()
        with (out / (label + '.stdout')).open('wb') as so, (out / (label + '.stderr')).open('wb') as se:
            result = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=so, stderr=se)
        row = dict(label=label, argv=command, cwd=str(cwd), exit_code=result.returncode,
                   process_wall_ns=time.perf_counter_ns() - before,
                   stdout_sha256=sha(out / (label + '.stdout')),
                   stderr_sha256=sha(out / (label + '.stderr')))
        receipt['commands'].append(row)
        save(out / 'receipt.json', receipt)
        return result.returncode, (out / (label + '.stdout')).read_bytes(), (out / (label + '.stderr')).read_bytes()

    def build_driver(module, wanted):
        wrapper = out / (module + '-Main.hs')
        wrapper.write_text('{-# OPTIONS_GHC -O0 #-}\nmodule Main where\n'
                           'import qualified ' + module + ' as Driver\n'
                           'main :: IO ()\nmain = Driver.main\n')
        inputs[str(wrapper)] = sha(wrapper)
        for suffix in ['.hi', '.o']:
            (objects / ('Main' + suffix)).unlink(missing_ok=True)
        command = []
        for token in prior['argv']:
            token = {str(build / 'objects'): str(objects),
                     str(build / 'host.o'): str(out / 'host.o'),
                     str(build / 'supervisor.o'): str(out / 'supervisor.o'),
                     str(build / 'bin/emlf'): str(out / module),
                     str(source / 'host/ghc/app/emlf/Main.hs'): str(wrapper)}.get(token, token)
            command.append(token)
            if token == '-i':
                command += ['-i' + str(generated), '-i' + str(controls)]
        code, so, se = run('compile-' + module, command)
        req(code == 0, 'control compilation failed: ' + module)
        rows = re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*([^,\n]+),',
                          (so + se).decode(), re.M)
        actual = {name: str((source / path.strip()).resolve()) for name, path in rows}
        expected = {name: contract['module_sources'][name] for name in wanted}
        expected['Main'] = str(wrapper)
        req(len(rows) == len(expected) and actual == expected, 'exact fresh control module closure')
        verify(immutable_objects)
        return out / module

    try:
        session_driver = build_driver('SessionTests', TEST_MODULES)
        code, so, se = run('session-tests', [str(session_driver)])
        req(code == 0 and so == contract['expected_stdout'].encode() and se == b'',
            'six independent finite session groups')
        receipt['session_groups_passed'] = 6
        receipt['finite_trace_cases'] = 28
        save(out / 'receipt.json', receipt)
        admission_driver = build_driver('AdmissionTests', {'AdmissionTests'})
        code, so, se = run('admission-tests', [str(admission_driver)])
        req(code == 0 and so == contract['admission_expected_stdout'].encode() and se == b'',
            'independent direct-admission controls')
        receipt['admission_controls_passed'] = True
        receipt['admission_inventory'] = contract['admission_inventory']
        save(out / 'receipt.json', receipt)
        file_driver = build_driver('FileMain', {'FileMain'})
        files = out / 'files'
        code, so, se = run('materialize-files', [sys.executable, '-B', str(controls / 'materialize_file_cases.py'),
                                               '--output', str(files), '--builtin-prefix', builtin_prefix])
        req(code == 0 and so == contract['materializer_stdout'].encode() and
            se == contract['materializer_stderr'].encode(), 'authored file materialization')
        materialized = json.loads((files / 'materialized.json').read_text())
        req(materialized['complete'] and materialized['materialization_only'] and
            len(materialized['cases']) == 9, 'exact nine finite file cases')
        req(materialized['shared_builtin_prefix'] == builtin_prefix and
            materialized['shared_dependency_pins'] == builtin_pins, 'identical immutable dependency input')
        req([row['name'] for row in materialized['cases']] == [row['name'] for row in original_cases['cases']],
            'same ordered literal file case inventory')
        req(materialized['artifact_comparison_suffixes'] == ['.mlfci', '.mlfco', '.queries'],
            'all original exact artifact comparisons, no normalization')
        for case in materialized['cases']:
            verify(case['source_pins'])
            inputs.update(case['source_pins'])
            req(all(not Path(p).exists() for p in case['missing_sources']), 'authored missing source')
            outcomes = []
            for side in case['runs']:
                spec = Path(side['spec'])
                req(sha(spec) == side['spec_sha256'], 'authored spec bytes')
                inputs[str(spec)] = side['spec_sha256']
                req(list(Path(side['cache']).iterdir()) == [], 'each target cache begins empty')
                label = 'file-' + case['name'] + '-' + side['implementation']
                code, so, se = run(label, [str(file_driver), *side['argv']], files)
                req(code == 0 and se == b'', 'file control failed: ' + label)
                wanted = case['expected_type']
                if wanted == 'reject':
                    req(so.startswith(b'REJECT ') and so.endswith(b'\n') and so.count(b'\n') == 1,
                        'ordinary complete rejection line')
                    for fragment in case['required_error_fragments']:
                        req(fragment.encode() in so, 'handwritten error fragment')
                    if 'exact_error' in case:
                        req(so == ('REJECT ' + json.dumps(case['exact_error'], ensure_ascii=False) + '\n').encode(),
                            'handwritten exact rejection')
                    req(not Path(side['prefix'] + '.mlfci').exists() and
                        not Path(side['prefix'] + '.mlfco').exists(), 'no checked artifacts from rejection')
                    artifacts = {}
                else:
                    req(so == ('PASS file checked ' + wanted + '\n').encode(), 'handwritten file type oracle')
                    report = json.loads(Path(side['prefix'] + '.queries').read_text())
                    req(report['inferred_groups'] > 0 and report['reused_groups'] == 0 and
                        len(report['groups']) == report['inferred_groups'] and
                        all(not row['cached'] for row in report['groups']), 'every successful file group fresh')
                    artifacts = {suffix: sha(Path(side['prefix'] + suffix))
                                 for suffix in materialized['artifact_comparison_suffixes']}
                outcomes.append(dict(implementation=side['implementation'], stdout=so.decode(), artifacts=artifacts))
            req([x['implementation'] for x in outcomes] == ['old', 'session'] and
                outcomes[0]['stdout'] == outcomes[1]['stdout'] and
                outcomes[0]['artifacts'] == outcomes[1]['artifacts'], 'exact independent old/private file comparison')
            receipt['file_cases'].append(dict(name=case['name'], complete=True, outcomes=outcomes))
            save(out / 'receipt.json', receipt)
        object_pins = {str(p): sha(p) for p in objects.rglob('*') if p.is_file()}
        req(len(contract['negative_cases']) == 4, 'four sealed interface negatives')
        for case in contract['negative_cases']:
            target = out / ('negative-' + case['name'])
            target.mkdir()
            flags = []
            original_flags = iter(producer['flags'])
            for flag in original_flags:
                if flag in ['-odir', '-hidir']:
                    next(original_flags)
                    continue
                if flag == '-i' or flag.startswith('-i/'):
                    continue
                flags.append(flag)
            command = [producer['ghc']['path'], '-c', '-fno-code', '-fno-write-interface', *flags,
                       '-i', '-i' + str(objects), '-odir', str(target), '-hidir', str(objects),
                       '-ohi', str(target / (case['module'] + '.hi')), case['source']]
            code, so, se = run('negative-' + case['name'], command)
            diagnostic = (so + se).decode()
            compared = diagnostic.lower() if case.get('fragments_case_insensitive') else diagnostic
            fragments = [x.lower() if case.get('fragments_case_insensitive') else x
                         for x in case['required_error_fragments']]
            req(code == 1 and all(fragment in compared for fragment in fragments), 'intended interface rejection')
            req(len(re.findall(r'\berror:', diagnostic, re.I)) == case['expected_error_count'] and
                Path(case['source']).name in diagnostic, 'negative source and error count')
            req(not any(x in diagnostic.lower() for x in ['could not find module', 'panic!', 'internal error',
                                                          'parse error']), 'unrelated failure is not interface proof')
            verify(object_pins)
        verify(inputs)
        verify(immutable_objects)
        authenticate()
        req(sha(owner) == OWNER_SHA and sha(kernel) == KERNEL_SHA, 'post-control source freeze')
        req(files_below(build / 'objects') == object_baseline, 'producer object inventory unchanged')
        receipt.update(complete=True, all_controls_passed=True, negative_cases_passed=4,
                       immutable_inputs_verified_after=True)
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['outputs'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and p != out / 'receipt.json'}
        save(out / 'receipt.json', receipt)
    print('PASS A1 controls: 6 groups, 28 traces, 22 admission, 9 files, 4 seal negatives; no speed claim')


if __name__ == '__main__':
    main()
