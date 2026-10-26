{-# LANGUAGE ScopedTypeVariables #-}
-- Independent finite semantic comparison. The reference is frozen before the
-- fast-path implementation; expected cases below are literal public contracts.
module Main where

import Prelude
import qualified Control.Exception as Exception
import Control.Monad (forM_, unless)
import Data.List (nub)
import qualified Bootstrap.Regex as Candidate
import qualified RegexReference as Reference
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B

assert :: Bool -> String -> IO ()
assert condition message = unless condition (error message)

pair :: T.Maybe (Integer, Integer) -> Maybe (Integer, Integer)
pair T.Nothing = Nothing
pair (T.Just value) = Just value

candidate :: String -> Candidate.Regex
candidate text = case Candidate.compile (B.literal text) of
  T.Left message -> error ("candidate rejected " ++ show text ++ ": " ++ B.unpack message)
  T.Right value -> value

reference :: String -> Reference.Regex
reference text = case Reference.compile (B.literal text) of
  T.Left message -> error ("reference rejected " ++ show text ++ ": " ++ B.unpack message)
  T.Right value -> value

-- All strings through length four over this alphabet. Unicode and LF take part
-- in the Cartesian product rather than appearing only in handpicked examples.
subjects :: [String]
subjects = concat [sequence (replicate n "ab\nα") | n <- [0..4]] ++
  ["😀a😀", "\0a\0", "αβω!", ">one\nAC\n>two\nTA\n", "<a><bc>",
   "|a||bc|", "prefix<unterminated", "a--b--z", "aaaaab", "xyz\nxyz",
   "aaacXab", "abaab", "ax", "ac", "ααβ"]

atoms :: [String]
atoms = ["a", "b", "[ab]", "[^a]", "[a-b]", ".", "α", "[α-ω]"]

patterns :: [String]
patterns = nub $ atoms ++ [a ++ b | a <- atoms, b <- atoms] ++
  [a ++ "|" ++ b | a <- atoms, b <- atoms] ++
  [a ++ suffix | a <- atoms, suffix <- ["*", "+", "?", "{0}", "{2}", "{1,3}", "{2,}"]] ++
  ["", "ab|a", "a|ab", "aa|bb", "ab|ba", "a[ab]|[ab]b", "a|abc",
   "(ab|ba){2}", "a.*z|b", "a*ab", "(a?)*", "(a*)*b", "(|a)*",
   "(|a)*b", "(a?|b)*", "(^|.)*", "(a?|.)*", "(a|aa)*b", "^a*$",
   "^", "$", "^$", "a$|^b", ">.*\n|\n", ">[^\n]*\n|\n",
   "<[^>]*>", "\\|[^|][^|]*\\|", "a.*b", "a[^b]*b", "a[^a]*a",
   "😀|α", "😀a|αβ", "[\0-\2]", "[^😀]", "\\d+", "\\w+\\s\\d+",
   "a[ac]*b", "aa+b", "a[cd]+b|x", "a[^b]*b|c", "α[^ω]*ω"]

checkPair :: String -> IO ()
checkPair patternText = checkSubjects patternText subjects

checkSubjects :: String -> [String] -> IO ()
checkSubjects patternText selectedSubjects = do
  let c = candidate patternText
      r = reference patternText
  forM_ selectedSubjects $ \subjectText -> do
    let subject = B.literal subjectText
        context = show (patternText, subjectText)
    forM_ [-1 .. toInteger (length subjectText) + 1] $ \offset ->
      assert (pair (Candidate.find c subject offset) == pair (Reference.find r subject offset))
        ("find disagreement: " ++ context ++ " offset=" ++ show offset)
    assert (Candidate.countMatches c subject == Reference.countMatches r subject)
      ("count disagreement: " ++ context)
    forM_ ["", "$1\\literal😀"] $ \replacement ->
      assert (B.unpack (Candidate.replaceAll c (B.literal replacement) subject) ==
              B.unpack (Reference.replaceAll r (B.literal replacement) subject))
        ("replacement disagreement: " ++ context ++ " replacement=" ++ show replacement)

-- Kept outside the small Cartesian corpus so long adversarial subjects do not
-- multiply every unrelated nullable expression. Every offset and public
-- operation is still checked for each pair. Repeated suffixes defeat the skip
-- heuristic, exercising its bounded-work handoff to the forward automaton.
adversarialPairs :: [(String, String)]
adversarialPairs =
  [("baaaaaaa", replicate 200 'a' ++ "baaaaaaa"),
   ("baaaaaaa", replicate 200 'a'),
   ("aaaaaaab|aaaaaaac", replicate 200 'a' ++ "c"),
   ("aaaaaaab|aaaaaaac", replicate 200 'a' ++ "b" ++ replicate 8 'a' ++ "c"),
   ("aba|bab", concat (replicate 100 "ab") ++ "a"),
   ("abab|baba", concat (replicate 100 "ab") ++ "aba"),
   ("a[ab]ba|[ab]abb", concat (replicate 50 "aabb")),
   ("ab|ca", concat (replicate 70 "cab")),
   ("baaaaaaa", concat (replicate 100 "α😀") ++ "baaaaaaa"),
   ("aba", "a😀aba"),
   ("\0a", "b\0ab"),
   ("\0a", replicate 200 'b' ++ "\0a"),
   ("\127x|a\0", "α\127xa\0"),
   ('b' : replicate 63 'a', replicate 300 'a' ++ "b" ++ replicate 63 'a'),
   (replicate 65 'a', replicate 66 'a'),
   ("[ab]aaaaaa|baaaaab", replicate 200 'a' ++ "baaaaab"),
   ("baaaaaaa|caaaaaaa", replicate 200 'a' ++ "caaaaaaa"),
   ("baaaaaaa|caaaaaaa", replicate 200 'a' ++ "baaaaaaacaaaaaaa")]

expectedFind :: [(String, String, Integer, Maybe (Integer, Integer))]
expectedFind =
  [("ab|a", "ab", 0, Just (0,2)), ("a|ab", "ab", 0, Just (0,1)),
   ("aa|bb", "baabb", 0, Just (1,3)), ("ab|ba", "ababa", 1, Just (1,3)),
   ("[α-ω]😀|ab", "xβ😀ab", 0, Just (1,3)),
   ("a.*z|b", "a--b--z", 0, Just (0,7)),
   ("a.*z|b", "a--b--", 0, Just (3,4)),
   ("a*ab", "aaaab", 0, Just (0,5)), ("a{2,4}", "aaaaa", 0, Just (0,4)),
   ("<[^>]*>", "x<a><b>z", 0, Just (1,4)),
   ("a.*b", "xab--b!", 0, Just (1,6)),
   ("a[^b]*b", "xab--b!", 0, Just (1,3)),
   ("a[^a]*a", "abaaca", 0, Just (0,3)),
   ("\\|[^|][^|]*\\|", "||a|bc|", 0, Just (1,4)),
   ("(|a)*", "aaa", 0, Just (0,0)), ("(a?|b)*", "b", 0, Just (0,0)),
   ("(^|.)*", "a", 0, Just (0,0)), ("(a?|.)*", "ab", 0, Just (0,1)),
   ("^b", "ab", 1, Nothing), ("$", "α😀", 2, Just (2,2)),
   ("$", "ab", 3, Nothing), ("a", "a", -1, Nothing),
   (".", "\n", 0, Nothing), (".", "\0", 0, Just (0,1)),
   ("😀a", "x😀a", 0, Just (1,3)),
   ("a[ac]*b", "aaacXab", 0, Just (5,7)),
   ("aa+b", "abaab", 0, Just (2,5)),
   ("a[cd]+b|x", "ax", 0, Just (1,2)),
   ("a[^b]*b|c", "ac", 0, Just (1,2)),
   ("α[^ω]*ω", "ααβ", 0, Nothing),
   ("a[^b]*b", "aaaa", 0, Nothing),
   ("baaaaaaa", replicate 200 'a' ++ "baaaaaaa", 0, Just (200,208)),
   ("baaaaaaa", replicate 200 'a', 0, Nothing),
   ("aaaaaaab|aaaaaaac", replicate 200 'a' ++ "c", 0, Just (193,201)),
   ("baaaaaaa", concat (replicate 100 "α😀") ++ "baaaaaaa", 0, Just (200,208)),
   ("\0a", "b\0ab", 0, Just (1,3)),
   ('b' : replicate 63 'a', replicate 300 'a' ++ "b" ++ replicate 63 'a', 0, Just (300,364)),
   (replicate 65 'a', replicate 66 'a', 0, Just (0,65)),
   ("aba|bab", "abababa", 1, Just (1,4)),
   ("ab|ca", "cabcab", 0, Just (0,2)),
   ("\127x|a\0", "α\127xa\0", 0, Just (1,3))]

expectedCount :: [(String, String, Integer)]
expectedCount = [("aa", "aaaaa", 2), ("", "α😀", 3), ("a*", "aaa", 2),
  ("ab|ba", "ababa", 2), ("😀|α", "😀aα😀", 3),
  ("baaaaaaa", replicate 200 'a' ++ "baaaaaaabaaaaaaa", 2),
  ("aaaaaaab|aaaaaaac", replicate 200 'a' ++ "c" ++ replicate 200 'a' ++ "b", 2),
  ("aba|bab", concat (replicate 100 "ab") ++ "a", 67),
  ("\0a", "b\0ab\0a", 2)]

expectedReplace :: [(String, String, String, String)]
expectedReplace =
  [("", "-", "α😀", "-α-😀-"), ("a*", "x", "aaa", "xx"),
   ("a|ab", "x", "abab", "xbxb"), ("a+", "$1\\tail", "caaad", "c$1\\taild"),
   (">[^\n]*\n|\n", "", ">ONE\nAC\nGT\n>TWO\nTA\n", "ACGTTA"),
   ("<[^>]*>", "|", "<a><b>!", "||!"),
   ("baaaaaaa", "X", replicate 200 'a' ++ "baaaaaaabaaaaaaa", replicate 200 'a' ++ "XX"),
   ("aba|bab", "X", concat (replicate 100 "ab") ++ "a", replicate 67 'X'),
   ("\0a", "X", "b\0ab\0a", "bXbX"),
   ("ab", "", "αab😀abZ", "α😀Z"),
   ("a[cd]+b|x", "Q", "aaxacdbxxadb", "aaQQQQQ"),
   ("a[cd]+b", "X", "aabacXacdbZ", "aabacXXZ"),
   ("α[^ω]*ω", "", "xα😀ωyαβωzαbad", "xyzαbad"),
   ("<[^>]*>", "|", "u<a>v<unfinished", "u|v<unfinished"),
   ("a[cd]+b|x", "", "xaXx", "aX"),
   ("\\|[^|][^|]*\\|", "-", "||a|bc|", "|-bc|"),
   ("a[b]*[cd]", "X", "uabbcvabbdZ", "uXvXZ"),
   ("a[b]*[^b]", "Q", "abb😀aX", "QQ"),
   ("a[b]*[\0c]", "N", "a\0abc", "NN"),
   ("a[^😀]*😀", "|", "αaβ😀xa😀", "α|x|")]

invalidPatterns :: [String]
invalidPatterns = ["[", "(", "a)", "*a", "a**", "a+?", "[z-a]", "[]", "\\",
  "\\1", "\\b", "(?=a)", "a{2,1}", "a{1001}", "a{1,x}", "[\\d-z]",
  "(a{1000}){1000}", "((){1000}){1000}"]

-- The build driver exposes these constructors in a copied test-only module.
-- Behavioral agreement is insufficient if every optimization silently falls
-- back: require both accelerated routes and conservative exclusions explicitly.
planName :: Candidate.Regex -> String
planName (Candidate.Regex _ _ plan) = case plan of
  Candidate.GeneralPlan -> "general"
  Candidate.FixedPlan _ _ -> "fixed"
  Candidate.SkipPlan _ _ _ _ -> "skip"
  Candidate.SpanPlan _ _ -> "span"

expectedPlans :: [(String, String)]
expectedPlans =
  [("a|b", "fixed"), ("ab|cd", "skip"), ("[ab]cd|xyz", "skip"),
   (">.*\n|\n", "span"), ("<[^>]*>", "span"), ("\\|[^|][^|]*\\|", "span"),
   ("a|ab", "general"), ("(a?)*", "general"), ("a*a", "general"),
   ("a.*b|c", "general"), ("[α-ω]x", "general"),
   ("a[ac]*b", "span"), ("aa+b", "span"), ("a[cd]+b|x", "span"),
   ("a[^b]*b|c", "general"),
   ("baaaaaaa", "skip"), ("aaaaaaab|aaaaaaac", "skip"), ("\0a", "skip"),
   ('b' : replicate 63 'a', "skip"), (replicate 65 'a', "general")]

-- Throw explicit ErrorCall values without a source-location suffix, so error
-- precedence has an exact oracle rather than a substring or reference-only
-- comparison. These are public demand contracts, independent of plan shape.
bottom :: String -> a
bottom message = Exception.throw (Exception.ErrorCall message)

observeDemand :: Bool -> IO (Either String Bool)
observeDemand value = do
  result <- Exception.try (Exception.evaluate value)
  case result of
    Left (exception :: Exception.ErrorCall) -> pure (Left (Exception.displayException exception))
    Right answer -> pure (Right answer)

demandCases :: [(String, Either String Bool, Bool, Bool)]
demandCases =
  [("count both bottoms", Left "subject-first",
    Candidate.countMatches (bottom "regex-second") (bottom "subject-first") == 0,
    Reference.countMatches (bottom "regex-second") (bottom "subject-first") == 0),
   ("count empty subject", Left "regex-required",
    Candidate.countMatches (bottom "regex-required") (B.literal "") == 0,
    Reference.countMatches (bottom "regex-required") (B.literal "") == 0),
   ("find negative offset", Right True,
    pair (Candidate.find (bottom "unused-regex") (bottom "unused-subject") (-1)) == Nothing,
    pair (Reference.find (bottom "unused-regex") (bottom "unused-subject") (-1)) == Nothing),
   ("find past-end offset", Right True,
    pair (Candidate.find (bottom "unused-regex") (B.literal "abc") 4) == Nothing,
    pair (Reference.find (bottom "unused-regex") (B.literal "abc") 4) == Nothing),
   ("find both bottoms", Left "subject-first",
    pair (Candidate.find (bottom "regex-second") (bottom "subject-first") 0) == Nothing,
    pair (Reference.find (bottom "regex-second") (bottom "subject-first") 0) == Nothing),
   ("replace all bottoms", Left "subject-first",
    B.unpack (Candidate.replaceAll (bottom "regex-second") (bottom "replacement-third")
      (bottom "subject-first")) == "",
    B.unpack (Reference.replaceAll (bottom "regex-second") (bottom "replacement-third")
      (bottom "subject-first")) == ""),
   ("unused replacement on empty subject", Right True,
    B.unpack (Candidate.replaceAll (candidate "a") (bottom "unused-replacement") (B.literal "")) == "",
    B.unpack (Reference.replaceAll (reference "a") (bottom "unused-replacement") (B.literal "")) == ""),
   ("unused replacement on nonempty subject", Right True,
    B.unpack (Candidate.replaceAll (candidate "a") (bottom "unused-replacement") (B.literal "xyz")) == "xyz",
    B.unpack (Reference.replaceAll (reference "a") (bottom "unused-replacement") (B.literal "xyz")) == "xyz"),
   ("regex before replacement", Left "regex-first",
    B.unpack (Candidate.replaceAll (bottom "regex-first") (bottom "replacement-second") (B.literal "a")) == "",
    B.unpack (Reference.replaceAll (bottom "regex-first") (bottom "replacement-second") (B.literal "a")) == ""),
   ("fixed match requires replacement", Left "replacement-required",
    B.unpack (Candidate.replaceAll (candidate "a") (bottom "replacement-required") (B.literal "a😀a")) == "",
    B.unpack (Reference.replaceAll (reference "a") (bottom "replacement-required") (B.literal "a😀a")) == ""),
   ("terminal nullable match requires replacement", Left "replacement-required",
    B.unpack (Candidate.replaceAll (candidate "") (bottom "replacement-required") (B.literal "")) == "",
    B.unpack (Reference.replaceAll (reference "") (bottom "replacement-required") (B.literal "")) == ""),
   ("Unicode span matches require replacement", Left "replacement-required",
    B.unpack (Candidate.replaceAll (candidate "<[^>]*>") (bottom "replacement-required")
      (B.literal "α<x>😀<y>")) == "",
    B.unpack (Reference.replaceAll (reference "<[^>]*>") (bottom "replacement-required")
      (B.literal "α<x>😀<y>")) == ""),
   ("skip match requires replacement", Left "replacement-required",
    B.unpack (Candidate.replaceAll (candidate "ab") (bottom "replacement-required") (B.literal "xaby")) == "",
    B.unpack (Reference.replaceAll (reference "ab") (bottom "replacement-required") (B.literal "xaby")) == ""),
   ("skip empty subject leaves replacement unused", Right True,
    B.unpack (Candidate.replaceAll (candidate "ab") (bottom "unused-replacement") (B.literal "")) == "",
    B.unpack (Reference.replaceAll (reference "ab") (bottom "unused-replacement") (B.literal "")) == ""),
   ("skip short subject leaves replacement unused", Right True,
    B.unpack (Candidate.replaceAll (candidate "ab") (bottom "unused-replacement") (B.literal "a")) == "a",
    B.unpack (Reference.replaceAll (reference "ab") (bottom "unused-replacement") (B.literal "a")) == "a"),
   ("unclosed span leaves replacement unused", Right True,
    B.unpack (Candidate.replaceAll (candidate "<[^>]*>") (bottom "unused-replacement") (B.literal "α<unfinished")) == "α<unfinished",
    B.unpack (Reference.replaceAll (reference "<[^>]*>") (bottom "unused-replacement") (B.literal "α<unfinished")) == "α<unfinished"),
   ("span minimum rejection leaves replacement unused", Right True,
    B.unpack (Candidate.replaceAll (candidate "a[cd]+b") (bottom "unused-replacement") (B.literal "ab")) == "ab",
    B.unpack (Reference.replaceAll (reference "a[cd]+b") (bottom "unused-replacement") (B.literal "ab")) == "ab")]

-- Synthetic transition tables isolate scheduler demand from regex admission
-- and matching. The reference predates these private functions; each result
-- and first-error marker below is therefore an independent literal oracle.
internalSchedulingCases :: [(String, Either String Bool, Bool)]
internalSchedulingCases =
  [("scan width first", Left "width-first",
    Candidate.scanSkip (bottom "width-first") unusedForward dead (bottom "shifts-third")
      subject 1 0 (bottom "credit-second") == 0),
   ("scan credit before shifts", Left "credit-first",
    Candidate.scanSkip 8 unusedForward dead (bottom "shifts-second")
      subject 1 0 (bottom "credit-first") == 0),
   ("scan shifts required", Left "shifts-required",
    Candidate.scanSkip 8 unusedForward dead (bottom "shifts-required") subject 1 0 16 == 0),
   ("scan empty ignores operands", Right True,
    Candidate.scanSkip (bottom "unused-width") unusedForward (bottom "unused-backward")
      (bottom "unused-shifts") (bottom "unused-subject") 0 0 (bottom "unused-credit") == (-1)),
   ("scan immediate acceptance ignores operands", Right True,
    Candidate.scanSkip (bottom "unused-width") unusedForward accept (bottom "unused-shifts")
      subject 1 0 (bottom "unused-credit") == 1),
   ("count width first", Left "width-first",
    Candidate.countSkip (bottom "width-first") unusedForward dead (bottom "shifts-third")
      subject 1 0 (bottom "credit-second") 73 == 0),
   ("count credit before shifts", Left "credit-first",
    Candidate.countSkip 8 unusedForward dead (bottom "shifts-second")
      subject 1 0 (bottom "credit-first") 73 == 0),
   ("count shifts required", Left "shifts-required",
    Candidate.countSkip 8 unusedForward dead (bottom "shifts-required") subject 1 0 16 73 == 0),
   ("count empty ignores operands", Right True,
    Candidate.countSkip (bottom "unused-width") unusedForward (bottom "unused-backward")
      (bottom "unused-shifts") (bottom "unused-subject") 0 0 (bottom "unused-credit") 73 == 73),
   ("count match ignores incoming credit and shifts", Right True,
    Candidate.countSkip 1 unusedForward accept (bottom "unused-shifts")
      subject 1 0 (bottom "unused-credit") 73 == 74),
   ("count match count before next offset width", Left "count-first",
    Candidate.countSkip (bottom "width-second") unusedForward accept (bottom "unused-shifts")
      subject 1 0 (bottom "unused-credit") (bottom "count-first") == 0),
   ("count match requires next offset width", Left "width-required",
    Candidate.countSkip (bottom "width-required") unusedForward accept (bottom "unused-shifts")
      subject 1 0 (bottom "unused-credit") 73 == 0)]
  where
    subject = B.literal "a"
    dead = B.literal (replicate 256 '\1')
    accept = B.literal (replicate 256 '\0')
    unusedForward = bottom "unused-forward"

main :: IO ()
main = do
  forM_ expectedPlans $ \(patternText, expected) ->
    assert (planName (candidate patternText) == expected)
      ("plan admission oracle: " ++ show (patternText, expected))
  putStrLn ("PASS plan-admission " ++ show (length expectedPlans))
  forM_ expectedFind $ \(patternText, subject, offset, expected) ->
    assert (pair (Candidate.find (candidate patternText) (B.literal subject) offset) == expected)
      ("literal find oracle: " ++ show (patternText, subject, offset, expected))
  forM_ expectedCount $ \(patternText, subject, expected) ->
    assert (Candidate.countMatches (candidate patternText) (B.literal subject) == expected)
      ("literal count oracle: " ++ show (patternText, subject, expected))
  forM_ expectedReplace $ \(patternText, replacement, subject, expected) ->
    assert (B.unpack (Candidate.replaceAll (candidate patternText) (B.literal replacement) (B.literal subject)) == expected)
      ("literal replacement oracle: " ++ show (patternText, replacement, subject, expected))
  putStrLn ("PASS literal-oracles " ++ show (length expectedFind + length expectedCount + length expectedReplace))
  forM_ invalidPatterns $ \patternText ->
    case (Candidate.compile (B.literal patternText), Reference.compile (B.literal patternText)) of
      (T.Left c, T.Left r) -> assert (B.unpack c == B.unpack r && not (null (B.unpack c)))
        ("compile diagnostic disagreement: " ++ show patternText)
      _ -> error ("invalid regex was accepted: " ++ show patternText)
  putStrLn ("PASS invalid-patterns " ++ show (length invalidPatterns))
  forM_ demandCases $ \(label, expected, candidateValue, referenceValue) -> do
    forM_ [("candidate", candidateValue), ("reference", referenceValue)] $ \(engine, value) -> do
      actual <- observeDemand value
      assert (actual == expected)
        ("demand oracle: " ++ label ++ " engine=" ++ engine ++
          " expected=" ++ show expected ++ " actual=" ++ show actual)
  putStrLn ("PASS demand-oracles " ++ show (length demandCases))
  forM_ internalSchedulingCases $ \(label, expected, value) -> do
    actual <- observeDemand value
    assert (actual == expected)
      ("internal scheduling oracle: " ++ label ++
        " expected=" ++ show expected ++ " actual=" ++ show actual)
  putStrLn ("PASS internal-scheduling " ++ show (length internalSchedulingCases))
  forM_ patterns checkPair
  putStrLn ("PASS differential-patterns " ++ show (length patterns))
  putStrLn ("PASS differential-subjects " ++ show (length subjects))
  putStrLn ("PASS differential-pairs " ++ show (length patterns * length subjects))
  forM_ adversarialPairs $ \(patternText, subject) -> checkSubjects patternText [subject]
  putStrLn ("PASS adversarial-pairs " ++ show (length adversarialPairs))
  putStrLn "Regex fast-path semantic audit passed"
