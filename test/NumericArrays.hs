-- Exercise new arithmetic and state through the shared interpreter/LLVM
-- matrix, including serialization, generic application and forced collection.
module NumericArrays (numericArrayTests) where

import Control.Monad (forM_, unless)
import Data.List (group, isInfixOf, sort)
import Data.Bits ((.&.))
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO X.Term
checked source = do
  term <- compiledTerm <$> right (compile "<numeric/array test>" source)
  parsed <- right (XP.parseTerm "<numeric/array xMLF>" (prettyTerm term))
  unless (X.erase term == X.erase parsed) (fail "numeric/array serialization changed erasure")
  pure parsed

observe :: Backends -> X.Term -> String -> IO ()
observe backends term expected = do
  result <- B.execute backends IOEntry (Input "" False) term
  right (B.outcome result)
  unless (B.output result == expected) (fail (show result ++ "; expected " ++ show expected))

numericArrayTests :: Backends -> [(String,IO ())]
numericArrayTests backends =
  [("native scalar arguments: " ++ label, do
      term <- checked (recursion ++ source)
      llvm <- right (emitLLVMIO term)
      unless (any (\line -> "define private ptr @mlf.numeric." `isInfixOf` line &&
                    "double %a" `isInfixOf` line) (lines llvm))
        (fail "fixture did not exercise an unboxed Double worker")
      observe backends term expected) | (label,source,expected) <- scalarPrograms] ++
  [("native numeric region: " ++ label, do
      term <- checked (recursion ++ source)
      llvm <- right (emitLLVMIO term)
      unless ("define private ptr @mlf.numeric." `isInfixOf` llvm)
        (fail "fixture did not produce a native numeric region")
      result <- B.execute backends IOEntry (Input "" False) term
      case expected of
        Right output -> right (B.outcome result) >> unless (B.output result == output) (fail (show result))
        Left message -> case B.outcome result of
          Left err | message `isInfixOf` show err && B.output result == "before\n" -> pure ()
          _ -> fail (show result)) | (label,source,expected) <- regionPrograms] ++
  [("numeric: " ++ label, checked source >>= \term -> observe backends term expected)
    | (label,source,expected) <- programs] ++
  [("numeric failure: " ++ label, do
      term <- checked ("do { putStrLn \"before\"; " ++ source ++ " }")
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | message `isInfixOf` show err && B.output result == "before\n" -> pure ()
        _ -> fail (show result)) | (label,source,message) <- failures] ++
  [ ("native numeric region: multiplication and division retain arbitrary precision", do
      let limit = 2^(62 :: Int) :: Integer
          values = [-2^(100 :: Int),-limit-1,-limit,-3,0,3,limit-1,limit,2^(100 :: Int)]
          pairs = [(a,b) | a <- values, b <- [-1,2,limit-1]]
          ops = ["mulInt x y", "quotInt x (-1)", "remInt x (-1)",
                 "quotInt x 3", "remInt x 3", "quotInt x (-3)", "remInt x (-3)", "andInt x y"]
          width = length ops
          expected (a,b) = [a*b,a `quot` (-1),a `rem` (-1),a `quot` 3,a `rem` 3,a `quot` (-3),a `rem` (-3),a .&. b]
          source = recursion ++
            "let loop : IntArray -> IntArray -> Int -> IO Unit = fix (\\again a b i -> " ++
            "ifThenElse (ltInt i " ++ show (length pairs) ++ ") (do { " ++
            "x <- readIntArray a (mulInt i 2); y <- readIntArray a (addInt (mulInt i 2) 1); " ++
            concat ["writeIntArray b (addInt (mulInt i " ++ show width ++ ") " ++ show j ++ ") (" ++ op ++ "); "
                   | (j,op) <- zip [0::Int ..] ops] ++
            "again a b (addInt i 1) }) (return ())) in " ++
            "let dump : IntArray -> Int -> IO Unit = fix (\\again a i -> " ++
            "ifThenElse (ltInt i " ++ show (length pairs*width) ++ ") " ++
            "(do { x <- readIntArray a i; printInt x; again a (addInt i 1) }) (return ())) in " ++
            "do { a <- newIntArray " ++ show (length pairs*2) ++ " 0; " ++
            concat ["writeIntArray a " ++ show i ++ " (" ++ show n ++ "); "
                   | (i,n) <- zip [0::Int ..] (concatMap (\(a,b) -> [a,b]) pairs)] ++
            "b <- newIntArray " ++ show (length pairs*width) ++ " 0; loop a b 0; dump b 0 }"
      term <- checked source
      llvm <- right (emitLLVMIO term)
      unless (all (`isInfixOf` llvm) ["call { i64, i1 } @llvm.smul.with.overflow.i64", "sdiv i64", "srem i64"])
        (fail "arithmetic boundary fixture missed the native fast paths")
      observe backends term (unlines (map show (concatMap expected pairs))))
  , ("native scalar arguments: recursive permutations bound specialization", do
      let arguments = ["x" ++ show i | i <- [1::Int ..9]]
          source = recursion ++ "let start : " ++ concat (replicate 9 "Double -> ") ++ "IO Double = \\" ++
            unwords arguments ++ " -> let rotate : Int -> " ++ concat (replicate 10 "Double -> ") ++
            "IO Double = fix (\\again n first " ++ unwords arguments ++ " -> " ++
            "ifThenElse (eqInt n 0) (return first) (again (subInt n 1) " ++
            unwords arguments ++ " (addDouble first 0.0))) in rotate 21 1.0 " ++ unwords arguments ++ " in " ++
            "do { x <- start " ++ unwords [show i ++ ".0" | i <- [2::Int ..10]] ++
            "; putStrLn (formatDouble 1 x) }"
      term <- checked source
      llvm <- right (emitLLVMIO term)
      let prefix = "define private ptr @mlf.numeric."
          counts = map length . group . sort $
            [takeWhile (\c -> c /= '.' && c /= '(') (drop (length prefix) line)
             | line <- lines llvm, take (length prefix) line == prefix,
               not ("@mlf.numeric.entry." `isInfixOf` line)]
      unless (9 `elem` counts && all (<=9) counts) (fail ("specialization cap was not exercised: " ++ show counts))
      observe backends term "2.0\n")
  , ("numeric: multiplication and signed quotient boundaries", do
      let limit = 2^(62 :: Int)
          values = [-2^(100 :: Int),-limit-1,-limit,-1,0,1,3,limit-1,limit,2^(100 :: Int)]
          pairs = [(a,b) | a <- values, b <- values]
          cases = concat [[(P.MulInt,a,b,a*b),(P.AndInt,a,b,a .&. b)] ++
            [(p,a,b,op a b) | b /= 0, (p,op) <- [(P.QuotInt,quot),(P.RemInt,rem)]] | (a,b) <- pairs]
          apply p a b = X.App (X.App (X.Primitive p []) (X.IntTerm a)) (X.IntTerm b)
          printNumber x = X.App (X.Primitive P.PrintInt []) x
          unit = T.Con "Unit" []
          sequence' = foldr (\(i,a) b -> X.App (X.App (X.Primitive P.IOBind [unit,unit]) a)
            (X.Abs (X.Name i "ignored") unit b)) (X.App (X.Primitive P.IOReturn [unit]) (X.Constructor "Unit" []))
      observe backends (sequence' (zip [1000..] [printNumber (apply p a b) | (p,a,b,_) <- cases]))
        (unlines [show n | (_,_,_,n) <- cases]))
  , ("numeric: types reject invalid numeric and array programs", forM_
      [ "addDouble 1 2.0", "sqrtDouble 1", "addInt 1.0 2.0", "andInt 1 2.0"
      , "do { a <- newIntArray 2 0; writeIntArray a 0 1.0 }"
      , "do { a <- newDoubleArray 2 0.0; readIntArray a 0 }"
      , "do { a <- newIntArray 2 0; printInt (readIntArray a 0) }"
      , "data Double = Forged; Forged", "data IntArray = Forged; Forged"
      , "data DoubleArray = Forged; Forged", "putStrLn (formatDouble 2 1e9999)"
      ] $ \source -> case compile "<invalid numeric/array test>" source of
        Left _ -> pure ()
        Right _ -> fail ("accepted: " ++ source))
  , ("numeric: non-finite target literal rejected by both backends", do
      let term = X.App (X.Primitive P.IOReturn [T.Con "Double" []]) (X.DoubleTerm (0/0))
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | "non-finite Double literal" `isInfixOf` show err && null (B.events result) -> pure ()
        _ -> fail (show result))
  , ("numeric: direct and curried formatting force the same arguments", forM_ [False,True] $ \generic -> do
      term <- checked ("let bad = intToDouble (quotInt 1 0) in do { putStrLn \"before\"; " ++
        (if generic then "formatter <- return formatDouble; putStrLn (formatter (-1) bad)"
                    else "putStrLn (formatDouble (-1) bad)") ++ " }")
      result <- B.execute backends IOEntry (Input "" False) term
      case B.outcome result of
        Left err | "integer division by zero" `isInfixOf` show err && B.output result == "before\n" -> pure ()
        _ -> fail (show result))
  , ("numeric: pidigits benchmark partial and full rows", do
      term <- readFile "benchmarks/pidigits/mlf/main.emlf" >>= checked
      forM_ [(1,"3         \t:1\n"),(27,"3141592653\t:10\n5897932384\t:20\n6264338   \t:27\n")] $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n :: Int) ++ "\n") False) term
        right (B.outcome result)
        unless (B.output result == expected && null (B.remaining result)) (fail (show result)))
  , ("numeric: n-body benchmark initialization and integration", do
      term <- readFile "benchmarks/n-body/mlf/main.emlf" >>= checked
      fixture <- readFile "benchmarks/n-body/expected-1000.txt"
      forM_ [(0,"-0.169075164\n-0.169075164\n"),(1,"-0.169075164\n-0.169074954\n"),(1000,fixture)] $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n :: Int) ++ "\n") False) term
        right (B.outcome result)
        let numbers = map read (words (B.output result)) :: [Double]
            reference = map read (words expected) :: [Double]
        unless (length numbers == 2 && all (\(a,b) -> not (isNaN a || isInfinite a) && abs (a-b) <= 1e-8)
          (zip numbers reference) && null (B.remaining result)) (fail (show result)))
  , ("numeric: spectral-norm benchmark small and odd matrices", do
      term <- readFile "benchmarks/spectral-norm/mlf/main.emlf" >>= checked
      fixture <- readFile "benchmarks/spectral-norm/expected-100.txt"
      forM_ [(1,"1.000000000"),(2,"1.183350177"),(3,"1.233644501"),(100,fixture)] $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n :: Int) ++ "\n") False) term
        right (B.outcome result)
        let numbers = map read (words (B.output result)) :: [Double]
        unless (case numbers of [x] -> not (isNaN x || isInfinite x) && abs (x-read expected) <= 1e-8; _ -> False)
          (fail (show result)))
  , ("numeric: fannkuch-redux benchmark checksum and flips", do
      term <- readFile "benchmarks/fannkuch-redux/mlf/main.emlf" >>= checked
      fixture <- readFile "benchmarks/fannkuch-redux/expected-7.txt"
      forM_ [(1,"0\nPfannkuchen(1) = 0\n"),(2,"-1\nPfannkuchen(2) = 1\n"),
             (5,"11\nPfannkuchen(5) = 7\n"),(7,fixture)] $ \(n,expected) -> do
        result <- B.execute backends IOEntry (Input (show (n :: Int) ++ "\n") False) term
        right (B.outcome result)
        unless (B.output result == expected && null (B.remaining result)) (fail (show result)))
  ]

