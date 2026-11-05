{-# LANGUAGE OverloadedStrings #-}
-- Host-only acceptance harness. All changed old logic is frozen separately;
-- unchanged parsers/semantic validators are shared, not claimed independent.
module Main where

import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_, unless)
import qualified Data.ByteString as BS
import Data.Char (chr)
import Data.IORef
import Data.List (isInfixOf)
import System.Directory (createDirectory, doesFileExist)
import System.Environment (getArgs)
import System.FilePath ((</>))
import qualified Bootstrap.Types as T
import qualified Bootstrap.Crate as C
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as S
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Pretty as Pretty
import qualified FrozenFingerprint as Old
import qualified MLF.Host.Base as H

observeDigest :: H.String -> IO (Either String String)
observeDigest value = do
  answer <- try (evaluate (BS.length (H.utf8 value) `seq` H.unpack value))
    :: IO (Either SomeException String)
  pure (case answer of Left exception -> Left (displayException exception); Right result -> Right result)

observeState :: (Integer,Integer) -> IO (Either String (Integer,Integer))
observeState value = do
  answer <- try (evaluate (case value of (a,b) -> a `seq` b `seq` (a,b)))
    :: IO (Either SomeException (Integer,Integer))
  pure (case answer of Left exception -> Left (displayException exception); Right result -> Right result)

observeOuter :: (Integer,Integer) -> IO (Either String Bool)
observeOuter value = do
  answer <- try (evaluate (case value of (_,_) -> True)) :: IO (Either SomeException Bool)
  pure (case answer of Left exception -> Left (displayException exception); Right result -> Right result)

-- This binding must continue to typecheck with the preceding public API.
compilePreparedAPI :: C.CrateSpec -> [(H.String,A.CrateInterface)] -> C.PreparedCrate ->
  IO (T.Either H.String (A.CrateObject,Q.QueryReport))
compilePreparedAPI = C.compilePrepared

check :: IORef Int -> String -> Bool -> IO ()
check count label result = do
  unless result (error ("fingerprint control failed: " ++ label))
  modifyIORef' count (+1)

textEqual :: IORef Int -> String -> H.String -> H.String -> IO ()
textEqual count label expected actual =
  check count label (H.utf8 expected == H.utf8 actual)

right :: String -> T.Either H.String a -> a
right label answer = case answer of
  T.Left message -> error (label ++ ": " ++ H.unpack message)
  T.Right value -> value

decodeImage :: T.Either H.String A.CrateInterface -> Either String String
decodeImage answer = case answer of
  T.Left message -> Left (H.unpack message)
  T.Right iface -> Right (H.unpack (Old.oldEncodeInterface iface))

base :: H.String -> A.CrateInterface
base identity = A.CrateInterface identity [] ["Fixture"] [("Fixture",[])]
  [("Fixture",[])] [] [] [] [] [] "" "pending" []

declA, declB :: T.DataDecl
declA = T.DataDecl "Alpha" [] [T.ConstructorDecl "A" []]
declB = T.DataDecl "Beta" [] [T.ConstructorDecl "B" []]

unit :: H.String -> [T.DataDecl] -> [T.DataDecl] -> T.XTerm -> S.UnitObject
unit name header body term =
  let payload = if null body then term else T.XWithData body term
      iface = S.UnitInterface name [] [] header [] [] []
        (S.fingerprint (Pretty.prettyTerm payload))
  in S.UnitObject iface payload

checkedUnit :: S.UnitObject
checkedUnit =
  let term = T.XStringTerm "checked: λ\x1f642\0\n"
      checked = right "independent checked fixture" (Checked.check term)
      iface = S.UnitInterface "Checked" [] [] [] [] [] []
        (S.fingerprint (Pretty.prettyTerm term))
  in S.CheckedUnitObject iface checked

fragmentCases :: [(String,[S.UnitObject])]
fragmentCases =
  [ ("empty",[])
  , ("int",[unit "One" [] [] (T.XIntTerm 7)])
  , ("unicode",[unit "Unicode" [] [] (T.XStringTerm "ASCII λ 中文 \x1f642 e\x0301\0\n")])
  , ("shared-layout",[unit "One" [declA] [declA] (T.XIntTerm 1),
                       unit "Two" [declA] [declA] (T.XIntTerm 2)])
  , ("different-header-body",[unit "Different" [declA] [declB] (T.XIntTerm 3)])
  , ("header-only",[unit "Header" [declA] [] (T.XIntTerm 4)])
  , ("body-only",[unit "Body" [] [declB] (T.XIntTerm 5)])
  , ("checked",[checkedUnit])
  ]

