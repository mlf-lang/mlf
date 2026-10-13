module DNA (dnaTests) where

import Control.Monad (forM_, unless)
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as ASCII
import Data.List (isInfixOf)
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO X.Term
checked source = do
  term <- compiledTerm <$> right (compile "<DNA test>" source)
  parsed <- right (XP.parseTerm "<DNA xMLF>" (prettyTerm term))
  unless (X.erase term == X.erase parsed) (fail "DNA round trip changed erasure")
  pure parsed

run :: Backends -> String -> Input -> BS.ByteString -> String -> IO ()
run backends source input expected unused = do
  term <- checked source
  result <- B.execute backends IOEntry input term
  right (B.outcome result)
  unless (B.outputBytes result == expected && B.remaining result == unused) (fail (show result))

dnaTests :: Backends -> [(String,IO ())]
dnaTests backends =
  [ ("byte input: raw bytes, blank lines, final line and repeated EOF", do
      let source = recursion ++ "let echo : Int -> IO Unit = fix (\\again n -> ifThenElse (eqInt n 0) (return ()) " ++
            "(do { line <- getByteLine; count <- lengthByteArray line; printInt count; " ++
            "putBytes line 0 count; again (subInt n 1) })) in echo 5"
          bytes = BS.pack [0,128,255,10,10,65]
      run backends source (RawInput bytes False)
        (ASCII.pack "4\n" <> BS.pack [0,128,255,10] <> ASCII.pack "1\n\n1\nA0\n0\n") "")
  , ("byte input: shared reads execute again and mix with getLine", do
      let source = "let read = getByteLine in do { let unused = read; a <- read; " ++
            "b <- read; writeByteArray a 0 88; n <- lengthByteArray b; putBytes b 0 n; " ++
            "text <- getLine; putStrLn text }"
      run backends source (Input "first\nsecond\nλ😀\nunused\n" False)
        (BS.pack [115,101,99,111,110,100,10,206,187,240,159,152,128,10]) "unused\n")
  , ("byte input: long raw line grows without decoding", do
      let bytes = BS.pack (take 17000 (cycle [0,128,255,65])) <> ASCII.pack "\n"
      run backends "do { a <- getByteLine; n <- lengthByteArray a; putBytes a 0 n }"
        (RawInput (bytes <> ASCII.pack "tail") False) bytes "tail")
  , ("byte input: buffer boundaries preserve mixed reads and retained lines", forM_ [65535,65536,65537] $ \size -> do
      let first = BS.pack (take size (cycle [0,128,255,65])) <> ASCII.pack "\n"
          text = BS.pack [206,187,240,159,152,128,10]
          next = ASCII.pack "next\n"
      run backends
        "do { first <- getByteLine; text <- getLine; next <- getByteLine; putStrLn text; n <- lengthByteArray first; putBytes first 0 n; m <- lengthByteArray next; putBytes next 0 m }"
        (RawInput (first <> text <> next <> ASCII.pack "tail") False)
        (text <> first <> next) "tail")
  , ("byte input: discarded action does not consume input", run backends
      "do { return getByteLine; putStrLn \"ok\" }" (RawInput (BS.pack [255]) False) (ASCII.pack "ok\n") ['\255'])
  , ("byte input: invalid UTF-8 still fails for text input", do
      term <- checked "do { getLine; putStrLn \"unreachable\" }"
      result <- B.execute backends IOEntry (RawInput (BS.pack [255,10,65]) False) term
      case B.outcome result of
        Left err | show err == "IO error: invalid UTF-8 input" && B.remaining result == "A" -> pure ()
        _ -> fail (show result))
  , ("table: fresh actions, aliasing, overwrite and snapshot reads", run backends
      ("let make = newIntTable in do { a <- make; b <- make; let alias = a; " ++
       "let read = readIntTable a 7; x <- read; writeIntTable alias 7 23; y <- read; " ++
       "writeIntTable a 7 (-4); z <- read; other <- readIntTable b 7; " ++
       "printInt x; printInt y; printInt z; printInt other }")
      (Input "" False) (ASCII.pack "0\n23\n-4\n0\n") "")
  , ("table: generic applications and unbounded signed keys and values", run backends
      ("do { make <- return newIntTable; read <- return readIntTable; write <- return writeIntTable; t <- make; " ++
       "write t (-1) 123456789012345678901234567890; write t 4611686018427387904 12; " ++
       "write t (-4611686018427387905) 13; write t 999999999999999999999999999999 14; " ++
       "write t (-999999999999999999999999999999) 15; " ++
       "a <- read t (-1); b <- read t (addInt 4611686018427387903 1); " ++
       "c <- read t (subInt (-4611686018427387904) 1); " ++
       "d <- read t (subInt 1000000000000000000000000000000 1); " ++
       "e <- read t (-999999999999999999999999999999); f <- read t 0; " ++
       "printInt a; printInt b; printInt c; printInt d; printInt e; printInt f }")
      (Input "" False) (ASCII.pack "123456789012345678901234567890\n12\n13\n14\n15\n0\n") "")
  , ("table: native counting loop grows and updates collision-prone keys", do
      let source = recursion ++
            "let count : IntTable -> Int -> IO Unit = fix (\\again t n -> ifThenElse (eqInt n 0) (return ()) " ++
            "(do { let key = mulInt (remInt n 67) 4294967296; old <- readIntTable t key; " ++
            "writeIntTable t key (addInt old 1); again t (subInt n 1) })) in " ++
            "do { t <- newIntTable; count t 1000; x <- readIntTable t 0; " ++
            "y <- readIntTable t 4294967296; z <- readIntTable t 283467841536; printInt x; printInt y; printInt z }"
      term <- checked source
      llvm <- right (emitLLVMIO term)
      unless ("define private ptr @mlf.numeric." `isInfixOf` llvm && "call ptr @mlf_add_int_table" `isInfixOf` llvm)
        (fail "table loop did not use the native region")
      result <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome result)
      unless (B.output result == "14\n15\n14\n") (fail (show result)))
  , ("native IO: nested collections preserve caller values and prior results", do
      let source = recursion ++
            "let consume : ByteArray -> Int -> IO ByteArray = fix (\\again last n -> " ++
            "ifThenElse (eqInt n 0) (return last) (do { line <- getByteLine; again line (subInt n 1) })) in " ++
            "let read : Int -> IO ByteArray = \\n -> do { first <- getByteLine; " ++
            "last <- consume first n; count <- lengthByteArray first; putBytes first 0 count; return last } in " ++
            "do { a <- read 80; b <- read 80; " ++
            "na <- lengthByteArray a; nb <- lengthByteArray b; putBytes a 0 na; putBytes b 0 nb }"
          input = "first\n" ++ concat (replicate 79 "churn\n") ++ "last\n" ++
                  "second\n" ++ concat (replicate 79 "other\n") ++ "end\n"
      term <- checked source
      llvm <- right (emitLLVMIO term)
      unless (all (`isInfixOf` llvm) ["call void @mlf_gc_check", "call void @mlf_roots_enter"])
        (fail "fixture missed nested native collection")
      result <- B.execute backends IOEntry (Input input False) term
      right (B.outcome result)
      unless (B.output result == "first\nsecond\nlast\nend\n" && null (B.remaining result)) (fail (show result)))
  , ("table fusion: snapshots, large signed keys and promotion across updates", do
      let source = recursion ++
            "let update : IntTable -> IntArray -> Int -> Int -> IO Unit = \\t out key delta -> do { " ++
            "old <- readIntTable t key; writeIntTable t key (addInt old delta); writeIntArray out 0 old } in " ++
            "do { t <- newIntTable; out <- newIntArray 1 0; " ++
            "writeIntTable t (-999999999999999999999999) 4611686018427387903; " ++
            "update t out (-999999999999999999999999) 1; a <- readIntArray out 0; " ++
            "b <- readIntTable t (-999999999999999999999999); " ++
            "update t out (-999999999999999999999999) (-4611686018427387909); " ++
            "c <- readIntArray out 0; d <- readIntTable t (-999999999999999999999999); " ++
            "update t out 7 (-2); e <- readIntArray out 0; f <- readIntTable t 7; " ++
            "printInt a; printInt b; printInt c; printInt d; printInt e; printInt f }"
      term <- checked source
      llvm <- right (emitLLVMIO term)
      unless ("call ptr @mlf_add_int_table" `isInfixOf` llvm) (fail "fixture did not fuse the table update")
      result <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome result)
      unless (B.output result == "4611686018427387903\n4611686018427387904\n4611686018427387904\n-5\n0\n-2\n")
        (fail (show result)))
  , ("table fusion: intervening writes and unequal keys retain their order", run backends
      ("let update : IntTable -> Int -> Int -> IO Unit = \\t a b -> do { " ++
       "old <- readIntTable t a; writeIntTable t a 9; writeIntTable t b (addInt old 1) } in " ++
       "do { t <- newIntTable; writeIntTable t 1 3; update t 1 2; " ++
       "a <- readIntTable t 1; b <- readIntTable t 2; printInt a; printInt b }")
      (Input "" False) (ASCII.pack "9\n4\n") "")
  , ("table: GMP keys and values and pending IO survive collection", run backends
      (recursion ++ "let churn : Int -> IO Unit = fix (\\again n -> ifThenElse (eqInt n 0) (return ()) " ++
       "(do { t <- newIntTable; writeIntTable t n (mulInt n 999999999999999999999999); again (subInt n 1) })) in " ++
       "do { t <- newIntTable; writeIntTable t 99999999999999999999 88888888888888888888; " ++
       "let read = readIntTable t (addInt 99999999999999999998 1); churn 600; old <- read; " ++
       "writeIntTable t 99999999999999999999 42; churn 600; new <- read; printInt old; printInt new }")
      (Input "" False) (ASCII.pack "88888888888888888888\n42\n") "")
  , ("table: unused actions do not demand failing operands", run backends
      "do { t <- newIntTable; return (writeIntTable t (quotInt 1 0) (quotInt 2 0)); return (readIntTable t (quotInt 1 0)); printInt 7 }"
      (Input "" False) (ASCII.pack "7\n") "")
  , ("table: small keys retain GMP values through collection and promotion", run backends
      (recursion ++ "let churn : Int -> IO Unit = fix (\\again n -> ifThenElse (eqInt n 0) (return ()) " ++
       "(do { a <- newByteArray 1 0; again (subInt n 1) })) in " ++
       "let fill : IntTable -> Int -> IO Unit = fix (\\again t n -> ifThenElse (eqInt n 0) (return ()) " ++
       "(do { writeIntTable t n (addInt 99999999999999999999999 n); again t (subInt n 1) })) in " ++
       "let sum : IntTable -> Int -> Int -> IO Int = fix (\\again t n total -> ifThenElse (eqInt n 0) (return total) " ++
       "(do { x <- readIntTable t n; again t (subInt n 1) (addInt total x) })) in " ++
       "do { t <- newIntTable; fill t 100; churn 100; a <- sum t 100 0; " ++
       "writeIntTable t (-99999999999999999999999) 42; churn 100; b <- sum t 100 0; " ++
       "c <- readIntTable t (-99999999999999999999999); printInt a; printInt b; printInt c }")
      (Input "" False) (ASCII.pack "10000000000000000000004950\n10000000000000000000004950\n42\n") "")
  , ("table: demanded operands fail after preceding effects", forM_
      ["readIntTable t (quotInt 1 0)","writeIntTable t 0 (quotInt 1 0)",
       "writeIntTable t (quotInt 1 0) (readInt \"not an integer\")"] $ \operation -> do
      term <- checked ("do { t <- newIntTable; putStrLn \"before\"; " ++ operation ++ "; getByteLine }")
      result <- B.execute backends IOEntry (Input "unused\n" False) term
      case B.outcome result of
        Left err | "integer division by zero" `isInfixOf` show err && B.output result == "before\n"
          && B.remaining result == "unused\n" -> pure ()
        _ -> fail (show result))
  , ("table: nominal types and IO signatures are checked", forM_
      ["data IntTable = Forged; Forged", "do { t <- newIntTable; readByteArray t 0 }",
       "do { a <- newIntArray 1 0; readIntTable a 0 }", "do { t <- newIntTable; writeIntTable t 0 true }",
       "do { t <- newIntTable; readIntTable t 1.0 }", "getByteLine 1"] $ \source ->
      case compile "<invalid table>" source of
        Left _ -> pure (); Right _ -> fail ("accepted " ++ source))
  , ("DNA: reverse-complement ambiguity codes, records and growing buffers", do
      source <- readFile "benchmarks/reverse-complement/mlf/main.emlf"
      let cases = [("",""),(">empty\n",">empty\n"),
            (">id description\nacgtumrwsykvhdbn\n",">id description\nNVHDBMRSWYKAACGT\n"),
            (">a\nA\n>b\nCGT",">a\nT\n>b\nACG\n"),
            (">wide\n" ++ replicate 2100 'a' ++ "\n", ">wide\n" ++ concat (replicate 35 (replicate 60 'T' ++ "\n")))] ++
            [(">chunks\n" ++ replicate n 'a' ++ "\n", ">chunks\n" ++
              concat (replicate 1024 (replicate 60 'T' ++ "\n")) ++ if n == 61440 then "" else "T\n")
             | n <- [61440,61441]]
      forM_ cases $ \(input,expected) -> run backends source (Input input False) (ASCII.pack expected) "")
  , ("DNA: both upstream fixtures", forM_ ["reverse-complement","k-nucleotide"] $ \name -> do
      let path = "benchmarks/" ++ name ++ "/"
      source <- readFile (path ++ "mlf/main.emlf")
      input <- BS.readFile (path ++ "input-1000.txt")
      expected <- BS.readFile (path ++ "expected-1000.txt")
      run backends source (RawInput input False) expected "")
  , ("DNA: k-nucleotide short inputs, ties, mixed case and record termination", do
      source <- readFile "benchmarks/k-nucleotide/mlf/main.emlf"
      let zero = "0\tGGT\n0\tGGTA\n0\tGGTATT\n0\tGGTATTTTAATT\n0\tGGTATTTTAATTTATAGT\n"
      run backends source (Input ">ONE\nGGT\n>THREEISH\nGGT\n>THREE\naCgT\n>FOUR\nunused\n" False)
        (ASCII.pack ("A 25.000\nC 25.000\nG 25.000\nT 25.000\n\nAC 33.333\nCG 33.333\nGT 33.333\n\n" ++ zero)) "unused\n"
      run backends source (Input ">THREE\nA" False) (ASCII.pack ("A 100.000\n\n\n" ++ zero)) ""
      run backends source (Input ">THREE\n" False) (ASCII.pack ("\n\n" ++ zero)) "")
  ]

recursion :: String
recursion = "data Rec a = Rec (Rec a -> a); let fix : forall a. (a -> a) -> a = \\f -> " ++
  "let go = \\r -> case r of { Rec next -> f (next r) } in go (Rec go) in "