scalarPrograms :: [(String,String,String)]
scalarPrograms =
  [ ("captured doubles and nonnegative countdown",
      "let start : Double -> IO Double = \\step -> " ++
      "let loop : Int -> Double -> IO Double = fix (\\again n x -> " ++
      "ifThenElse (eqInt 0 n) (return x) (again (subInt n 1) (addDouble x step))) in loop 12 0.0 in " ++
      "do { x <- start 0.5; putStrLn (formatDouble 1 x) }", "6.0\n")
  , ("IEEE values survive recursive calls",
      "let loop : Int -> Double -> IO Double = fix (\\again n x -> " ++
      "ifThenElse (eqInt n 0) (return x) (again (subInt n 1) (divDouble x 1.0))) in " ++
      "do { a <- newDoubleArray 1 (-0.0); x <- readDoubleArray a 0; r <- loop 3 x; " ++
      "putStrLn (formatDouble 2 r); writeDoubleArray a 0 (divDouble 1.0 0.0); y <- readDoubleArray a 0; " ++
      "s <- loop 3 y; putStrLn (formatDouble 2 s); writeDoubleArray a 0 (divDouble 0.0 0.0); " ++
      "z <- readDoubleArray a 0; t <- loop 3 z; putStrLn (formatDouble 2 t) }", "-0.00\nInfinity\nNaN\n")
  , ("payload reads stay within their branch",
      "let loop : Bool -> Int -> Double -> IO Double = fix (\\again flag n x -> " ++
      "ifThenElse (eqInt n 0) (return x) (do { ignored <- ifThenElse flag " ++
      "(return (addDouble x 1.0)) (return 0.0); again flag (subInt n 1) (mulDouble x 2.0) })) in " ++
      "do { x <- loop false 3 1.0; y <- loop true 2 1.0; putStrLn (formatDouble 1 x); " ++
      "putStrLn (formatDouble 1 y) }", "8.0\n4.0\n")
  , ("unused failing floating arguments remain lazy",
      "let loop : Int -> Double -> Double -> IO Double = fix (\\again n bad x -> " ++
      "ifThenElse (eqInt n 0) (return x) (again (subInt n 1) bad (addDouble x 0.5))) in " ++
      "do { x <- loop 3 (intToDouble (quotInt 1 0)) 1.0; putStrLn (formatDouble 1 x) }", "2.5\n")
  ]