replaceAt :: Int -> a -> [a] -> [a]
replaceAt wanted replacement values =
  [if n == wanted then replacement else value | (n,value) <- zip [0..] values]

canonicalFromPrefix :: [H.String] -> H.String
canonicalFromPrefix fields = S.pack (fields ++ [S.fingerprint (S.pack fields)])

metadataCases :: A.CrateInterface -> [(String,H.String,Bool)]
metadataCases iface =
  let encoded = Old.oldEncodeInterface iface
      fields = right "unpack canonical fixture" (S.unpack encoded)
      prefix = init fields
      changed index value = canonicalFromPrefix (replaceAt index value prefix)
  in [ ("canonical", encoded, True)
     , ("checksum", S.pack (init fields ++ ["wrong-checksum"]), False)
     , ("outer-leading-zero", H.literal ("0" ++ H.unpack encoded), False)
     , ("truncated", H.literal (init (H.unpack encoded)), False)
     , ("extra-field", S.pack (fields ++ ["extra"]), False)
     , ("epoch-valid-checksum", changed 0 "MLFCI-4", False)
     , ("empty-identity-valid-checksum", changed 1 "", False)
     , ("empty-body-hash-valid-checksum", changed 11 "", False)
     , ("noncanonical-inner-frame", changed 3 "07:Fixture", False)
     , ("duplicate-modules", changed 3 (S.pack ["Fixture","Fixture"]), False)
     , ("module-exports-mismatch", changed 4 "", False)
     , ("module-reach-mismatch", changed 5 "", False)
     , ("executable-metadata", changed 6 "injected = 1", False)
     , ("malformed-protection", changed 12 (S.pack [S.pack ["x","maybe"]]), False)
     , ("protection-inventory-mismatch", changed 12 (S.pack [S.pack ["x","true"]]), False)
     ]

pureControls :: IORef Int -> IO ()
pureControls count = do
  forM_ ["crate:ascii","crate:λ/中文/\x1f642","crate:e\x0301\0\n"] $ \identity ->
    forM_ fragmentCases $ \(label,fragments) -> do
      let iface = base identity
          before = Old.oldMakeObject iface fragments
          after = A.makeObject iface fragments
          (paired,payload) = A.makeObjectWithPayload iface fragments
          interfaceText = A.encodeInterface (A.objectInterface paired)
          oldText = Old.oldEncodeObject before
      textEqual count (label ++ "/make-interface")
        (Old.oldEncodeInterface (A.objectInterface before))
        (A.encodeInterface (A.objectInterface after))
      textEqual count (label ++ "/object") oldText (A.encodeObject after)
      textEqual count (label ++ "/paired-object") oldText
        (A.encodePooledObject (A.objectInterface paired) interfaceText payload)
      textEqual count (label ++ "/payload") (A.encodePooledPayload fragments) payload
      textEqual count (label ++ "/interface-sharing") oldText
        (A.encodeObjectWithInterface paired interfaceText)
      check count (label ++ "/interface-validation") $
        case A.validateInterface (A.objectInterface paired) of
          T.Left _ -> False
          T.Right _ -> True
      forM_ (metadataCases (A.objectInterface paired)) $ \(name,input,accepted) -> do
        let expected = decodeImage (Old.oldDecodeInterface input)
            actual = decodeImage (A.decodeInterface input)
        check count (label ++ "/decode/" ++ name) (expected == actual)
        check count (label ++ "/acceptance/" ++ name) $
          case actual of Left _ -> not accepted; Right _ -> accepted
  -- Different contexts are byte-preserved, not silently unified to the header.
  let header = unit "Mismatch" [declA] [declB] (T.XIntTerm 0)
      repaired = unit "Mismatch" [declA] [declA] (T.XIntTerm 0)
  check count "header/body distinction" $
    H.utf8 (A.encodePooledPayload [header]) /= H.utf8 (A.encodePooledPayload [repaired])
  let iface = base "malformed-object-control"
      object = Old.oldMakeObject iface []
      full = Old.oldEncodeObject object
      fields = right "object fields" (S.unpack full)
      malformed = [H.literal ("0" ++ H.unpack full), S.pack (replaceAt 0 "MLFCO-0" fields),
        S.pack (replaceAt 1 "different-identity" fields), S.pack (replaceAt 2 "bad-metadata" fields),
        S.pack (replaceAt 3 "bad-payload" fields)]
  forM_ (zip [0::Int ..] malformed) $ \(number,input) ->
    check count ("unchanged object rejection/" ++ show number) $
      case A.decodeObject (A.objectInterface object) input of T.Left _ -> True; T.Right _ -> False
  -- Valid semantics and verified raw checksums still cannot admit unsorted
  -- module, binding or protection encodings. This reaches canonical equality,
  -- rather than being rejected earlier by malformed metadata checks.
  let sortedIface = A.CrateInterface "sorting" [] ["Zeta","Alpha"]
        [("Zeta",[]),("Alpha",[])] [("Zeta",[]),("Alpha",[])] [] [] [] []
        [("z",T.XCon "Int" []),("a",T.XCon "String" [])] "" "body"
        [("z",True),("a",False)]
      canonical = Old.oldEncodeInterface sortedIface
      sortedFields = init (right "sorting fields" (S.unpack canonical))
  forM_ [3,9,12] $ \position -> do
    let entries = right "sorting entries" (S.unpack (sortedFields !! position))
        input = canonicalFromPrefix (replaceAt position (S.pack (reverse entries)) sortedFields)
        expected = decodeImage (Old.oldDecodeInterface input)
        actual = decodeImage (A.decodeInterface input)
    check count ("canonical-sorting/" ++ show position) (expected == actual)
    check count ("canonical-sorting-error/" ++ show position)
      (actual == Left "noncanonical crate metadata")
  check count "unpaired payload cannot bypass checksum validation" $
    case A.decodeObject (A.objectInterface object)
      (A.encodePooledObject (A.objectInterface object)
        (A.encodeInterface (A.objectInterface object)) "different payload") of
      T.Left message -> H.unpack message == "crate object checksum mismatch"
      T.Right _ -> False

