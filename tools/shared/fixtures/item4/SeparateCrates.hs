{-# LANGUAGE OverloadedStrings #-}
-- Separate producer/consumer inference uses decoded metadata, never producer source.
module Main where
import Prelude
import Data.List (isInfixOf)
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
list = foldr T.Cons T.Nil
toList T.Nil = []
toList (T.Cons x xs) = x : toList xs
expect label value = case value of
  T.Left e -> error (label ++ ": " ++ B.unpack e)
  T.Right x -> pure x
check label ok = if ok then putStrLn ("PASS " ++ label) else error label
source name exports body = B.literal $ "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule " ++ name ++ exports ++ " where\nimport MLF.Primitive\n" ++ body ++ "\n"
roundtrip obj = do
  iface <- expect "decode interface" (A.decodeInterface (A.encodeInterface (A.objectInterface obj)))
  expect "decode pooled object" (A.decodeObject iface (A.encodeObject obj))
compile base name entry exports body deps = do
  let path = B.literal (base ++ "/" ++ name ++ ".hs")
      spec = C.CrateSpec (B.literal ("item4:" ++ name)) (B.literal entry) T.NoImplicitPrelude
        (list [T.Pair (B.literal name) path]) (list [p | (p,_) <- deps])
        (B.literal (base ++ "/cache-" ++ name)) (B.literal (base ++ "/builtin"))
      interfaces = list [T.Pair p (A.objectInterface o) | (p,o) <- deps]
  writeFile (B.unpack path) (B.unpack (source name exports body))
  parsed <- C.loadSourcesInPackage (C.specIdentity spec) (C.specSources spec) >>= expect "load own source with crate package identity"
  prepared <- expect "prepare against metadata" (C.prepareCrate spec interfaces parsed)
  T.Pair obj _ <- C.compilePrepared spec interfaces prepared >>= expect "compile separate crate"
  roundtrip obj
value objects root = do
  term <- expect "link decoded objects" (A.linkObjects (list objects) (A.crateId (A.objectInterface root)))
  T.Pair env _ <- expect "prepare runtime" (R.prepare False term)
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
    B.unpack (Q.queryKey "fixed-crate" "compiler" (Modules.sourceValues keyA) T.Nil T.Nil) /=
    B.unpack (Q.queryKey "fixed-crate" "compiler" (Modules.sourceValues keyB) T.Nil T.Nil)
  putStrLn "BEGIN compile and roundtrip builtin"
  builtin <- expect "compile builtin" A.builtinPrelude >>= roundtrip
  let bp = B.literal (base ++ "/builtin.mlfi")
      pp = B.literal (base ++ "/provider.mlfi")
  putStrLn "BEGIN compile producer"
  provider <- compile base "Provider" "" " (who, Choice(Only), makeOther)"
    "who :: HasCallStack => [Char]\nwho = helper\nhelper :: HasCallStack => [Char]\nhelper = prettyCallStack callStack\ndata Choice = Only | Other\nmakeOther :: IO Choice\nmakeOther = pure Other" [(bp,builtin)]
  putStrLn "PASS producer compiled and metadata/object decoded"
  mapM_ (\(T.Pair n ty) -> putStrLn ("EXPORT " ++ B.unpack n ++ " :: " ++ B.unpack (Pretty.prettyType ty))) (toList (A.crateBindings (A.objectInterface provider)))
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
  putStrLn "BEGIN hidden-family separate consumer"
  hidden <- compile base "Hidden" "Hidden" ""
    "import Provider (Choice(Only), makeOther)\nmain = catchIOError (do { Only <- makeOther; pure 0 }) (\\_ -> pure 42)" [(bp,builtin),(pp,provider)]
  (env,action) <- value [builtin,provider,hidden] hidden
  outcome <- R.runAction T.Nil env (T.Right action)
  check "hidden constructor retains refutable do failure through artifacts" $ case outcome of
    T.Right (T.Right (R.RInteger 42)) -> True
    _ -> False
  putStrLn "BEGIN custom Eq/IsString producer and consumer"
  literalProvider <- compile base "LiteralProvider" "" " (Key(..), key)"
    "data Key = Key Int\ninstance Eq Key where { (==) (Key a) (Key b) = a == b }\ninstance IsString Key where { fromString _ = Key 7 }\nkey = Key 7" [(bp,builtin)]
  let lp = B.literal (base ++ "/literal-provider.mlfi")
  literalConsumer <- compile base "LiteralConsumer" "LiteralConsumer" ""
    "import LiteralProvider (Key(..), key)\nmain = case (key,42) of { (\"a\",0) -> 0; (\"b\",x) -> x; _ -> 99 }"
    [(bp,builtin),(lp,literalProvider)]
  (_,literalValue) <- value [builtin,literalProvider,literalConsumer] literalConsumer
  check "custom Eq/IsString metadata preserves ordered string-pattern fallback" $ case literalValue of
    R.RInteger 42 -> True
    _ -> False
