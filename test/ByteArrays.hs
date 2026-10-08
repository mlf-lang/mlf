module ByteArrays (byteArrayTests) where

import Control.Monad (forM_, unless)
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as ASCII
import Data.List (isInfixOf)
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.Primitive as P
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO X.Term
checked source = do
  term <- compiledTerm <$> right (compile "<byte-array test>" source)
  parsed <- right (XP.parseTerm "<byte-array xMLF>" (prettyTerm term))
  unless (X.erase term == X.erase parsed) (fail "byte-array round trip changed erasure")
  pure parsed

byteArrayTests :: Backends -> [(String,IO ())]
byteArrayTests backends =
  [("bytes: " ++ label, do
      term <- checked source
      result <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome result)
      unless (B.outputBytes result == expected) (fail (show result))) | (label,source,expected) <- programs] ++
  [("byte failure: " ++ label, do
      term <- checked ("do { putStrLn \"before\"; " ++ source ++ " }")
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | message `isInfixOf` show err && B.output result == "before\n" -> pure ()
        _ -> fail (show result)) | (label,source,message) <- failures] ++
  [ ("bytes: native loop emits every byte without Unicode conversion", do
      term <- checked (recursion ++ "let fill : ByteArray -> Int -> IO Unit = fix (\\again a i -> " ++
        "ifThenElse (ltInt i 256) (do { writeByteArray a i i; again a (addInt i 1) }) (return ())) in " ++
        "do { a <- newByteArray 256 0; fill a 0; putBytes a 0 256 }")
      llvm <- right (emitLLVMIO term)
      unless ("define private ptr @mlf.numeric." `isInfixOf` llvm && "store i8" `isInfixOf` llvm)
        (fail "byte loop did not use native byte storage")
      result <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome result)
      unless (B.outputBytes result == BS.pack [0..255]) (fail (show result)))
  , ("bytes: bulk copy preserves offsets, empty ranges and forward overlap", do
      let copy = recursion ++ "let move : ByteArray -> ByteArray -> Int -> Int -> Int -> IO Unit = " ++
            "fix (\\again source dest end offset index -> ifThenElse (ltInt index end) " ++
            "(do { b <- readByteArray source index; writeByteArray dest (addInt offset index) b; " ++
            "again source dest end offset (addInt index 1) }) (return ())) in "
          cases = [(False,6,2,1,"012bcdef89"),(True,5,1,0,"aaaaaa"),
                   (True,6,0,0,"abcdef"),(True,6,-2,2,"cdefef"),
                   (False,2,2^(100::Int),99,"0123456789"),(False,0,0,0,"0123456789")]
      forM_ cases $ \(alias,end,offset,start,expected) -> do
        term <- checked (copy ++ "do { a <- byteArrayFromString \"abcdef\"; b <- " ++
          (if alias then "return a" else "byteArrayFromString \"0123456789\"") ++
          "; move a b " ++ show (end::Integer) ++ " (" ++ show (offset::Integer) ++ ") (" ++ show (start::Integer) ++
          "); move a b 0 0 0; n <- lengthByteArray b; putBytes b 0 n }")
        llvm <- right (emitLLVMIO term)
        unless ("call void @llvm.memmove" `isInfixOf` llvm) (fail "copy idiom was not exercised")
        result <- B.execute backends IOEntry (Input "" False) term
        right (B.outcome result)
        unless (B.output result == expected) (fail (show result)))
  , ("bytes: bulk copy fallback retains bounds failures", forM_
      [(7,0,0),(3,5,0),(3,0,-1),(2^(100::Int),0,0)] $ \(end,offset,start) -> do
      term <- checked (recursion ++ "let move : ByteArray -> ByteArray -> Int -> Int -> Int -> IO Unit = " ++
        "fix (\\again source dest end offset index -> ifThenElse (ltInt index end) " ++
        "(do { b <- readByteArray source index; writeByteArray dest (addInt offset index) b; " ++
        "again source dest end offset (addInt index 1) }) (return ())) in " ++
        "do { a <- byteArrayFromString \"abcdef\"; move a a 0 0 0; putStrLn \"before\"; " ++
        "move a a " ++ show (end::Integer) ++ " (" ++ show (offset::Integer) ++ ") (" ++ show (start::Integer) ++ ") }")
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | "array index out of bounds" `isInfixOf` show err && B.output result == "before\n" -> pure ()
        _ -> fail (show result))
  , ("bytes: native stores check bounds before byte range", forM_
      [(0,256,"byte value must be between 0 and 255"),
       (0,-1,"byte value must be between 0 and 255"),
       (0,4611686018427387904,"byte value must be between 0 and 255"),
       (0,-4611686018427387905,"byte value must be between 0 and 255"),
       (1,256,"array index out of bounds"),(2147483647,256,"array index out of bounds"),
       (2147483648,256,"array index out of bounds"),
       (4611686018427387904,256,"array index out of bounds")] $ \(index,value,message) -> do
      term <- checked (recursion ++ "let write : ByteArray -> Int -> Int -> Int -> IO Unit = " ++
        "fix (\\again a i x n -> ifThenElse (eqInt n 0) (return ()) " ++
        "(do { writeByteArray a i x; again a i x (subInt n 1) })) in " ++
        "do { a <- newByteArray 1 0; putStrLn \"before\"; write a " ++
        show (index::Integer) ++ " (" ++ show (value::Integer) ++ ") 1 }")
      llvm <- right (emitLLVMIO term)
      unless ("define private ptr @mlf.numeric." `isInfixOf` llvm && "store i8" `isInfixOf` llvm)
        (fail "byte failure did not exercise native storage")
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | message `isInfixOf` show err && B.output result == "before\n" -> pure ()
        _ -> fail (show result))
  , ("bytes: write failures stop continuation and preserve raw output", do
      term <- checked "do { a <- newByteArray 2 255; putBytes a 0 2; getLine; return () }"
      result <- B.execute backends IOEntry (Input "unused\n" True) term
      case B.outcome result of
        Left err | show err == "IO error: write failed" && B.outputBytes result == BS.pack [255,255]
          && B.remaining result == "unused\n" -> pure ()
        _ -> fail (show result))
  , ("bytes: nominal types reject invalid operations", forM_
      [ "data ByteArray = Forged; Forged", "newByteArray 1 1.0"
      , "do { a <- newIntArray 1 0; readByteArray a 0 }"
      , "do { a <- newByteArray 1 0; writeByteArray a 0 true }"
      , "putBytes \"text\" 0 1", "byteArrayFromString 42"
      , "do { a <- newByteArray 1 0; printInt (readByteArray a 0) }"
      ] $ \source -> case compile "<invalid bytes>" source of
        Left _ -> pure (); Right _ -> fail ("accepted " ++ source))
  , ("bytes: forged surrogate is rejected before encoding by both backends", do
      let term = X.App (X.Primitive P.IOReturn [T.Con "String" []]) (X.StringTerm ['\xd800'])
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | "invalid Unicode scalar" `isInfixOf` show err && null (B.events result) -> pure ()
        _ -> fail (show result))
  , ("numeric region: integer-to-Double conversion preserves rounding", do
      term <- checked (recursion ++ "let convert : IntArray -> DoubleArray -> Int -> IO Unit = fix (\\again a b n -> " ++
        "ifThenElse (eqInt n 0) (return ()) (do { x <- readIntArray a 0; " ++
        "writeDoubleArray b 0 (intToDouble x); again a b (subInt n 1) })) in " ++
        "do { a <- newIntArray 1 9007199254740995; b <- newDoubleArray 1 0.0; convert a b 1; " ++
        "x <- readDoubleArray b 0; putStrLn (formatDouble 0 x); " ++
        "writeIntArray a 0 (-4611686018427388672); convert a b 1; y <- readDoubleArray b 0; " ++
        "putStrLn (formatDouble 0 y); writeIntArray a 0 " ++ show (10^(400::Int)::Integer) ++
        "; convert a b 1; z <- readDoubleArray b 0; putStrLn (formatDouble 0 z) }")
      llvm <- right (emitLLVMIO term)
      unless ("sitofp i64" `isInfixOf` llvm) (fail "conversion did not enter native numeric code")
      result <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome result)
      unless (B.output result == "9007199254740996\n-4611686018427388928\nInfinity\n") (fail (show result)))
  , ("bytes: fasta empty, single-base and upstream fixture", do
      term <- readFile "benchmarks/fasta/mlf/main.emlf" >>= checked
      fixture <- BS.readFile "benchmarks/fasta/expected-1000.txt"
      forM_ [(0,ASCII.pack ">ONE Homo sapiens alu\n>TWO IUB ambiguity codes\n>THREE Homo sapiens frequency\n"),
             (1,ASCII.pack ">ONE Homo sapiens alu\nGG\n>TWO IUB ambiguity codes\nctt\n>THREE Homo sapiens frequency\ntgagc\n"),
             (1000,fixture)] $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n::Int) ++ "\n") False) term
        right (B.outcome result)
        unless (B.outputBytes result == expected && null (B.remaining result)) (fail (show result)))
  , ("bytes: mandelbrot packed pixels, partial rows and upstream fixture", do
      term <- readFile "benchmarks/mandelbrot/mlf/main.emlf" >>= checked
      fixture <- BS.readFile "benchmarks/mandelbrot/expected-200.pbm"
      let small = [(1,[0]), (2,[0,192]), (7,[0,4,30,126,126,30,4]),
                   (8,[2,0,15,47,255,47,15,0]),
                   (9,[0,0,2,0,7,128,15,128,63,128,63,128,15,128,7,128,2,0])]
          samples = [(n,ASCII.pack ("P4\n" ++ show n ++ " " ++ show n ++ "\n") <> BS.pack pixels)
                    | (n,pixels) <- small] ++ [(200,fixture)]
      forM_ samples $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n::Int) ++ "\n") False) term
        right (B.outcome result)
        unless (B.outputBytes result == expected && null (B.remaining result)) (fail (show result)))
  ]