lazyControls :: IORef Int -> IO ()
lazyControls count = do
  let ignoredFragments = error "forced unused fragments"
      iface = base "lazy"
  textEqual count "old makeObject leaves fragments lazy" "lazy"
    (A.crateId (A.objectInterface (Old.oldMakeObject iface ignoredFragments)))
  textEqual count "makeObject leaves fragments lazy" "lazy"
    (A.crateId (A.objectInterface (A.makeObject iface ignoredFragments)))
  textEqual count "paired makeObject leaves fragments lazy" "lazy"
    (A.crateId (A.objectInterface (fst (A.makeObjectWithPayload iface ignoredFragments))))
  textEqual count "payload does not force unused iface" (A.encodePooledPayload [])
    (snd (A.makeObjectWithPayload (error "forced unused iface") []))
  -- The type witness itself is a function value, not an IO compilation.
  evaluate compilePreparedAPI >> check count "compilePrepared public API" True

writeControls :: IORef Int -> FilePath -> IO ()
writeControls count directory = do
  forM_ (zip [0::Int ..] fragmentCases) $ \(number,(label,fragments)) -> do
    let iface = base "write:λ\x1f642"
        before = Old.oldMakeObject iface fragments
        (paired,payload) = A.makeObjectWithPayload iface fragments
        root = directory </> show number
        oldPrefix = H.literal (root ++ "-old")
        newPrefix = H.literal (root ++ "-new")
        pairedPrefix = H.literal (root ++ "-paired")
    Old.oldWriteObject oldPrefix before
    A.writeObject newPrefix paired
    A.writeObjectWithPayload pairedPrefix paired payload
    forM_ [".mlfco",".mlfci"] $ \suffix -> do
      expected <- BS.readFile (root ++ "-old" ++ suffix)
      actual <- BS.readFile (root ++ "-new" ++ suffix)
      carried <- BS.readFile (root ++ "-paired" ++ suffix)
      check count (label ++ "/write/" ++ suffix) (expected == actual && expected == carried)
  let legacyIface = A.withObjectFingerprint (base "legacy") (A.legacyFragmentFingerprint [])
      legacy = A.LegacyCrateObject legacyIface []
  Old.oldWriteObject (H.literal (directory </> "legacy-old")) legacy
  A.writeObject (H.literal (directory </> "legacy-new")) legacy
  A.writeObjectWithPayload (H.literal (directory </> "legacy-paired")) legacy
    (error "legacy forced unused pooled payload")
  forM_ [".mlfco",".mlfci"] $ \suffix -> do
    expected <- BS.readFile (directory </> ("legacy-old" ++ suffix))
    actual <- BS.readFile (directory </> ("legacy-new" ++ suffix))
    paired <- BS.readFile (directory </> ("legacy-paired" ++ suffix))
    check count ("legacy/" ++ suffix) (expected == actual && expected == paired)
  -- Unwritable .mlfco must fail before .mlfci is created, on every path.
  forM_ [0::Int ..2] $ \mode -> do
    let prefix = directory </> ("blocked-" ++ show mode)
        (object,payload) = A.makeObjectWithPayload (base "blocked") []
        action = case mode of
          0 -> Old.oldWriteObject (H.literal prefix) object
          1 -> A.writeObject (H.literal prefix) object
          _ -> A.writeObjectWithPayload (H.literal prefix) object payload
    createDirectory (prefix ++ ".mlfco")
    outcome <- try action :: IO (Either SomeException ())
    metadata <- doesFileExist (prefix ++ ".mlfci")
    check count ("write-order/" ++ show mode) $
      not metadata && case outcome of
        Left exception -> "file write failed" `isInfixOf` displayException exception
        Right _ -> False
  -- Failure of the second write must leave the first, complete object bytes.
  forM_ [0::Int ..2] $ \mode -> do
    let prefix = directory </> ("blocked-interface-" ++ show mode)
        (object,payload) = A.makeObjectWithPayload (base "blocked-interface") []
        action = case mode of
          0 -> Old.oldWriteObject (H.literal prefix) object
          1 -> A.writeObject (H.literal prefix) object
          _ -> A.writeObjectWithPayload (H.literal prefix) object payload
    createDirectory (prefix ++ ".mlfci")
    outcome <- try action :: IO (Either SomeException ())
    bytes <- BS.readFile (prefix ++ ".mlfco")
    check count ("second-write-failure/" ++ show mode) $
      bytes == H.utf8 (Old.oldEncodeObject object) && case outcome of
        Left exception -> "file write failed" `isInfixOf` displayException exception
        Right _ -> False
  -- Filename validation precedes payload demand; retain the original error.
  forM_ [0::Int ..2] $ \mode -> do
    let prefix = H.literal (directory ++ "/bad\0path")
        object = error "forced object before invalid filename"
        action = case mode of
          0 -> Old.oldWriteObject prefix object
          1 -> A.writeObject prefix object
          _ -> A.writeObjectWithPayload prefix object (error "forced payload before invalid filename")
    outcome <- try action :: IO (Either SomeException ())
    check count ("invalid-path-demand/" ++ show mode) $ case outcome of
      Left exception -> "file path contains NUL" `isInfixOf` displayException exception
      Right _ -> False

