{-# LANGUAGE OverloadedStrings #-}
-- Separate producer/consumer inference uses decoded metadata, never producer source.
module Main where
import Prelude
import Data.List (isInfixOf, isPrefixOf)
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
main = do
  hSetBuffering stdout LineBuffering
  [base] <- getArgs
  keyA <- expect "parse first package" (P.parseModuleInPackage "package:first" "/unchanged/Caller.hs"
    (source "Caller" "" "main = textFromChars (prettyCallStack callStack)"))
  keyB <- expect "parse second package" (P.parseModuleInPackage "package:second" "/unchanged/Caller.hs"
    (source "Caller" "" "main = textFromChars (prettyCallStack callStack)"))
  check "parsed package attribution changes query key with same crate and file" $
    B.unpack (Q.queryKey "fixed-crate" "compiler" (Modules.sourceValues keyA) [] []) /=
    B.unpack (Q.queryKey "fixed-crate" "compiler" (Modules.sourceValues keyB) [] [])
  putStrLn "BEGIN compile and roundtrip builtin"
  builtin <- expect "compile builtin" A.builtinPrelude >>= roundtrip
  let bp = B.literal (base ++ "/builtin.mlfi")
      pp = B.literal (base ++ "/provider.mlfi")
  let oldBuiltin (A.CrateInterface _ deps ms es reach ds cs instances lowered bindings entry objectHash protection) = A.CrateInterface "mlf:builtin-shared-haskell-v1:8" deps ms es reach ds cs instances lowered bindings entry objectHash protection
      stalePath = B.literal (base ++ "/stale-builtin8.mlfci")
  writeFile (B.unpack stalePath) (B.unpack (A.encodeInterface (oldBuiltin (A.objectInterface builtin))))
  staleLoaded <- A.loadInterfaces [stalePath]
  check "stale builtin8 dependency rejected by filesystem loader" (case staleLoaded of { T.Left message -> "stale or forged builtin crate identity" `isInfixOf` B.unpack message; T.Right _ -> False })
  -- All consumers use DECODED builtin metadata; no source facade is injected.
  let facadeCase name imports = B.literal ("module " ++ name ++ " where\n" ++ imports ++ "\nmain :: IO Int\nmain = do { x <- return (42 :: Int); if (\"same\" :: [Char]) == \"same\" then return x else return 0 }\n")
      checkFacade name mode imports deps = do
        obj <- compileText base name name mode (facadeCase name imports) deps
        check ("decoded Prelude Eq/IsString/Monad consumer " ++ name) (not (null (A.crateBindings (A.objectInterface obj))))
        pure obj
  _ <- checkFacade "ViaDefault" T.ImplicitPrelude "" [(bp,builtin)]
  _ <- checkFacade "ViaSelective" T.NoImplicitPrelude "import Prelude (IO, Int, Char, Monad, return, (>>=), Eq, (==), IsString, fromString)" [(bp,builtin)]
  _ <- checkFacade "ViaHiding" T.NoImplicitPrelude "import Prelude hiding (Monad, return, bind)\nimport MLF.Primitive (Monad, return, bind)" [(bp,builtin)]
  facade <- compileText base "Facade" "" T.NoImplicitPrelude "module Facade (module P) where\nimport Prelude as P\n" [(bp,builtin)]
  _ <- checkFacade "ViaReexport" T.NoImplicitPrelude "import Facade" [(bp,builtin),(B.literal (base ++ "/facade.mlfci"),facade)]
  putStrLn "BEGIN compile producer"
  provider <- compile base "Provider" "" " (who, Choice(Only), makeOther)"
    "who :: HasCallStack => [Char]\nwho = helper\nhelper :: HasCallStack => [Char]\nhelper = prettyCallStack callStack\ndata Choice = Only | Other\nmakeOther :: IO Choice\nmakeOther = pure Other" [(bp,builtin)]
  putStrLn "PASS producer compiled and metadata/object decoded"
  mapM_ (\((,) n ty) -> putStrLn ("EXPORT " ++ B.unpack n ++ " :: " ++ B.unpack (Pretty.prettyType ty))) (toList (A.crateBindings (A.objectInterface provider)))
  putStrLn "BEGIN infer consumer from decoded producer metadata"
  consumer <- compile base "Consumer" "Consumer" ""
    "import qualified Provider as P\nmain = textFromChars P.who" [(bp,builtin),(pp,provider)]
  (_,v) <- value [builtin,provider,consumer] consumer
  check "managed qualifier survives separate consumer inference" $ case v of
    R.RString text -> (base ++ "/Consumer.hs") `isInfixOf` B.unpack text && "who" `isInfixOf` B.unpack text
    _ -> False
  check "producer and consumer frames retain distinct truthful package identities" $ case v of
    R.RString text -> "in item4:Provider:Provider" `isInfixOf` B.unpack text &&
      "in item4:Consumer:Consumer" `isInfixOf` B.unpack text &&
      (base ++ "/Provider.hs") `isInfixOf` B.unpack text &&
      (base ++ "/Consumer.hs") `isInfixOf` B.unpack text
    _ -> False
  putStrLn "BEGIN unsigned helper copied into managed instance across artifacts"
  unsignedProvider <- compileText base "UnsignedProvider" "" T.NoImplicitPrelude
    "module UnsignedProvider (Capture(..)) where\nimport MLF.Primitive\nclass Capture a where { capture :: HasCallStack => a -> [Char] }\nunsigned = prettyCallStack callStack\ninstance Capture Int where { capture _ = unsigned }" [(bp,builtin)]
  unsignedConsumer <- compile base "UnsignedConsumer" "UnsignedConsumer" ""
    "import UnsignedProvider (Capture(..))\nmain = textFromChars (capture (42 :: Int))"
    [(bp,builtin),(B.literal (base ++ "/unsigned-provider.mlfci"),unsignedProvider)]
  (_,unsignedStack) <- value [builtin,unsignedProvider,unsignedConsumer] unsignedConsumer
  check "separate managed instance preserves unsigned source-helper empty stack" $ case unsignedStack of
    R.RString text -> null (B.unpack text)
    _ -> False
  putStrLn "BEGIN hidden-family separate consumer"
  hidden <- compile base "Hidden" "Hidden" ""
    "import Provider (Choice(Only), makeOther)\nmain = catchIOError (do { Only <- makeOther; pure 0 }) (\\_ -> pure 42)" [(bp,builtin),(pp,provider)]
  (env,action) <- value [builtin,provider,hidden] hidden
  outcome <- R.runAction [] env (T.Right action)
  check "hidden constructor retains refutable do failure through artifacts" $ case outcome of
    T.Right (T.Right (R.RInteger 42)) -> True
    _ -> False
  putStrLn "BEGIN custom Eq/IsString producer and consumer"
  literalProvider <- compile base "LiteralProvider" "" " (Key(..), key, glyphs)"
    "data Key = Key Int\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\ninstance IsString Key where { fromString _ = Key 7 }\nkey = Key 7\nglyphs :: [Char]\nglyphs = \"\\xD800\\&\\x10FFFF\"" [(bp,builtin)]
  let lp = B.literal (base ++ "/literal-provider.mlfi")
  literalConsumer <- compile base "LiteralConsumer" "LiteralConsumer" ""
    "import LiteralProvider (Key(..), key)\nmain = case (key,42) of { (\"a\",0) -> 0; (\"b\",x) -> x; _ -> 99 }"
    [(bp,builtin),(lp,literalProvider)]
  (_,literalValue) <- value [builtin,literalProvider,literalConsumer] literalConsumer
  check "custom Eq/IsString metadata preserves ordered string-pattern fallback" $ case literalValue of
    R.RInteger 42 -> True
    _ -> False
  putStrLn "BEGIN full Char string patterns against separate custom instances"
  surrogateConsumer <- compile base "SurrogateConsumer" "SurrogateConsumer" ""
    "import LiteralProvider (Key(..), key)\nmain = case (key,42) of { (\"\\xD800\",0) -> 0; (\"\\xDFFF\",x) -> x; _ -> 99 }"
    [(bp,builtin),(lp,literalProvider)]
  (_,surrogateValue) <- value [builtin,literalProvider,surrogateConsumer] surrogateConsumer
  check "full Char string-pattern payload preserves separate custom Eq ordered fallback" $ case surrogateValue of
    R.RInteger 42 -> True
    _ -> False
  putStrLn "BEGIN full Char literal producer object and metadata-only consumer"
  charsConsumer <- compile base "CharsConsumer" "CharsConsumer" ""
    "import LiteralProvider (glyphs)\nmain = case glyphs of { c : d : [] -> charCode c + charCode d; _ -> 0 }"
    [(bp,builtin),(lp,literalProvider)]
  (_,charsValue) <- value [builtin,literalProvider,charsConsumer] charsConsumer
  check "surrogate and maximum Char survive separate checked object roundtrip" $ case charsValue of
    R.RInteger 1169407 -> True
    _ -> False
