{-# LANGUAGE OverloadedStrings #-}
module OptimizationCrates (run) where

import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless)
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.ImportedRoot as Imports
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Host.Base as H

need :: String -> Bool -> IO ()
need label ok = unless ok (fail label)

-- Independent scalar framing: ordinary Haskell strings and no production
-- packing or builder helpers. Include every source constructor, kind and flag.
pack :: [String] -> String
pack = concatMap (\value -> show (length value) ++ ":" ++ value)

node :: String -> [String] -> String
node tag fields = pack (tag : fields)

kind :: T.Kind -> String
kind T.Star = node "star" []
kind (T.KArrow a b) = node "kind-arrow" [kind a, kind b]

source :: T.SType -> String
source ty = case ty of
  T.STVar name -> node "variable" [H.unpack name]
  T.SBottom -> node "bottom" []
  T.SBottomKind k -> node "bottom-kind" [kind k]
  T.SArrow a b -> node "arrow" [source a, source b]
  T.SCon name args -> node "constructor" [H.unpack name, pack (map source args)]
  T.STypeApp f a -> node "application" [source f, source a]
  T.SForall flag name bound body -> node "forall"
    [case flag of { T.Flexible -> "flexible"; T.Rigid -> "rigid" },
     H.unpack name, source bound, source body]
  T.SQualified predicates body -> node "qualified" [pack (map predicate predicates), source body]

predicate :: T.SPredicate -> String
predicate (T.SPredicate name args) = node "predicate" [H.unpack name, pack (map source args)]

encodingChecks :: IO ()
encodingChecks = do
  let names = ["", "a", "λ😀\NUL:12", "type:0"]
      ks = [T.Star, T.KArrow T.Star T.Star,
            foldr T.KArrow T.Star (replicate 96 (T.KArrow T.Star T.Star))]
      leaves = [T.SBottom] ++ map T.STVar names ++ map T.SBottomKind ks
      layer t = [T.SArrow t t, T.STypeApp (T.STVar "f") t,
                 T.SCon "C😀\NUL" [t, T.SCon "Int" []],
                 T.SForall T.Flexible "λ😀" T.SBottom t,
                 T.SForall T.Rigid "b" t (T.STVar "b"),
                 T.SQualified [T.SPredicate "Eqλ" [t], T.SPredicate "C" []] t]
      samples = leaves ++ concatMap layer leaves ++
        [foldr T.SArrow T.SBottom (replicate 192 (T.STVar "λ😀")),
         iterate (T.SForall T.Rigid "q" (T.SBottomKind (T.KArrow T.Star T.Star))) T.SBottom !! 192,
         iterate (\t -> T.SQualified [T.SPredicate "C" [t]] (T.STVar "a")) T.SBottom !! 96]
  forM_ ks $ \k -> need "kind scalar framing changed" (kind k == H.unpack (Q.encodeKind k))
  forM_ ks $ \k -> need "target bottom-kind scalar framing changed"
    (node "bottom-kind" [kind k] == H.unpack (Q.encodeXType (T.XBotKind k)))
  forM_ samples $ \ty -> do
    need "source type framing changed" (source ty == H.unpack (Q.encodeType ty))
    let p = T.SPredicate "Constraint😀" [ty, T.STVar "λ"]
    need "predicate framing changed" (predicate p == H.unpack (Q.encodePredicate p))
    need "annotation framing changed"
      (node "annotation" [pack ["λ", "😀"], source ty] ==
       H.unpack (Q.encodeAnnotation (T.SAnnotation ["λ", "😀"] ty)))

-- Each legacy encoder forces a field's text before inspecting the next
-- field's syntax. A chunk builder must retain that first diagnostic too.
encodingFailureChecks :: IO ()
encodingFailureChecks = do
  let first label wanted encoded = do
        result <- try (evaluate (H.v_stringLength encoded)) :: IO (Either H.HostError H.Int)
        case result of
          Left (H.HostError actual) -> need label (actual == wanted)
          Right _ -> fail (label ++ ": expected a framing failure")
      text = H.v_panic "first text"
      later = H.v_panic "later syntax"
  first "source arrow forces its left payload first" "first text"
    (Q.encodeType (T.SArrow (T.STVar text) later))
  first "source application forces its function payload first" "first text"
    (Q.encodeType (T.STypeApp (T.STVar text) later))
  first "source constructor forces its name before its arguments" "first text"
    (Q.encodeType (T.SCon text [later]))
  first "source quantifier forces its flag before its body" "first flag"
    (Q.encodeType (T.SForall (H.v_panic "first flag") "q" T.SBottom later))
  first "source quantifier forces its name before its bound" "first text"
    (Q.encodeType (T.SForall T.Flexible text later T.SBottom))
  first "source predicate forces its class before its arguments" "first text"
    (Q.encodePredicate (T.SPredicate text [later]))
  first "qualified type forces predicates before its body" "first text"
    (Q.encodeType (T.SQualified [T.SPredicate text [T.SBottom]] later))
  first "kind encoding retains left-to-right diagnostics" "first kind"
    (Q.encodeKind (T.KArrow (T.KArrow T.Star (H.v_panic "first kind")) (H.v_panic "later kind")))

-- Exercise the normal imported-root route with its authenticated schema. The
-- ordinary graph path is an independent reference for compact evidence-only
-- embedding, including fallback for noncanonical first occurrences.
importChecks :: IO ()
importChecks = forM_ [1, 2, 7, 24] $ \count -> do
  let vars = [T.XTyVar (fromIntegral (97 + i * 11)) | i <- [0 .. count-1]]
      names = [H.literal ("a" ++ show i) | i <- [0 .. 2*count-1]]
      slots = V.fromInt 37
      declarations = [T.DataDecl "Dictionary" names [T.ConstructorDecl "DictionaryValue" []]]
      concrete = T.SCon "Dictionary" (replicate (2*count) (T.SCon "Int" []))
      rhs = T.SAnn (T.SWantedRefs "Dictionary" [(T.InstanceEvidence, T.DeclRef slots "instance")])
        (T.SAnnotation [] concrete)
      variants = [vars ++ vars, concatMap (replicate 2) vars,
                  reverse vars ++ vars, replicate (2*count) (head vars)]
      checked value = case value of
        T.Left message -> fail (H.unpack message)
        T.Right result -> pure result
      observation value = case value of
        T.Left message -> Left (H.unpack message)
        T.Right (_, parameters, term) -> Right
          (map (H.unpack . Pretty.prettyType . snd) parameters, H.unpack (Pretty.prettyTerm term))
  env <- checked (Open.environment declarations)
  forM_ (zip [0 :: Int ..] variants) $ \(variant, occurrences) -> do
    let scheme = foldr (\v body -> T.XForall v T.XBot body)
          (T.XCon "Dictionary" (map T.XVar occurrences)) vars
        parameters = [(slots, "instance", scheme)]
        members = [(V.fromInt 101, ("entry", T.Nothing, rhs))]
    (_, lowered) <- checked (Inference.prepareIndexedGroup parameters declarations members)
    selected <- checked (Imports.fileImports parameters lowered)
    let ordinary = Imports.finishFileImports selected lowered
        compact = Imports.finishFileImportsIn (T.Just env) selected lowered
    need "evidence-only import changed checked term, identities or diagnostic"
      (observation ordinary == observation compact)
    -- Reordered or unused quantifiers can legitimately be rejected by the
    -- ordinary graph route. Its exact diagnostic is part of this comparison.
    if variant < 2 then checked ordinary >> pure () else pure ()

run :: IO ()
run = encodingChecks >> encodingFailureChecks >> importChecks
