{-# LANGUAGE OverloadedStrings #-}
module Main where

import qualified Prelude as P
import Prelude (($), (.), (++), (==), (/=), (<), (>), (+), (-), (*), (<$>), (>>=))
import Control.Exception (evaluate, try, SomeException)
import Control.Monad (forM_, unless)
import qualified MLF.Primitive as B
import Bootstrap.Types
import qualified Bootstrap.Std as S
import qualified Bootstrap.Module as M
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.Separate as Sep

assert name ok = unless ok (P.error name)
right value = case value of Left e -> P.error "unexpected Left in metadata control"; Right x -> P.pure x
same a b = case (a,b) of
  (W.VInt x,W.VInt y) -> x == y
  (W.VBits x,W.VBits y) -> x == y
  (W.VText x,W.VText y) -> B.eqString x y
  (W.VNode x xs,W.VNode y ys) -> x == y P.&& sameList xs ys
  _ -> P.False
sameList [] [] = P.True
sameList (a:as) (b:bs) = same a b P.&& sameList as bs
sameList _ _ = P.False
wireValue = A.toCrateInterfaceFields
types = [XBot, XBotKind Star, XBotKind (KArrow Star Star), XVar (XTyVar (-1)),
  XVar (XTyVar 7), XArrow XBot (XVar (XTyVar 7)), XCon "Int" [],
  XCon "Box" [XVar (XTyVar 7)], XApply (XCon "Box" []) XBot,
  XForall (XTyVar 7) XBot (XArrow (XVar (XTyVar 7)) (XVar (XTyVar 7))),
  XForall (XTyVar 8) XBot (XArrow (XVar (XTyVar 8)) (XVar (XTyVar 8)))]
sourceTypes = [STVar "a",SBottom,SBottomKind Star,SBottomKind (KArrow Star Star),
  SArrow (STVar "a") (SCon "Int" []),SCon "Box" [STVar "a"],
  STypeApp (SCon "Box" []) (STVar "a"),
  SForall Flexible "a" SBottom (STVar "a"),
  SForall Rigid "a" SBottom (STVar "a"),
  SQualified [SPredicate "Eq" [STVar "a"]] (STVar "a")]
roles = [M.Value,M.Datatype,M.Class,M.Constructor "Box",M.Method "Eq",
  M.BuiltinType,M.Primitive PAddInt,M.Primitive PPanic,M.Boolean B.False,
  M.Boolean B.True,M.ManagedConstraint]
decls = [DataDecl "Tree" ["a"] [ConstructorDecl "Leaf" [Parameter "a"]],
  DataDeclK "Box" [("a",Star)] [ConstructorDecl "Box" [
    Function (Parameter "a") (Applied "Int" []),
    Application (Applied "Box" []) (Parameter "a"),
    Quantified "b" (KArrow Star Star) (Applied "T" [Parameter "b"])]]]
klass = SClassDecl "C" [("a",Star),("f",KArrow Star Star)]
  [SPredicate "Eq" [STVar "a"]] [("method",t) | t <- sourceTypes]
instanceWith expression = SInstanceDecl [("a",Star)] [SPredicate "C" [STVar "a"]]
  "C" sourceTypes [("first",expression),("second",SVar "other")]
base = A.CrateInterfaceFields "crate" [("dep","wire-hash","semantic-hash")]
  ["One","Two"] [("Exports",[M.Entity "Owner" "name" role | role <- roles])]
  [("Reach",["First","Second"])] decls [klass] [("Owner",instanceWith (SIntLit 1))]
  (P.reverse decls) [("binding",t) | t <- types] "entry" "open-object" [("hidden",B.True),("public",B.False)]
withInstances instances (A.CrateInterfaceFields a b c d e f g _ i j k l m) =
  A.CrateInterfaceFields a b c d e f g instances i j k l m
withBindings bindings (A.CrateInterfaceFields a b c d e f g h i _ k l m) =
  A.CrateInterfaceFields a b c d e f g h i bindings k l m
-- Mutate the generic wire model, then independently decode admitted cases.
-- This reaches every scalar and nested field without reproducing the typed
-- comparator's dispatch, and retains order and duplicate-list counterexamples.
mutations v = local ++ case v of
  W.VNode tag fields -> [W.VNode tag (P.take i fields ++ [x] ++ P.drop (i+1) fields)
    | (i,field) <- P.zip [0..] fields, x <- mutations field]
  _ -> []
  where local = case v of
          W.VInt n -> [W.VInt (n+1),W.VInt (-9223372036854775808),W.VInt 9223372036854775807]
          W.VText _ -> [W.VText "",W.VText "changed-\x3bb"]
          W.VBits n -> [W.VBits (n+1)]
          W.VNode 1 fields -> [W.VNode 1 [],W.VNode 1 (P.reverse fields),W.VNode 1 (fields ++ fields)]
          W.VNode 6 [] -> [W.VNode 7 []]
          W.VNode 7 [] -> [W.VNode 6 []]
          W.VNode 10 [] -> [W.VNode 11 [W.VNode 10 [],W.VNode 10 []]]
          W.VNode 41 [] -> [W.VNode 42 [W.VNode 10 []]]
          W.VNode 42 [_] -> [W.VNode 41 []]
          W.VNode 12 [] -> [W.VNode 13 []]
          W.VNode 13 [] -> [W.VNode 12 []]
          _ -> []
admitted = [x | value <- mutations (wireValue base),Right x <- [A.fromCrateInterfaceFields value]]
cachedMatches fields package expected digest = case O.cachedMetadata fields package of
  Nothing -> assert "unexpected metadata cache miss" (P.not expected)
  Just actual -> assert "unexpected metadata cache hit" (expected P.&& B.eqString actual digest)
packageFor fields = do
  receipt <- O.makeMetadataReceipt fields >>= right
  let digest = O.metadataReceiptHash receipt
  package <- O.makePackage "fixture" (Sep.pack [digest]) [] >>= right
  retained <- right (O.withMetadataReceipt receipt package)
  P.pure (receipt,package,retained,digest)
withName name (A.CrateInterfaceFields _ b c d e f g h i j k l m) =
  A.CrateInterfaceFields name b c d e f g h i j k l m
withEntry entry (A.CrateInterfaceFields a b c d e f g h i j _ l m) =
  A.CrateInterfaceFields a b c d e f g h i j entry l m
main = do
  let cases = base : admitted
  forM_ (P.zip [0 :: P.Int ..] cases) $ \(i,fields) -> do
    let (value,_,_,_) = A.crateMetadataParts fields
    assert ("projection parity " ++ P.show i) (same (wireValue fields) value)
    (_,_,retained,digest) <- packageFor fields
    expectedDigest <- Q.hashValue (wireValue fields) >>= right
    assert ("digest parity " ++ P.show i) (B.eqString digest expectedDigest)
    forM_ [base,cases P.!! (i `P.mod` P.length cases),cases P.!! ((i+19) `P.mod` P.length cases)] $ \other ->
      cachedMatches other retained (same (wireValue fields) (wireValue other)) digest
  let ignored = withInstances [("Owner",instanceWith (P.error "excluded method body forced"))] base
  assert "method bodies excluded" (same (wireValue base) (wireValue ignored))
  (receipt,package,retained,digest) <- packageFor ignored
  cachedMatches base retained P.True digest
  case O.cachedMetadata (P.error "absent receipt forced metadata") package of
    Nothing -> P.pure (); _ -> P.error "unexpected receipt"
  cachedMatches (withBindings [("different",P.error "type forced after name mismatch")] base) retained P.False digest
  cachedMatches (withName "different" (withBindings (P.error "bindings forced after prefix mismatch") base)) retained P.False digest
  after <- try (evaluate (case O.cachedMetadata
    (withEntry "different" (withBindings [("binding",P.error "binding-before-suffix")] base)) retained of
      Nothing -> P.False; Just _ -> P.True)) :: P.IO (P.Either SomeException P.Bool)
  case after of P.Left _ -> P.pure (); P.Right _ -> P.error "suffix mismatch bypassed binding demand"
  let bound7=withBindings [("x",types P.!! 9)] base
      bound8=withBindings [("x",types P.!! 10)] base
  (_,_,seven,d7) <- packageFor bound7
  cachedMatches bound8 seven P.False d7
  let bottom=withBindings [("x",XBot)] base
      kindBottom=withBindings [("x",XBotKind Star)] base
  (_,_,bot,db) <- packageFor bottom
  cachedMatches kindBottom bot P.False db
  forM_ cases $ \fields -> cachedMatches fields retained (same (wireValue base) (wireValue fields)) digest
  wrong <- O.makePackage "fixture" (Sep.pack ["different"]) [] >>= right
  case O.withMetadataReceipt receipt wrong of Left _ -> P.pure (); _ -> P.error "wrong manifest admitted"
  let deep = P.iterate (XArrow XBot) XBot P.!! (P.fromIntegral (W.maxDepth W.defaultLimits) + 1)
      bad = withBindings [("deep",deep)] base
  oldBad <- Q.encodeHashed (wireValue bad)
  newBad <- O.makeMetadataReceipt bad
  case (oldBad,newBad) of
    (Left x,Left y) -> assert "finite limit diagnostic parity" (B.eqString x y)
    _ -> P.error "depth admission mismatch"
  P.putStrLn ("PASS metadata cases=" ++ P.show (P.length cases) ++
    "; 4 receipt comparisons/case; canonical projection/digest; exact IDs/tags; excluded-body demand; prefix/binding/suffix demand; absent-receipt demand; manifest rejection; finite limits")
