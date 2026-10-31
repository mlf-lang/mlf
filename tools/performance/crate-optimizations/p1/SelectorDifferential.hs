{-# LANGUAGE OverloadedStrings #-}
-- Test-only host entry. No compiler implementation is rewritten here.
-- FrozenSelectors is independently captured from the corrected baseline.
module Main where

import Control.Exception (SomeException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.IORef
import Data.List (isInfixOf, subsequences)
import qualified Bootstrap.Module as Candidate
import qualified FrozenSelectors as Oracle
import qualified Bootstrap.Types as T
import qualified FrozenSelectorMap as Map
import qualified Bootstrap.Map as CandidateMap
import qualified FrozenSelectorSet as Set
import qualified Bootstrap.Set as CandidateSet
import qualified Bootstrap.Primitive as Primitive
import qualified MLF.Host.Base as Host

type EntityImage = (String, String, (Integer, String))
type InterfaceImage = [((Integer, String), [EntityImage])]
type Entry = (String, Candidate.Entity)

roleImage :: Candidate.Role -> (Integer, String)
roleImage role = case role of
  Candidate.Value -> (0, "")
  Candidate.Datatype -> (1, "")
  Candidate.Class -> (2, "")
  Candidate.Constructor name -> (3, Host.unpack name)
  Candidate.Method name -> (4, Host.unpack name)
  Candidate.BuiltinType -> (5, "")
  Candidate.Primitive value -> (6, show (Primitive.primitiveCode value))
  Candidate.Boolean value -> (7, show value)
  Candidate.ManagedConstraint -> (8, "")

entityImage :: Candidate.Entity -> EntityImage
entityImage (Candidate.Entity owner name role) =
  (Host.unpack owner, Host.unpack name, roleImage role)

interfaceImage :: Candidate.Interface -> InterfaceImage
interfaceImage (Candidate.Interface entries) =
  [ ((Oracle.spaceCode space, Host.unpack name), map entityImage (Set.toList entities))
  | ((space, name), entities) <- Map.toList entries ]

resultImage :: T.Either Host.String Candidate.Interface -> Either String InterfaceImage
resultImage result = case result of
  T.Left message -> Left (Host.unpack message)
  T.Right interface -> Right (interfaceImage interface)

-- Build both implementations' input through frozen comparators, not candidate
-- interface/visible or collections. Frozen and candidate collections share
-- Bootstrap.Types datatypes, so no conversion (or candidate setup) is needed.
-- The same original identity may occur under many aliases.
environment :: [Entry] -> Candidate.Interface
environment entries = Candidate.Interface $
  Map.fromListWith Oracle.compareKey (Set.union Oracle.compareEntity)
    [ ((Oracle.space entity, Host.literal key), Set.singleton entity)
    | (key, entity) <- entries ]

entity :: String -> String -> Candidate.Role -> Candidate.Entity
entity owner name role = Candidate.Entity (Host.literal owner) (Host.literal name) role

memberCases :: [(String, T.Members)]
memberCases =
  [ ("abstract", T.Abstract)
  , ("all", T.AllMembers)
  , ("empty-members", T.Members [])
  , ("C", T.Members ["C"])
  , ("method", T.Members ["method"])
  , ("missing", T.Members ["missing"])
  , ("duplicates", T.Members ["C", "C"])
  , ("ordered", T.Members ["method", "C"])
  , ("unicode", T.Members ["λ", "构造", "🙂"])
  , ("boolean", T.Members ["True", "False"])
  ]

compareValue :: (Eq a, Show a) => IORef Integer -> String -> a -> a -> IO ()
compareValue count label expected actual = do
  outcome <- try (evaluate (expected == actual)) :: IO (Either SomeException Bool)
  case outcome of
    Left exception -> error (label ++ ": unexpected exception: " ++ show exception)
    Right False -> error (label ++ ":\nexpected " ++ show expected ++ "\nactual " ++ show actual)
    Right True -> modifyIORef' count (+1)

checkEnvironment :: IORef Integer -> String -> [String] -> [Entry] -> IO ()
checkEnvironment count label names entries = do
  let env = environment entries
  forM_ names $ \name -> forM_ memberCases $ \(memberLabel, members) -> do
    let text = Host.literal name
        item = T.ExportType text members
        suffix = label ++ "/" ++ name ++ "/" ++ memberLabel
    compareValue count (suffix ++ "/selectType")
      (resultImage (Oracle.selectType env text members))
      (resultImage (Candidate.selectType env text members))
    forM_ [False, True] $ \hiding -> do
      compareValue count (suffix ++ "/selectItem/" ++ show hiding)
        (resultImage (Oracle.selectItem hiding env item))
        (resultImage (Candidate.selectItem hiding env item))
      compareValue count (suffix ++ "/partialSelectItem/" ++ show hiding)
        (interfaceImage (Oracle.partialSelectItem hiding env item))
        (interfaceImage (Candidate.partialSelectItem hiding env item))
  forM_ names $ \name -> forM_ [False, True] $ \hiding -> do
    let text = Host.literal name
    forM_ [("value", T.ExportValue text), ("module", T.ExportModule text)] $ \(kind, item) -> do
      compareValue count (label ++ "/" ++ name ++ "/" ++ kind ++ "/selectItem/" ++ show hiding)
        (resultImage (Oracle.selectItem hiding env item))
        (resultImage (Candidate.selectItem hiding env item))
      compareValue count (label ++ "/" ++ name ++ "/" ++ kind ++ "/partialSelectItem/" ++ show hiding)
        (interfaceImage (Oracle.partialSelectItem hiding env item))
        (interfaceImage (Candidate.partialSelectItem hiding env item))

smallPool :: [Entry]
smallPool =
  [ ("T", entity "A" "T" Candidate.Datatype)
  , ("T", entity "B" "T" Candidate.Datatype)
  , ("C", entity "A" "C" (Candidate.Constructor "T"))
  , ("C", entity "B" "C" (Candidate.Constructor "T"))
  , ("Class", entity "A" "Class" Candidate.Class)
  , ("method", entity "A" "method" (Candidate.Method "Class"))
  , ("value", entity "A" "value" Candidate.Value)
  ]

layouts :: [Entry] -> [[Entry]]
layouts entries =
  [ entries
  , reverse entries
  , entries ++ entries ++ [("Q." ++ key, value) | (key, value) <- entries]
  , reverse (entries ++ [("Q." ++ key, value) | (key, value) <- entries]
                     ++ [("Long.Alias." ++ key, value) | (key, value) <- entries])
  ]

authored :: [(String, [String], [Entry])]
authored =
  [ ("Boolean-parent", ["Bool", "Q.Bool", "T", "Missing"],
      [ ("Bool", entity "Prelude" "Bool" Candidate.BuiltinType)
      , ("Q.Bool", entity "Prelude" "Bool" Candidate.BuiltinType)
      , ("True", entity "Prelude" "True" (Candidate.Boolean True))
      , ("Q.True", entity "Prelude" "True" (Candidate.Boolean True))
      , ("False", entity "Prelude" "False" (Candidate.Boolean False))
      , ("Foreign.True", entity "Foreign" "True" (Candidate.Boolean True))
      , ("Bool", entity "Foreign" "Bool" Candidate.Datatype)
      , ("T", entity "A" "T" Candidate.Datatype) ])
  , ("unicode-metadata", ["Ω", "Q.Ω", "Class", "Missing"],
      [ ("Ω", entity "模块" "Ω" Candidate.Datatype)
      , ("Q.Ω", entity "模块" "Ω" Candidate.Datatype)
      , ("λ", entity "模块" "λ" (Candidate.Constructor "Ω"))
      , ("构造", entity "模块" "构造" (Candidate.Constructor "Ω"))
      , ("🙂", entity "模块" "🙂" (Candidate.Constructor "Ω"))
      , ("Class", entity "模块" "Class" Candidate.Class)
      , ("method", entity "模块" "method" (Candidate.Method "Class")) ])
  , ("all-roles-and-member-collision", ["T", "Class", "Managed", "Int", "Missing"],
      [ ("T", entity "A" "T" Candidate.Datatype)
      , ("Class", entity "A" "Class" Candidate.Class)
      , ("C", entity "A" "C" (Candidate.Constructor "T"))
      , ("C", entity "A" "C" (Candidate.Method "T"))
      , ("C", entity "A" "C" Candidate.Value)
      , ("C", entity "B" "C" (Candidate.Constructor "T"))
      , ("method", entity "A" "method" (Candidate.Method "Class"))
      , ("Managed", entity "A" "Managed" Candidate.ManagedConstraint)
      , ("Int", entity "Prelude" "Int" Candidate.BuiltinType)
      , ("addInt", entity "Prelude" "addInt" (Candidate.Primitive T.PAddInt)) ])
  , ("hiding-type-constructor-same-name", ["T", "Q.T", "Missing"],
      [ ("T", entity "A" "T" Candidate.Datatype)
      , ("T", entity "A" "T" (Candidate.Constructor "T"))
      , ("Q.T", entity "A" "T" Candidate.Datatype)
      , ("Q.T", entity "A" "T" (Candidate.Constructor "T")) ])
  , ("source-reference-prefix", ["T", "$MLF.Source.T", "$MLF.Source.Q.T"],
      [ ("T", entity "A" "T" Candidate.Datatype)
      , ("Q.T", entity "A" "T" Candidate.Datatype)
      , ("C", entity "A" "C" (Candidate.Constructor "T")) ])
  ]

stressEntries :: Int -> [Entry]
stressEntries count = concat
  [ [ (prefix ++ key, value)
    | (key, value) <-
        [ (typeName, entity owner typeName Candidate.Datatype)
        , ("C", entity owner "C" (Candidate.Constructor (Host.literal typeName)))
        , ("method", entity owner "method" (Candidate.Method (Host.literal typeName)))
        , ("unrelated", entity owner "unrelated" Candidate.Value) ]
    , prefix <- ["", "Q.", "Alias.", "Deep.Alias."] ]
  | index <- [0..count-1]
  , let owner = "Owner" ++ show index
        typeName = "T" ++ show index ]

-- Test helpers themselves must be sensitive to poisoned child enumeration.
-- Map's stored values are intentionally lazy; this is a valid map shape with
-- one explicitly undefined unrelated value, not a claim about all malformed
-- internal graphs. Abstract/empty member requests must not enumerate it.
poisonedEnvironment :: Candidate.Interface
poisonedEnvironment = Candidate.Interface $
  Map.fromList Oracle.compareKey
    [ ((Candidate.Types, "T"), Set.singleton (entity "A" "T" Candidate.Datatype))
    , ((Candidate.Terms, "ok"), Set.singleton (entity "A" "ok" Candidate.Value))
    , ((Candidate.Terms, "unused"), error "unused child memo forced") ]

expectThrows :: IORef Integer -> String -> Bool -> IO ()
expectThrows count label value = do
  outcome <- try (evaluate value) :: IO (Either SomeException Bool)
  case outcome of
    Left exception | "unused child memo forced" `isInfixOf` show exception -> modifyIORef' count (+1)
    _ -> error (label ++ ": poison control did not raise the expected exception")

lazyControls :: IORef Integer -> IO ()
lazyControls count = do
  let env = poisonedEnvironment
      expectedType = resultImage (T.Right (Oracle.interface [entity "A" "T" Candidate.Datatype]))
      expectedValue = resultImage (T.Right (Oracle.interface [entity "A" "ok" Candidate.Value]))
      empty = interfaceImage Oracle.emptyInterface
  forM_ [("abstract", T.Abstract), ("empty-members", T.Members [])] $ \(label, members) -> do
    compareValue count ("lazy/oracle/" ++ label) expectedType (resultImage (Oracle.selectType env "T" members))
    compareValue count ("lazy/candidate/" ++ label) expectedType (resultImage (Candidate.selectType env "T" members))
  forM_ [False, True] $ \hiding -> do
    let item = T.ExportType "T" T.Abstract
    compareValue count ("lazy/oracle/partial-abstract/" ++ show hiding)
      expectedType (Right (interfaceImage (Oracle.partialSelectItem hiding env item)))
    compareValue count ("lazy/candidate/partial-abstract/" ++ show hiding)
      expectedType (Right (interfaceImage (Candidate.partialSelectItem hiding env item)))
    compareValue count ("lazy/oracle/value/" ++ show hiding)
      expectedValue (resultImage (Oracle.selectItem hiding env (T.ExportValue "ok")))
    compareValue count ("lazy/candidate/value/" ++ show hiding)
      expectedValue (resultImage (Candidate.selectItem hiding env (T.ExportValue "ok")))
    compareValue count ("lazy/oracle/module/" ++ show hiding) empty
      (interfaceImage (Oracle.partialSelectItem hiding (error "unused env") (T.ExportModule "Unused")))
    compareValue count ("lazy/candidate/module/" ++ show hiding) empty
      (interfaceImage (Candidate.partialSelectItem hiding (error "unused env") (T.ExportModule "Unused")))
  compareValue count "lazy/missing-type-short-circuit"
    (Left "name is not in scope: Missing")
    (resultImage (Candidate.selectType env "Missing" T.AllMembers))
  expectThrows count "lazy/oracle/all-sensitive"
    (resultImage (Oracle.selectType env "T" T.AllMembers) == expectedType)
  expectThrows count "lazy/candidate/all-sensitive"
    (resultImage (Candidate.selectType env "T" T.AllMembers) == expectedType)

fixedExpectations :: IORef Integer -> IO ()
fixedExpectations count = do
  let t = entity "A" "T" Candidate.Datatype
      c = entity "A" "C" (Candidate.Constructor "T")
      env = environment [("T",t),("Q.T",t),("C",c),("Q.C",c),("C",c)]
      want = Right [((0,"C"),[("A","C",(3,"T"))]),((1,"T"),[("A","T",(1,""))])]
  compareValue count "fixed/alias-dedup" want (resultImage (Candidate.selectType env "Q.T" T.AllMembers))
  compareValue count "fixed/repeated-request-dedup" want (resultImage (Candidate.selectType env "T" (T.Members ["C","C"])))
  compareValue count "fixed/unknown-member-error"
    (Left "missing is not a visible member of T")
    (resultImage (Candidate.selectType env "T" (T.Members ["missing"])))
  let ambiguous = environment [("T",t),("T",entity "B" "T" Candidate.Datatype)]
  compareValue count "fixed/ambiguity-order" (Left "ambiguous name T: A.T, B.T")
    (resultImage (Candidate.selectType ambiguous "T" T.Abstract))
  compareValue count "fixed/unknown-hidden-type" (Left "name is not exported: Missing")
    (resultImage (Candidate.selectItem True env (T.ExportType "Missing" T.Abstract)))

-- Equal ranks deliberately have different observable key representatives.
-- List-authored expectations neither call candidate operations nor derive from
-- the frozen map result; they check both implementations independently.
type CollectionKey = (Integer, String)

compareCollectionKey :: CollectionKey -> CollectionKey -> Integer
compareCollectionKey (a, _) (b, _) = if a < b then -1 else if a > b then 1 else 0

collectionControls :: IORef Integer -> IO ()
collectionControls count = do
  let ranks = [0..4] :: [Integer]
      leftKey rank = (rank, "left-" ++ show rank)
      rightKey rank = (rank, "right-" ++ show rank)
      leftValue rank = "L" ++ show rank
      rightValue rank = "R" ++ show rank
      combine left right = left ++ ">" ++ right
      cmp = compareCollectionKey
  forM_ (subsequences ranks) $ \left -> forM_ (subsequences ranks) $ \right -> do
    let a = Map.fromList cmp [(leftKey rank, leftValue rank) | rank <- left]
        b = Map.fromList cmp [(rightKey rank, rightValue rank) | rank <- reverse right]
        aset = Set.fromList cmp (map leftKey left)
        bset = Set.fromList cmp (map rightKey (reverse right))
        selected = [rank | rank <- ranks, rank `elem` left || rank `elem` right]
        key rank = if rank `elem` left then leftKey rank else rightKey rank
        value rank
          | rank `elem` left && rank `elem` right = combine (leftValue rank) (rightValue rank)
          | rank `elem` left = leftValue rank
          | otherwise = rightValue rank
        leftBiased rank = if rank `elem` left then leftValue rank else rightValue rank
        wantCombined = [(key rank, value rank) | rank <- selected]
        wantUnion = [(key rank, leftBiased rank) | rank <- selected]
        wantSet = map key selected
        expectedSize = toInteger (length selected)
        mapImage tree = (Map.toList tree, Map.valid cmp tree, Map.size tree)
        setImage values@(T.Set tree) = (Set.toList values, Map.valid cmp tree, Map.size tree)
        label = "collections/" ++ show left ++ "/" ++ show right
    -- The historical validator checks every cached subtree size, ordering and
    -- size-balance invariant independently of candidate operations. Correct
    -- enumeration alone must not hide a malformed persistent result tree.
    compareValue count (label ++ "/frozen/unionWith") (wantCombined, True, expectedSize)
      (mapImage (Map.unionWith cmp combine a b))
    compareValue count (label ++ "/candidate/unionWith") (wantCombined, True, expectedSize)
      (mapImage (CandidateMap.unionWith cmp combine a b))
    compareValue count (label ++ "/frozen/union") (wantUnion, True, expectedSize)
      (mapImage (Map.union cmp a b))
    compareValue count (label ++ "/candidate/union") (wantUnion, True, expectedSize)
      (mapImage (CandidateMap.union cmp a b))
    compareValue count (label ++ "/frozen/set-union") (wantSet, True, expectedSize)
      (setImage (Set.union cmp aset bset))
    compareValue count (label ++ "/candidate/set-union") (wantSet, True, expectedSize)
      (setImage (CandidateSet.union cmp aset bset))
  -- Valid tree shapes and total comparators; values/combining functions stay
  -- lazy. Deliberately do not claim equivalence for a bottom comparator:
  -- candidate's empty-right fast path can avoid old reconstruction comparisons.
  let cmp = compareCollectionKey
      a = Map.fromList cmp [((0,"left-0"), "L"),
                            ((1,"left-1"), error "stored value poison"),
                            ((2,"left-2"), "T")]
      b = Map.singleton (0,"right-0") (error "right value poison")
      small = Map.singleton (0,"small-left") "S"
      large = Map.fromList cmp [((0,"right-0"), error "right value poison"),
                                ((1,"right-1"), error "stored value poison"),
                                ((2,"right-2"), "U")]
      leftKeys = [(0,"left-0"),(1,"left-1"),(2,"left-2")]
      rightKeys = [(0,"small-left"),(1,"right-1"),(2,"right-2")]
      unusedCombine = error "combine poison"
  forM_ [("frozen", Map.unionWith), ("candidate", CandidateMap.unionWith)] $ \(label, unionWith) -> do
    let check suffix = compareValue count ("collections/lazy/" ++ label ++ "/" ++ suffix)
        joined = unionWith cmp const a b
    check "left-larger-keys" leftKeys (Map.keys (unionWith cmp unusedCombine a b))
    check "right-larger-keys" rightKeys (Map.keys (unionWith cmp unusedCombine small large))
    check "left-larger-left-value" "L" (Map.get cmp (0, "lookup") joined)
    check "right-larger-left-value" "S" (Map.get cmp (0, "lookup") (unionWith cmp const small large))
    check "empty-left-keys" leftKeys (Map.keys (unionWith cmp unusedCombine Map.empty a))
    check "empty-right-keys" leftKeys (Map.keys (unionWith cmp unusedCombine a Map.empty))
    check "disjoint-unused-combiner" [((0,"a"),"A"),((1,"b"),"B")]
      (Map.toList (unionWith cmp unusedCombine (Map.singleton (0,"a") "A") (Map.singleton (1,"b") "B")))
    expectCollectionPoison count (label ++ "/stored-value-sensitive") "stored value poison"
      (Map.get cmp (1, "lookup") joined == "unused")
    expectCollectionPoison count (label ++ "/combiner-sensitive") "combine poison"
      (Map.get cmp (0, "lookup") (unionWith cmp unusedCombine a b) == "unused")

expectCollectionPoison :: IORef Integer -> String -> String -> Bool -> IO ()
expectCollectionPoison count label message value = do
  outcome <- try (evaluate value) :: IO (Either SomeException Bool)
  case outcome of
    Left exception | message `isInfixOf` show exception -> modifyIORef' count (+1)
    _ -> error (label ++ ": collection poison control did not raise the expected exception")

main :: IO ()
main = do
  checks <- newIORef 0
  let subsets = subsequences smallPool
  forM_ (zip [0 :: Int ..] subsets) $ \(index, entries) ->
    forM_ (zip [0 :: Int ..] (layouts entries)) $ \(layout, variant) ->
      checkEnvironment checks ("exhaustive/" ++ show index ++ "/" ++ show layout)
        ["T", "Q.T", "Class", "C", "Missing"] variant
  forM_ authored $ \(label, names, entries) ->
    forM_ (zip [0 :: Int ..] (layouts entries)) $ \(layout, variant) ->
      checkEnvironment checks (label ++ "/" ++ show layout) names variant
  forM_ [32,128] $ \size -> forM_ [False,True] $ \backwards -> do
    let entries = stressEntries size
        ordered = if backwards then reverse entries else entries
    checkEnvironment checks ("stress/" ++ show size ++ "/reverse=" ++ show backwards)
      ["T0", "Q.T0", "T17", "Q.T17", "Missing"] ordered
  lazyControls checks
  fixedExpectations checks
  collections <- newIORef 0
  collectionControls collections
  collectionCount <- readIORef collections
  unless (collectionCount == 6162) (error ("collection test inventory changed: " ++ show collectionCount))
  count <- readIORef checks
  unless (count == 154072) (error ("test inventory changed: " ++ show count))
  putStrLn ("{\"format\":\"selector-differential-v1\",\"complete\":true,\"checks\":" ++ show count ++
    ",\"collection_checks\":" ++ show collectionCount ++ ",\"exhaustive_interfaces\":512,\"authored_interfaces\":20,\"stress_interfaces\":4,\"scope\":\"partial\"}")
  putStrLn "Frozen selector differential, ordered identity/error and lazy-demand controls passed."
