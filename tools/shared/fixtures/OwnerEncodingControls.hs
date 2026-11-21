{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (forM_, unless)
import Data.Char (chr, ord, isAscii, isAlphaNum)
import Data.List (sort, stripPrefix, nub)
import qualified Data.Set as Set
import Numeric (showHex)
import qualified MLF.Host.Base as B
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as S
import qualified Bootstrap.Module as M

need label ok = unless ok (fail label)
frame = concatMap (\s -> show (length s) ++ ":" ++ s)
decimal = concatMap (\c -> show (ord c) ++ "_")
compact = concatMap (\c -> if isAscii c && isAlphaNum c && c /= 'z' then [c]
                         else if c == 'z' then "zz" else "z" ++ showHex (ord c) "z")
reference version crate prefixes names = frame [version, crate, frame (map member (sort names))]
  where
    member name = case [(tag, suffix) | (tag, prefix) <- prefixes,
                                      Just suffix <- [stripPrefix prefix name]] of
      [(tag, suffix)] -> frame [tag, suffix]
      _ -> frame ["raw", name]
reference2 crate = reference "MLF-OPEN-GROUP-2" crate
  [("value", "module_" ++ decimal crate ++ "z_"), ("type", "Module_" ++ decimal crate ++ "z_")]
reference3 crate = reference "MLF-OPEN-GROUP-3" crate
  [("value", "module_c1_" ++ compact crate ++ "_"), ("type", "Module_c1_" ++ compact crate ++ "_")]

main = do
  let alphabet = map chr ([0..127] ++ [128,255,256,2047,2048,55295,57344,65535,65536,1114111])
      texts = "" : map (:[]) alphabet ++ [[a,b] | a <- alphabet, b <- alphabet] ++
              ["z0z", "z3az", "zz", "a_b", "a:z/b", replicate 65536 'a', replicate 2048 '\x1f600'] ++
              [replicate n 'a' ++ "z/λ😀" ++ replicate n 'b' | n <- [255,256,257]]
      encode s = B.unpack (S.compactName (B.literal s))
  forM_ texts $ \value -> do
    let result = encode value
    need "independent scalar component encoding" (result == compact value)
    need "component alphabet excludes separators" (all (\c -> isAscii c && isAlphaNum c) result)
    need "component rendering bound" (length result <= 8 * length value)
  need "component injectivity on adversarial corpus"
    (Set.size (Set.fromList (map encode texts)) == Set.size (Set.fromList texts))
  need "crate/entity boundaries remain distinct"
    (length (nub [encode a ++ "_" ++ encode b | (a,b) <- [("ab","c"),("a","bc"),("a_","b"),("a","_b"),("","a_b")]]) == 5)
  let roles = [(M.Value,"value","",False), (M.Datatype,"data","",True),
               (M.Class,"class","",True), (M.Constructor "Pair","constructor","Pair",True),
               (M.Method "Tag","method","Tag",False),
               (M.ManagedConstraint,"managed-constraint","",True)]
  forM_ ["", "crate", "crate/λ", "9:a\NUL😀", "otherz_"] $ \crate -> do
    forM_ ["Main", "A.B", "模块", "z_", ""] $ \owner ->
      forM_ ["x", "f0", "+", "λ", "z3az", "", "a_b"] $ \spelling ->
        forM_ roles $ \(role,tag,parent,upper) -> do
          let entity = M.Entity (B.literal owner) (B.literal spelling) role
              expected = (if upper then "Module_c1_" else "module_c1_") ++ compact crate ++ "_" ++
                         compact (frame [owner,spelling,tag,parent])
          need "complete crate/module/name/role/parent identity"
            (B.unpack (A.definitionName (B.literal crate) entity) == expected)
    let value = "module_c1_" ++ compact crate ++ "_"
        ty = "Module_c1_" ++ compact crate ++ "_"
        legacy = "module_" ++ decimal crate ++ "z_97_"
        names = [value ++ "a", ty ++ "T", "raw:λ", "module_c1_other_a", value ++ "b", legacy]
        c = B.literal crate
        encoded xs = S.compactOpenGroupName c (map B.literal xs)
        matches xs owner = A.openGroupOwnerMatches c (map B.literal (sort xs)) owner
    forM_ [[], take 1 names, take 2 names, names, reverse names, ["ab", "c"], ["a", "bc"]] $ \xs -> do
      let owner = encoded xs
      need "independent canonical owner bytes" (B.unpack owner == reference3 crate xs)
      need "exact compact owner admission" (matches xs owner == not (null xs))
      need "v2 bytes remain independently specified"
        (B.unpack (S.compactOpenGroupNameV2 c (map B.literal xs)) == reference2 crate xs)
      if null xs then pure () else do
        need "v2 owner still admitted" (matches xs (B.literal (reference2 crate xs)))
        need "existing framed owner still admitted" (matches xs (S.openGroupName c (map B.literal xs)))
        need "legacy owner still admitted" (matches xs (S.queryGroupName c (map B.literal (sort xs))))
        need "trailing owner bytes rejected" (not (matches xs (B.literal (B.unpack owner ++ "x"))))
        need "wrong crate rejected" (not (A.openGroupOwnerMatches "different crate" (map B.literal (sort xs)) owner))
        need "changed complete inventory rejected" (not (matches (xs ++ ["extra"]) owner))
    need "sorting is before factoring" (encoded names `same` encoded (reverse names))
    need "framed inventories are injective" (not (encoded ["ab", "c"] `same` encoded ["a", "bc"]))
    need "duplicate member remains represented" (not (encoded names `same` encoded ((value ++ "a"):names)))
    let canonical = reference3 crate names
        malformed = [frame ["MLF-OPEN-GROUP-3", crate, frame [frame ["raw", value ++ "a"]]],
                     frame ["MLF-OPEN-GROUP-3", crate, frame [frame ["value", "a"], frame ["value", "a"]]],
                     frame ["MLF-OPEN-GROUP-3", crate, frame [frame ["unknown", "a"]]],
                     frame ["MLF-OPEN-GROUP-3", crate, frame [frame ["type", "a"]]]]
    need "mutation inventory is distinct" (length (nub malformed) == length malformed)
    forM_ malformed $ \owner -> need "noncanonical or changed owner rejected"
      (owner /= canonical && not (matches [value ++ "a"] (B.literal owner)))
  need "managed builtin identity" (B.unpack (A.definitionName "crate" (M.Entity "MLF.Primitive" "callStack" M.Value)) == "mlfCallStack")
  need "builtin type identity" (B.unpack (A.definitionName "crate" (M.Entity "Prelude" "Int" M.BuiltinType)) == "Int")
  putStrLn "PASS compact declaration components, full identities, v3/v2 owners, Unicode, bounds and mutations"
  where same a b = B.unpack a == B.unpack b