regionPrograms :: [(String,String,Either String String)]
regionPrograms =
  [ ("specialized integer ranges permit negative results and GMP promotion",
      "let loop : Int -> Int -> IO Int = fix (\\again n x -> ifThenElse (eqInt n 0) (return x) " ++
      "(ifThenElse (eqInt x 4611686018427387903) (again (subInt n 1) (addInt x 1)) " ++
      "(ifThenElse (eqInt x 0) (again (subInt n 1) (subInt x 1)) (again (subInt n 1) (addInt x 1))))) in " ++
      "let start : Bool -> IO Int = \\large -> ifThenElse large (loop 1 4611686018427387903) (loop 2 0) in " ++
      "do { x <- start true; y <- start false; printInt x; printInt y }",
      Right "4611686018427387904\n0\n")
  , ("reused actions execute and snapshots stay immutable",
      "let loop : IntArray -> Int -> IO Int = fix (\\again a n -> ifThenElse (eqInt n 0) " ++
      "(readIntArray a 0) (do { x <- readIntArray a 0; writeIntArray a 0 (addInt x 1); again a (subInt n 1) })) in " ++
      "do { a <- newIntArray 1 4611686018427387902; let action = loop a 2; x <- action; y <- action; printInt x; printInt y }",
      Right "4611686018427387904\n4611686018427387906\n")
  , ("unforced unused arguments take the lazy boundary",
      "let loop : Bool -> Int -> IntArray -> Int -> IO Int = fix (\\again flag bad a n -> " ++
      "ifThenElse (eqInt n 0) (return 0) (ifThenElse flag (return 42) " ++
      "(do { writeIntArray a 0 bad; again flag bad a (subInt n 1) }))) in " ++
      "do { a <- newIntArray 1 0; x <- loop true (quotInt 1 0) a 1; printInt x }", Right "42\n")
  , ("aliased Double arrays preserve write and read order",
      "let loop : DoubleArray -> DoubleArray -> Int -> IO Unit = fix (\\again a b n -> " ++
      "ifThenElse (eqInt n 0) (return ()) (do { x <- readDoubleArray a 0; writeDoubleArray b 0 (addDouble x 1.0); " ++
      "y <- readDoubleArray a 0; writeDoubleArray b 0 (mulDouble y 2.0); again a b (subInt n 1) })) in " ++
      "do { a <- newDoubleArray 1 1.0; b <- newDoubleArray 1 1.0; c <- newDoubleArray 1 0.0; " ++
      "loop a a 2; loop b c 2; x <- readDoubleArray a 0; y <- readDoubleArray c 0; " ++
      "putStrLn (formatDouble 1 x); putStrLn (formatDouble 1 y) }", Right "10.0\n2.0\n")
  , ("range facts do not escape a conditional branch",
      "let loop : Bool -> IntArray -> Int -> Int -> IO Unit = fix (\\again flag a i n -> " ++
      "ifThenElse (eqInt n 0) (return ()) (do { ifThenElse flag " ++
      "(do { ignored <- readIntArray a i; return () }) (return ()); " ++
      "writeIntArray a (addInt i 1) 0; again flag a i (subInt n 1) })) in " ++
      "do { putStrLn \"before\"; a <- newIntArray 1 0; loop false a 4611686018427387903 1 }",
      Left "array index out of bounds")
  , ("lazy write operands retain bounds-error ordering",
      "let loop : IntArray -> Int -> Int -> Int -> IO Unit = fix (\\again a i bad n -> " ++
      "ifThenElse (eqInt n 0) (return ()) (do { writeIntArray a i bad; again a i bad (subInt n 1) })) in " ++
      "do { putStrLn \"before\"; a <- newIntArray 1 0; loop a 2 (quotInt 1 0) 1 }",
      Left "array index out of bounds")
  ] ++ [(label,
      "let loop : DoubleArray -> Int -> Int -> IO Unit = fix (\\again a i n -> " ++
      "ifThenElse (eqInt n 0) (return ()) (do { ignored <- readDoubleArray a i; again a i (subInt n 1) })) in " ++
      "do { putStrLn \"before\"; a <- newDoubleArray " ++ size ++ " 0.0; loop a " ++ index ++ " 1 }",
      Left "array index out of bounds") | (label,size,index) <-
        [("negative native index","1","(-1)"),
         ("GMP native index","1","4611686018427387904"),
         ("empty native array","0","0")]]

