{-# LANGUAGE OverloadedStrings #-}
-- Separate producer/consumer inference uses decoded metadata, never producer source.
module Main where
import Prelude
import Data.List (isInfixOf, isPrefixOf)
import System.Directory(removeFile)
import qualified Bootstrap.X.Type as XT
import System.Environment (getArgs)
import System.IO (hSetBuffering, stdout, BufferMode(LineBuffering))
import qualified Bootstrap.Types as T
import qualified Bootstrap.Parser as P
import qualified Bootstrap.Crate as C
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified MLF.Host.Base as B
list = foldr (:) []
toList [] = []
toList ((:) x xs) = x : toList xs
expect label value = case value of
  T.Left e -> error (label ++ ": " ++ B.unpack e)
  T.Right x -> pure x
check label ok = if ok then putStrLn ("PASS " ++ label) else error label
source name exports body = B.literal $ "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule " ++ name ++ exports ++ " where\nimport MLF.Primitive\n" ++ body ++ "\n"
roundtrip obj = do
  iface <- expect "decode interface" (A.decodeInterface (A.encodeInterface (A.objectInterface obj)))
  expect "decode pooled object" (A.decodeObject iface (A.encodeObject obj))
compile base name entry exports body deps = compileText base name entry T.NoImplicitPrelude (source name exports body) deps
compileText base name entry mode text deps = do
  let extension = if "-- mlf:syntax" `isPrefixOf` B.unpack text then ".hs" else ".emlf"
      path = B.literal (base ++ "/" ++ name ++ extension)
      spec = C.CrateSpec (B.literal ("item4:" ++ name)) (B.literal entry) mode
        (list [(,) (B.literal name) path]) (list [p | (p,_) <- deps])
        (B.literal (base ++ "/cache-" ++ name)) (B.literal (base ++ "/builtin"))
      interfaces = list [(,) p (A.objectInterface o) | (p,o) <- deps]
  writeFile (B.unpack path) (B.unpack text)
  parsed <- C.loadSourcesInPackage (C.specIdentity spec) (C.specSources spec) >>= expect "load own source with crate package identity"
  prepared <- expect "prepare against metadata" (C.prepareCrate spec interfaces parsed)
  (,) obj _ <- C.compilePrepared spec interfaces prepared >>= expect "compile separate crate"
  roundtrip obj
value objects root = do
  term <- expect "link decoded objects" (A.linkObjects (list objects) (A.crateId (A.objectInterface root)))
  (,) env _ <- expect "prepare runtime" (R.prepare False term)
  v <- expect "evaluate linked term" (R.evaluate env (R.REnv M.empty) (X.erase term))
  pure (env,v)
compileMetadata base name entry body paths=do
 let path=B.literal(base++"/"++name++".hs")
     spec=C.CrateSpec(B.literal("item4:"++name))(B.literal entry)T.NoImplicitPrelude [(B.literal name,path)] paths (B.literal(base++"/cache-"++name)) (B.literal(base++"/builtin"))
 writeFile(B.unpack path)(B.unpack(source name "" body))
 loaded<-A.loadInterfaces paths >>=expect "load metadata-only dependencies"
 own<-C.loadSourcesInPackage(C.specIdentity spec)(C.specSources spec)>>=expect "load only own source"
 prepared<-expect "prepare actual source route"(C.prepareCrate spec loaded own)
 check "actual module uses source SCC route"(case C.preparedSourcePlan prepared of T.Just _->True;_->False)
 (object,report)<-C.compilePrepared spec loaded prepared >>=expect "actual source SCC crate"
 decoded<-roundtrip object
 let metadata=B.literal(base++"/"++name++".mlfci")
 writeFile(B.unpack metadata)(B.unpack(A.encodeInterface(A.objectInterface decoded)))
 pure(metadata,decoded,report)
scheme iface spelling=let name=A.definitionName(A.crateId iface)(Modules.Entity (head(A.crateModules iface)) (B.literal spelling) Modules.Value) in case lookup name(A.crateBindings iface)of Just ty->ty;_->error "missing scheme"
flag iface spelling=let name=A.definitionName(A.crateId iface)(Modules.Entity (head(A.crateModules iface)) (B.literal spelling) Modules.Value) in case lookup name(A.crateProtection iface)of Just b->b;_->error("protection lookup "++spelling++" missing "++B.unpack name)
main=do
 hSetBuffering stdout LineBuffering
 [base]<-getArgs
 builtin<-expect "builtin compile" A.builtinPrelude >>=roundtrip
 let bp=B.literal(base++"/builtin.mlfci")
 writeFile(B.unpack bp)(B.unpack(A.encodeInterface(A.objectInterface builtin)))
 (pp,provider,_)<-compileMetadata base "Provider" "" "who = let { ignored = callStack } in 42\nordinary = 21\nequal = (42 :: Int) == 42\nsignedOrdinary :: Int\nsignedOrdinary = if (1 :: Int) == 1 then 42 else 0" [bp]
 check "ordinary source helper remains unprotected"(not(flag(A.objectInterface provider)"ordinary"))
 check "signed compareInt-like helper ignores visible managed instances"(not(flag(A.objectInterface provider)"signedOrdinary"))
 check "provider protected helper has exact plain Int target"(XT.alphaEq(scheme(A.objectInterface provider)"who")(T.XCon "Int" []))
 check "unsigned managed helper plain-type retains protection"(flag(A.objectInterface provider)"who")
 let facadeText=source "Facade" " (module P)" "import Provider as P"
 facade<-compileText base "Facade" "" T.NoImplicitPrelude facadeText [(bp,builtin),(pp,provider)]
 let fp=B.literal(base++"/Facade.mlfci")
 writeFile(B.unpack fp)(B.unpack(A.encodeInterface(A.objectInterface facade)))
 removeFile(base++"/Provider.hs")
 (cp,consumer,_)<-compileMetadata base "Consumer" "Consumer" "import Facade\nmain = who\nordinaryCopy = signedOrdinary" [fp,bp]
 check "metadata reexport preserves ordinary signed helper nonprotection"(not(flag(A.objectInterface consumer)"ordinaryCopy"))
 check "consumer has exact plain Int target"(XT.alphaEq(scheme(A.objectInterface consumer)"main")(T.XCon "Int" []))
 check "metadata-only facade preserves empty-overload managed protection"(flag(A.objectInterface consumer)"main")
 (_,result)<-value[builtin,provider,facade,consumer]consumer
 check "decoded final objects link and run"(case result of R.RInteger 42->True;_->False)
 (_,warm,warmReport)<-compileMetadata base "Consumer" "Consumer" "import Facade\nmain = who\nordinaryCopy = signedOrdinary" [fp,bp]
 check "actual crate warm all raw hits"(Q.inferredCount warmReport==0&&Q.reusedCount warmReport>0)
 check "actual crate warm artifact exact parity"(A.encodeObject consumer==A.encodeObject warm)
 putStrLn "PASS actual metadata-only protected facade source SCC"