programs :: [(String,String,BS.ByteString)]
programs =
  [ ("raw high bytes, NUL and text retain order",
      "do { a <- newByteArray 4 0; writeByteArray a 1 127; writeByteArray a 2 128; writeByteArray a 3 255; " ++
      "putStr \"A\"; putBytes a 0 4; putStrLn \"Z\" }", BS.pack [65,0,127,128,255,90,10])
  , ("UTF-8 source strings produce byte lengths and fresh mutable buffers",
      "let new = byteArrayFromString \"λ😀\\0\" in do { a <- new; b <- new; n <- lengthByteArray a; " ++
      "printInt n; writeByteArray a 0 65; putBytes b 0 n; putBytes a 0 1 }",
      BS.pack [55,10,206,187,240,159,152,128,0,65])
  , ("shared reads are snapshots and shared outputs read current contents",
      "do { a <- newByteArray 2 65; let read = readByteArray a 0; let write = putBytes a 0 2; " ++
      "x <- read; write; writeByteArray a 0 255; y <- read; write; printInt x; printInt y }",
      BS.pack [65,65,255,65] <> ASCII.pack "65\n255\n")
  , ("generic primitive applications preserve slicing",
      "do { new <- return newByteArray; write <- return writeByteArray; read <- return readByteArray; " ++
      "len <- return lengthByteArray; from <- return byteArrayFromString; put <- return putBytes; " ++
      "a <- new 3 65; write a 1 255; x <- read a 1; n <- len a; b <- from \"BC\"; " ++
      "put a 1 2; put b 0 2; printInt x; printInt n }", BS.pack [255,65,66,67] <> ASCII.pack "255\n3\n")
  , ("empty slices and unused failing actions remain lazy",
      "do { a <- newByteArray 0 0; putBytes a 0 0; let bad = putBytes a (-1) (quotInt 1 0); " ++
      "return bad; b <- byteArrayFromString \"ab\"; putBytes b 2 0; putBytes b 1 1 }", ASCII.pack "b")
  , ("byte buffers and pending slices survive collection",
      recursion ++ "let churn : Int -> IO Unit = fix (\\again n -> ifThenElse (eqInt n 0) (return ()) " ++
      "(do { ignored <- newByteArray 100 255; again (subInt n 1) })) in " ++
      "do { a <- byteArrayFromString \"retained\"; let action = putBytes a 0 8; churn 300; action }", ASCII.pack "retained")
  ]