-- Actual production Separate functions versus the independently frozen old
-- indexed loops, not merely a translated checksum algebra. Empty/end states
-- deliberately remain unnormalized; negative offsets keep the indexed errors.
streamControls :: IORef Int -> IO ()
streamControls count = do
  let texts = ["", "ASCII", "nul\0newline\n", "λ中文\x1f642", "e\x0301",
        map chr [0,127,128,255,2047,2048,0xd7ff,0xe000,0xffff,0x10000,0x10ffff],
        concat (replicate 17 "λ\x1f642")]
        ++ [replicate n 'x' | n <- [31,32,33,255,256,257,4095,4096,4097]]
      states = [(0,1),(0,0),(17,29),(-17,-29),(2147483647,2147483629),(10^40,negate (10^40))]
  forM_ (zip [0::Int ..] texts) $ \(number,chars) -> do
    let value = H.literal chars
        offsets = [-2,-1,0,1,2,toInteger (length chars),toInteger (length chars)+3]
    textEqual count ("stream/full/" ++ show number) (Old.oldFingerprint value) (S.fingerprint value)
    check count ("stream/part/" ++ show number) (Old.oldFingerprintPart value == S.fingerprintPart value)
    forM_ states $ \(a,b) -> do
      textEqual count "stream/after" (Old.oldFingerprintAfter (a,b) value) (S.fingerprintAfter (a,b) value)
      check count "stream/append" $
        Old.oldFingerprintAppend (a,b) (Old.oldFingerprintPart value) ==
        S.fingerprintAppend (a,b) (S.fingerprintPart value)
      forM_ offsets $ \offset -> do
        oldDigest <- observeDigest (Old.oldFingerprintFrom value offset a b)
        newDigest <- observeDigest (S.fingerprintFrom value offset a b)
        check count ("stream/digest/" ++ show (number,offset,a,b)) (oldDigest == newDigest)
        oldState <- observeState (Old.oldFingerprintStateFrom value offset a b)
        newState <- observeState (S.fingerprintStateFrom value offset a b)
        check count ("stream/state/" ++ show (number,offset,a,b)) (oldState == newState)
  let failureCases =
        [ ("text", H.failure "stream-text", 0, 0, 1)
        , ("index", "A", H.failure "stream-index", 0, 1)
        , ("seed-a", "A", 0, H.failure "stream-seed-a", 1)
        , ("seed-b", "A", 0, 0, H.failure "stream-seed-b")
        , ("negative-seed-a", "A", -1, H.failure "stream-seed-a", 1)
        , ("negative-seed-b", "A", -1, 0, H.failure "stream-seed-b")
        , ("end-seed-b", "A", 1, 7, H.failure "stream-seed-b")
        , ("empty-seed-a", "", 0, H.failure "stream-seed-a", 1)
        , ("invalid-scalar", H.literal [chr 0xd800], 0, 0, 1)
        , ("text-and-index", H.failure "stream-text", H.failure "stream-index", 0, 1)
        ]
      failed result = case result of Left _ -> True; Right _ -> False
  forM_ failureCases $ \(label,value,offset,a,b) -> do
    oldDigest <- observeDigest (Old.oldFingerprintFrom value offset a b)
    newDigest <- observeDigest (S.fingerprintFrom value offset a b)
    check count ("stream/failure-digest/" ++ label) (failed oldDigest && oldDigest == newDigest)
    oldState <- observeState (Old.oldFingerprintStateFrom value offset a b)
    newState <- observeState (S.fingerprintStateFrom value offset a b)
    check count ("stream/failure-state/" ++ label) (failed oldState && oldState == newState)
  forM_ [("",0),("A",1),("A",3)] $ \(value,offset) -> do
    expected <- observeOuter (Old.oldFingerprintStateFrom value offset (H.failure "lazy-a") (H.failure "lazy-b"))
    actual <- observeOuter (S.fingerprintStateFrom value offset (H.failure "lazy-a") (H.failure "lazy-b"))
    check count "stream/lazy-terminal-state" (expected == Right True && actual == expected)
  check count "stream/lazy-first-field" $
    fst (Old.oldFingerprintStateFrom "" 0 43 (H.failure "lazy-b")) == 43 &&
    fst (S.fingerprintStateFrom "" 0 43 (H.failure "lazy-b")) == 43
  check count "stream/lazy-second-field" $
    snd (Old.oldFingerprintStateFrom "" 0 (H.failure "lazy-a") 59) == 59 &&
    snd (S.fingerprintStateFrom "" 0 (H.failure "lazy-a") 59) == 59
  oldLoop <- observeOuter (Old.oldFingerprintStateFrom "A" 0 0 (H.failure "loop-seed-b"))
  newLoop <- observeOuter (S.fingerprintStateFrom "A" 0 0 (H.failure "loop-seed-b"))
  check count "stream/loop-retains-strict-state" (failed oldLoop && oldLoop == newLoop)

main :: IO ()
main = do
  arguments <- getArgs
  directory <- case arguments of
    [path] -> pure path
    _ -> error "usage: fingerprint-differential NEW-OUTPUT-DIRECTORY"
  createDirectory directory
  count <- newIORef 0
  pureControls count
  lazyControls count
  writeControls count directory
  streamControls count
  total <- readIORef count
  putStrLn ("{\"format\":\"fingerprint-differential-v1\",\"complete\":true,\"checks\":" ++ show total ++ "}")
  putStrLn "Frozen fingerprint byte/error/lazy and write-order controls passed."
