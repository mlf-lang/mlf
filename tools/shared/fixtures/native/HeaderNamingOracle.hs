{-# LANGUAGE OverloadedStrings #-}
module HeaderNamingOracle (currentName, encoded, controls, historicalControls) where
import Prelude
import Control.Monad (unless, forM_)
import Data.Char (ord, isAscii, isAlphaNum)
import Data.List (nub)
import Numeric (showHex)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Module as M
import qualified Bootstrap.Data as D
import qualified Bootstrap.Primitive as Primitive
import qualified HistoricalHeaderNames as H
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as S
import qualified MLF.Primitive as P

-- Expected encoding/framing is independent of all production name formatters.
-- Role primitive labels and the canonical constructor inventory are shared
-- semantic metadata, not independently qualified historical metadata.
chars = P.textToChars
text = P.textFromChars
compact = concatMap (\c -> if isAscii c && isAlphaNum c && c /= 'z' then [c]
                         else if c == 'z' then "zz" else "z" ++ showHex (ord c) "z")
decimal = concatMap (\c -> show (ord c) ++ "_")
frame = concatMap (\s -> show (length s) ++ ":" ++ s)
encoded = text . compact . chars

roleFields role = case role of
 M.Value -> ("value","")
 M.Datatype -> ("data","")
 M.Class -> ("class","")
 M.ManagedConstraint -> ("managed-constraint","")
 M.Constructor parent -> ("constructor",chars parent)
 M.Method parent -> ("method",chars parent)
 M.BuiltinType -> ("builtin","")
 M.Primitive p -> ("primitive",chars (Primitive.primitiveName p))
 M.Boolean b -> ("bool",if b then "true" else "false")
upper role = case role of
 M.Datatype -> True
 M.Class -> True
 M.ManagedConstraint -> True
 M.Constructor _ -> True
 M.BuiltinType -> True
 _ -> False
builtin role = case role of { M.BuiltinType -> True; _ -> False }
canonical owner spelling role = owner == "Prelude" && case role of
 M.Constructor parent -> any (\d -> chars (D.datatypeName d) == chars parent &&
                      any (\c -> chars (D.constructorName c) == spelling)
                          (D.datatypeConstructors d)) D.sourceBuiltinDeclarations
 _ -> False
managed owner spelling role = if owner /= "MLF.Primitive" then Nothing else case role of
 M.ManagedConstraint | spelling == "HasCallStack" -> Just "MLFHasCallStack"
 M.BuiltinType | spelling == "CallStack" -> Just "MLFCallStack"
 M.Value | spelling == "callStack" -> Just "mlfCallStack"
 _ -> Nothing
currentName = nameWith compact "Module_c1_" "module_c1_" "_"
historicalName = nameWith decimal "Module_" "module_" "z_"
nameWith codec typePrefix valuePrefix separator identity (M.Entity ownerText spellingText role) = text result
 where
 owner = chars ownerText
 spelling = chars spellingText
 (tag,arg) = roleFields role
 result = case managed owner spelling role of
  Just name -> name
  Nothing -> if owner == "Prelude" || builtin role
   then if builtin role || canonical owner spelling role then spelling
        else (if upper role then "Module_" else "module_") ++ decimal owner ++ "z_" ++ decimal spelling
   else (if upper role then typePrefix else valuePrefix) ++ codec (chars identity) ++ separator ++
        codec (frame [owner,spelling,tag,arg])

need label yes = unless yes (error label)
exact expected actual = expected == chars actual
controls :: IO ()
controls = do
 let goldens = [("",""),("Az09","Azz09"),("z","zz"),("_","z5fz"),("\0","z0z"),
                ("é","ze9z"),("😀","z1f600z"),("z0z","zz0zz"),(":","z3az")]
 forM_ goldens $ \(input,want) -> do
  need "independent compact golden" (compact input == want)
  need "production compact golden" (exact want (S.compactName (text input)))
 let ordinary = M.Entity "U" "x" M.Value
     golden = "module_c1__1z3azU1z3azx5z3azvalue0z3az"
 need "literal complete ordinary golden" (exact golden (currentName "" ordinary))
 need "actual complete ordinary golden" (exact golden (A.definitionName "" ordinary))
 let wrong = ["module__1z3azU1z3azx5z3azvalue0z3az",
              "module_c1_1z3azU1z3azx5z3azvalue0z3az",
              "module_c1__1z3AU1z3azx5z3azvalue0z3az",
              "Module_c1__1z3azU1z3azx5z3azvalue0z3az"]
 forM_ wrong $ \bad -> do
  need "negative differs from literal oracle" (bad /= golden)
  need "wrong prefix escape separator rejected" (not (exact bad (A.definitionName "" ordinary)))
 let texts = ["","z","zz","z0z","z3az","_","a_b","a:b","\0","λ😀"] ++
             [replicate n 'a' ++ middle ++ replicate n 'b' |
                n <- [255,256,257], middle <- ["","z","_","λ😀"]]
 forM_ texts $ \input -> do
  let actual = S.compactName (text input)
  need "chunk boundary independent bytes" (exact (compact input) actual)
  need "component alphabet" (all (\c -> isAscii c && isAlphaNum c) (chars actual))
  need "scalar rendering bound" (length (chars actual) <= 8 * length input)
  let expected = currentName (text input) ordinary
  need "actual direct identity boundary" (P.eqString expected (A.definitionName (text input) ordinary))
  need "actual cached identity boundary" (P.eqString expected (A.definitionNameEncoded (encoded (text input)) ordinary))
 need "finite component injectivity"
  (length (nub (map (chars . S.compactName . text) texts)) == length (nub texts))
 let pairs = [("ab","c"),("a","bc"),("a_","b"),("a","_b"),("","a_b")]
 need "component separator injectivity" (length (nub [compact a ++ "_" ++ compact b | (a,b) <- pairs]) == length pairs)
 let branches = [(M.Entity "MLF.Primitive" "callStack" M.Value,"mlfCallStack"),
                 (M.Entity "MLF.Primitive" "CallStack" M.BuiltinType,"MLFCallStack"),
                 (M.Entity "MLF.Primitive" "HasCallStack" M.ManagedConstraint,"MLFHasCallStack"),
                 (M.Entity "Prelude" "Int" M.BuiltinType,"Int"),
                 (M.Entity "Own" "Unusual" M.BuiltinType,"Unusual")]
 forM_ branches $ \(entity,want) -> do
  need "retained branch independent golden" (exact want (currentName "crate" entity))
  need "retained branch actual golden" (exact want (A.definitionName "crate" entity))
 let roles = [M.Value,M.Datatype,M.Class,M.ManagedConstraint,M.Constructor "T",M.Constructor "U",M.Method "T",M.Method "U"]
     entities = [M.Entity owner "x" role | owner <- ["U","V"], role <- roles]
 forM_ entities $ \entity ->
  need "full role parent and owner oracle" (P.eqString (currentName "crate" entity) (A.definitionName "crate" entity))
 need "role parent owner remain distinct" (length (nub (map (chars . A.definitionName "crate") entities)) == length entities)
 -- Historical decimal spelling is not silently an alternate cached c1 input.
 need "old cached encoding is not current identity"
  (not (P.eqString (currentName "z_" ordinary) (A.definitionNameEncoded (S.encoded "z_") ordinary)))

-- Run against the physically extracted historical four-function component.
-- This does not qualify historical shared metadata or a complete old compiler.
historicalControls :: IO ()
historicalControls = do
 let ordinary = M.Entity "U" "x" M.Value
     oldGolden = "module_z_49_58_85_49_58_120_53_58_118_97_108_117_101_48_58_"
     newGolden = "module_c1__1z3azU1z3azx5z3azvalue0z3az"
 need "historical independent full literal" (exact oldGolden (historicalName "" ordinary))
 need "historical physical full literal" (exact oldGolden (H.definitionName "" ordinary))
 need "historical physical cached literal" (exact oldGolden (H.definitionNameEncoded "" ordinary))
 need "current independent full literal witness" (exact newGolden (currentName "" ordinary))
 need "current physical full literal witness" (exact newGolden (A.definitionName "" ordinary))
 need "historical and current spelling are distinct" (oldGolden /= newGolden &&
   not (P.eqString (H.definitionName "" ordinary) (A.definitionName "" ordinary)))
 let identities = ["","z0z","z_","é\0😀","mlf:crate:test"]
     owners = ["","U","模块","z_"]
     spellings = ["","x","λ😀","z3az","a_b"]
     roles = [M.Value,M.Datatype,M.Class,M.ManagedConstraint,M.Constructor "T",
              M.Constructor "U",M.Method "T",M.Method "U",M.Primitive T.PAddInt,M.Boolean True]
 forM_ identities $ \identity -> forM_ owners $ \owner ->
  forM_ spellings $ \spelling -> forM_ roles $ \role -> do
   let entity = M.Entity (text owner) (text spelling) role
       expected = historicalName (text identity) entity
       actual = H.definitionName (text identity) entity
       cached = H.definitionNameEncoded (text (decimal identity)) entity
   need "historical independent decimal framing direct" (P.eqString expected actual)
   need "historical independent decimal framing cached" (P.eqString expected cached)
   need "historical ordinary and current remain separate" (not (P.eqString actual (A.definitionName (text identity) entity)))
 let bad = [newGolden,
            "Module_z_49_58_85_49_58_120_53_58_118_97_108_117_101_48_58_",
            "module_49_58_85_49_58_120_53_58_118_97_108_117_101_48_58_",
            "module_z_49_58_85_49_58_120_53_58_118_97_108_117_101_48_59_"]
 forM_ bad $ \value -> do
  need "historical negative differs from literal" (value /= oldGolden)
  need "historical incorrect prefix separator or scalar differs" (not (exact value (H.definitionName "" ordinary)))
 need "compact prefix is not historical cached identity"
  (not (P.eqString (historicalName "z_" ordinary) (H.definitionNameEncoded (encoded "z_") ordinary)))