programs :: [(String,String,String)]
programs =
  [ ("read unbounded signed decimals", "do { printInt (readInt \"+00042\"); printInt (readInt \"-123456789012345678901234567890\"); printInt (readInt \"-0\") }", "42\n-123456789012345678901234567890\n0\n")
  , ("curried GMP primitives", "do { mul <- return mulInt; q <- return quotInt; r <- return remInt; printInt (mul 12345678901234567890 10); printInt (q (-19) 3); printInt (r (-19) 3) }", "123456789012345678900\n-6\n-1\n")
  , ("curried unbounded bitwise AND", "do { mask <- return andInt; printInt (mask (-1) 1267650600228229401496703205377); printInt (mask (-2) (-3)); printInt (mask 1267650600228229401496703205377 3) }", "1267650600228229401496703205377\n-4\n1\n")
  , ("unused bitwise arguments remain lazy", "do { return (andInt (quotInt 1 0) 0); printInt (ifThenElse true 7 (andInt 0 (quotInt 2 0))) }", "7\n")
  , ("binary64 arithmetic and scientific literals", "do { putStrLn (formatDouble 9 (sqrtDouble (addDouble (mulDouble 3.0 3.0) (mulDouble 4e0 4.0)))); putStrLn (formatDouble 3 (divDouble (subDouble 1.25 (-2.5)) 2.0)); putStrLn (formatDouble 1 (intToDouble (-42))) }", "5.000000000\n1.875\n-42.0\n")
  , ("rounding ties and signed zero", "do { putStrLn (formatDouble 0 2.5); putStrLn (formatDouble 0 3.5); putStrLn (formatDouble 2 1.005); putStrLn (formatDouble 2 (-0.0)); putStrLn (formatDouble 2 (-0.001)) }", "2\n4\n1.00\n-0.00\n-0.00\n")
  , ("generic floating primitives and IEEE comparisons", "do { f <- return mulDouble; root <- return sqrtDouble; equal <- return eqDouble; less <- return ltDouble; putStrLn (formatDouble 2 (root (f 2.0 8.0))); printInt (ifThenElse (equal (-0.0) 0.0) 1 0); printInt (ifThenElse (less (-2.0) 1.0) 1 0); printInt (ifThenElse (equal (divDouble 0.0 0.0) 0.0) 1 0); printInt (ifThenElse (less (sqrtDouble (-1.0)) 0.0) 1 0) }", "4.00\n1\n1\n0\n0\n")
  , ("IEEE non-finite results", "do { putStrLn (formatDouble 3 (divDouble 1.0 0.0)); putStrLn (formatDouble 3 (divDouble (-1.0) 0.0)); putStrLn (formatDouble 3 (sqrtDouble (-1.0))); putStrLn (formatDouble 3 (mulDouble 1e308 1e308)) }", "Infinity\n-Infinity\nNaN\nInfinity\n")
  , ("large integer conversion rounds to nearest", "do { putStrLn (formatDouble 0 (intToDouble 9007199254740995)); putStrLn (formatDouble 0 (intToDouble 4611686018427388672)); putStrLn (formatDouble 0 (intToDouble (-4611686018427388672))) }", "9007199254740996\n4611686018427388928\n-4611686018427388928\n")
  , ("IntArray aliasing and repeated action reads", "do { a <- newIntArray 3 7; let alias = a; let read = readIntArray alias 1; x <- read; writeIntArray a 1 123456789012345678901234567890; y <- read; n <- lengthIntArray a; printInt x; printInt y; printInt n }", "7\n123456789012345678901234567890\n3\n")
  , ("allocation actions produce distinct arrays", "let new = newIntArray 1 5 in do { a <- new; b <- new; writeIntArray a 0 42; x <- readIntArray b 0; printInt x }", "5\n")
  , ("DoubleArray values are copied at read time", "do { a <- newDoubleArray 2 1.5; let read = readDoubleArray a 0; x <- read; writeDoubleArray a 0 (mulDouble x 2.0); y <- read; n <- lengthDoubleArray a; putStrLn (formatDouble 1 x); putStrLn (formatDouble 1 y); printInt n }", "1.5\n3.0\n2\n")
  , ("generic ternary writes", "do { write <- return writeIntArray; create <- return newDoubleArray; wd <- return writeDoubleArray; a <- newIntArray 1 0; b <- create 1 0.0; wa <- return (write a 0); wa 42; wd b 0 2.25; x <- readIntArray a 0; y <- readDoubleArray b 0; printInt x; putStrLn (formatDouble 2 y) }", "42\n2.25\n")
  , ("unused actions and unselected arithmetic remain lazy", "do { a <- newIntArray 1 1; let ignored = writeIntArray a 0 (quotInt 1 0); return ignored; let bad = newDoubleArray (-1) (sqrtDouble (-1.0)); return bad; x <- readIntArray a 0; printInt x; printInt (ifThenElse true 42 (quotInt 1 0)) }", "1\n42\n")
  , ("empty arrays have zero length", "do { a <- newIntArray 0 0; b <- newDoubleArray 0 0.0; x <- lengthIntArray a; y <- lengthDoubleArray b; printInt (addInt x y) }", "0\n")
  , ("array roots and boxed cells survive collection", recursion ++
      "let loop : IntArray -> DoubleArray -> Int -> IO Unit = fix (\\again a b n -> ifThenElse (eqInt n 0) (return ()) (do { x <- readIntArray a 0; y <- readDoubleArray b 0; writeIntArray a 0 (addInt x 1); writeDoubleArray b 0 (addDouble y 0.5); again a b (subInt n 1) })) in " ++
      "do { a <- newIntArray 1 123456789012345678901234567890; b <- newDoubleArray 1 0.0; loop a b 300; x <- readIntArray a 0; y <- readDoubleArray b 0; printInt x; putStrLn (formatDouble 1 y) }", "123456789012345678901234568190\n150.0\n")
  ]

