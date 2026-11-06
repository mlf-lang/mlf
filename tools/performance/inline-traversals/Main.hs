{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where

import Prelude
import Control.Exception (evaluate)
import Control.Monad (unless)
import System.Environment (getArgs)
import System.IO (withFile, IOMode(WriteMode), hSetEncoding, utf8, hPutStr)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.LLVM as Ordinary
import qualified Bootstrap.LLVM.Optimize as O
import qualified DiagnosticLLVM as Diagnostic
import qualified DiagnosticOptimize as D
import qualified Counters as C

right label value = case value of
  T.Left message -> fail (label ++ ": " ++ B.unpack message)
  T.Right result -> pure result

writeChunks path chunks = withFile path WriteMode $ \handle -> do
  hSetEncoding handle utf8
  mapM_ (hPutStr handle . B.unpack) chunks

-- These controls use actual production functions and deliberately undefined
-- zero-use terms/children. A counter that inspected them would fail the run.
controls = do
  let absent = T.XName 10 "absent"
      lazyTerm = error "zero-use pruning forced an absent subtree term"
      lazyValue = error "zero-use pruning forced a substitution value"
      ordinaryTree = O.UseTree lazyTerm M.empty (error "ordinary forced absent children")
      diagnosticTree = D.UseTree lazyTerm M.empty (error "diagnostic forced absent children")
      (ordinaryPruned, ordinarySeed) = O.runFresh (O.substituteUsed absent lazyValue ordinaryTree) 17
  unless (M.null (O.useCounts ordinaryPruned) && ordinarySeed == 17) (fail "ordinary zero-use substitution")
  case O.commonCalls absent 1 M.empty ordinaryTree of
    O.NoCommonCalls -> pure ()
    _ -> fail "ordinary zero-use calls"
  C.reset
  let (diagnosticPruned, diagnosticSeed) = D.runFresh (D.substituteUsed absent lazyValue diagnosticTree) 17
  unless (M.null (D.useCounts diagnosticPruned) && diagnosticSeed == 17) (fail "diagnostic zero-use substitution")
  substitute <- C.snapshot
  _ <- evaluate (length substitute)
  C.reset
  case D.commonCalls absent 1 M.empty diagnosticTree of
    D.NoCommonCalls -> pure ()
    _ -> fail "diagnostic zero-use calls"
  common <- C.snapshot
  _ <- evaluate (length common)
  let target = T.XName 20 "target"
      filler = T.XName 21 "filler"
      argument = T.XName 22 "argument"
      parameter = T.XName 23 "parameter"
      positiveInput = T.XEApp (T.XEVar filler)
                        (T.XEApp (T.XEVar target) (T.XEVar argument))
      ordinaryPositive = O.indexUses positiveInput
      diagnosticPositive = D.indexUses positiveInput
      outerCounts = M.singleton argument 1
      replacement = T.XEAbs parameter (T.XEVar parameter)
  -- Finish fixture construction before counting either target traversal.
  unless (X.equalErased positiveInput (D.useTerm diagnosticPositive)) (fail "positive fixture construction")
  case O.commonCalls target 1 outerCounts ordinaryPositive of
    O.CommonCalls names -> unless (O.sameCallNames names [argument]) (fail "ordinary positive common calls")
    _ -> fail "ordinary positive common calls result"
  C.reset
  case D.commonCalls target 1 outerCounts diagnosticPositive of
    D.CommonCalls names -> unless (O.sameCallNames names [argument]) (fail "diagnostic positive common calls")
    _ -> fail "diagnostic positive common calls result"
  positiveCommon <- C.snapshot
  _ <- evaluate (length positiveCommon)
  let (ordinarySubstitution, ordinarySubstitutionSeed) =
        O.runFresh (O.substituteUsed target replacement ordinaryPositive) 200
  C.reset
  let (diagnosticSubstitution, diagnosticSubstitutionSeed) =
        D.runFresh (D.substituteUsed target replacement diagnosticPositive) 200
  unless (X.equalErased (O.useTerm ordinarySubstitution) (D.useTerm diagnosticSubstitution) &&
          ordinarySubstitutionSeed == diagnosticSubstitutionSeed && diagnosticSubstitutionSeed == 201)
    (fail "positive substitution exact structure/fresh seed differs")
  positiveSubstitute <- C.snapshot
  _ <- evaluate (length positiveSubstitute)
  let outer = T.XName 1 "outer"
      alias = T.XName 2 "alias"
      binder = T.XName 3 "binder"
      input = T.XELet alias (T.XEVar outer)
                (T.XEAbs binder (T.XEApp (T.XEVar alias) (T.XEVar binder)))
      (ordinaryAlias, ordinaryAfter) = O.runFresh (O.identities input) 100
  C.reset
  let (diagnosticAlias, diagnosticAfter) = D.runFresh (D.identities input) 100
  unless (X.equalErased ordinaryAlias diagnosticAlias && ordinaryAfter == diagnosticAfter && diagnosticAfter == 101)
    (fail "alias control exact structure/fresh seed differs")
  aliasCounts <- C.snapshot
  _ <- evaluate (length aliasCounts)
  putStrLn ("{\"complete\":true,\"zero_substitute\":" ++ substitute ++
            ",\"zero_common\":" ++ common ++ ",\"positive_common\":" ++ positiveCommon ++
            ",\"positive_substitute\":" ++ positiveSubstitute ++ ",\"alias\":" ++ aliasCounts ++ "}")

main = do
  args <- getArgs
  case args of
    ["--controls"] -> controls
    [path, output] -> do
      checked <- Artifact.linkCheckedFile (B.literal path) >>= right "link checked crate"
      ordinary <- right "ordinary checked LLVM emission" (Ordinary.emitCheckedChunks True checked)
      writeChunks (output ++ "/ordinary.ll") ordinary
      C.reset
      diagnostic <- right "diagnostic checked LLVM emission" (Diagnostic.emitCheckedChunks True checked)
      -- Closing the UTF-8 output handle fully consumes all final output bytes.
      -- Snapshot is sequenced afterwards; there is no AST size/forcing pass.
      writeChunks (output ++ "/diagnostic.ll") diagnostic
      counters <- C.snapshot
      putStrLn ("{\"complete\":true,\"counters\":" ++ counters ++ "}")
    _ -> fail "usage: inline-traversals CHECKED.mlfci OUTPUT_DIRECTORY | --controls"