failures :: [(String,String,String)]
failures =
  [ ("negative length", "newByteArray (-1) 0", "invalid array length")
  , ("huge length", "newByteArray 999999999999999999999 0", "invalid array length")
  , ("negative initial value", "newByteArray 1 (-1)", "byte value must be between 0 and 255")
  , ("initial value outside byte", "newByteArray 0 256", "byte value must be between 0 and 255")
  , ("huge write value", "do { a <- newByteArray 1 0; writeByteArray a 0 999999999999999999999 }", "byte value must be between 0 and 255")
  , ("negative write value", "do { a <- newByteArray 1 0; writeByteArray a 0 (-1) }", "byte value must be between 0 and 255")
  , ("negative read", "do { a <- newByteArray 1 0; readByteArray a (-1) }", "array index out of bounds")
  , ("GMP index", "do { a <- newByteArray 1 0; readByteArray a 4611686018427387904 }", "array index out of bounds")
  , ("write checks bounds before value", "do { a <- newByteArray 1 0; writeByteArray a 1 (quotInt 1 0) }", "array index out of bounds")
  , ("empty array still demands index", "do { a <- newByteArray 0 0; readByteArray a (quotInt 1 0) }", "integer division by zero")
  , ("negative slice", "do { a <- newByteArray 1 0; putBytes a (-1) 0 }", "byte slice out of bounds")
  , ("negative count", "do { a <- newByteArray 1 0; putBytes a 0 (-1) }", "byte slice out of bounds")
  , ("slice past end", "do { a <- newByteArray 2 0; putBytes a 1 2 }", "byte slice out of bounds")
  , ("huge count", "do { a <- newByteArray 2 0; putBytes a 0 999999999999999999999 }", "byte slice out of bounds")
  , ("offset checked before count", "do { a <- newByteArray 1 0; putBytes a 2 (quotInt 1 0) }", "byte slice out of bounds")
  , ("write demands value", "do { a <- newByteArray 1 0; writeByteArray a 0 (quotInt 1 0) }", "integer division by zero")
  ]

recursion :: String
recursion = "data Rec a = Rec (Rec a -> a); let fix : forall a. (a -> a) -> a = \\f -> " ++
  "let go = \\r -> case r of { Rec next -> f (next r) } in go (Rec go) in "