failures :: [(String,String,String)]
failures =
  [ ("quotient by zero", "printInt (quotInt 4611686018427387904 0)", "integer division by zero")
  , ("remainder by zero", "printInt (remInt 1 0)", "integer division by zero")
  , ("bitwise zero mask still demands its argument", "printInt (andInt 0 (quotInt 1 0))", "integer division by zero")
  , ("direct bitwise arguments are ordered", "printInt (andInt (readInt \"bad\") (quotInt 1 0))", "invalid integer input")
  , ("curried bitwise arguments are ordered", "do { mask <- return andInt; printInt (mask (readInt \"bad\") (quotInt 1 0)) }", "invalid integer input")
  , ("empty integer input", "printInt (readInt \"\")", "invalid integer input")
  , ("signed empty input", "printInt (readInt \"-\")", "invalid integer input")
  , ("whitespace integer input", "printInt (readInt \" 1\")", "invalid integer input")
  , ("embedded NUL input", "printInt (readInt \"1\\0\")", "invalid integer input")
  , ("fractional integer input", "printInt (readInt \"1.5\")", "invalid integer input")
  , ("negative precision", "putStrLn (formatDouble (-1) 1.0)", "Double precision must be between 0 and 17")
  , ("large precision", "putStrLn (formatDouble 999999999999999999999 1.0)", "Double precision must be between 0 and 17")
  , ("negative array length", "newIntArray (-1) 0", "invalid array length")
  , ("huge array length", "newDoubleArray 999999999999999999999 0.0", "invalid array length")
  , ("negative read index", "do { a <- newIntArray 1 0; readIntArray a (-1) }", "array index out of bounds")
  , ("huge read index", "do { a <- newIntArray 1 0; readIntArray a 999999999999999999999 }", "array index out of bounds")
  , ("empty array read", "do { a <- newDoubleArray 0 0.0; readDoubleArray a 0 }", "array index out of bounds")
  , ("integer write past end", "do { a <- newIntArray 2 0; writeIntArray a 2 3 }", "array index out of bounds")
  , ("negative Double write", "do { a <- newDoubleArray 1 0.0; writeDoubleArray a (-1) 3.0 }", "array index out of bounds")
  , ("writes force stored values", "do { a <- newIntArray 1 0; writeIntArray a 0 (quotInt 1 0) }", "integer division by zero")
  , ("direct floating arguments are ordered", "putStrLn (formatDouble 1 (addDouble (intToDouble (readInt \"bad\")) (intToDouble (quotInt 1 0))))", "invalid integer input")
  , ("curried floating arguments are ordered", "do { add <- return addDouble; putStrLn (formatDouble 1 (add (intToDouble (readInt \"bad\")) (intToDouble (quotInt 1 0)))) }", "invalid integer input")
  ]

recursion :: String
recursion = "data Rec a = Rec (Rec a -> a); let fix : forall a. (a -> a) -> a = \\f -> let go = \\r -> case r of { Rec next -> f (next r) } in go (Rec go) in "
