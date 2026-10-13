-- Independent interpreter/native observations for optimizer and runtime
-- boundaries. Expected integers are calculated with Haskell Integer.
module NativeOptimization (nativeOptimizationTests) where

import Control.Monad (forM_, unless)
import Data.List (isInfixOf, isPrefixOf, tails)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.LLVM.Analysis as Analysis
import qualified MLF.LLVM.Codegen as Codegen
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X
import qualified MLF.X.Check as Check
import qualified MLF.X.Type as T
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)

int, unit, ioUnit :: T.Type
int = T.Con "Int" []
unit = T.Con "Unit" []
ioUnit = T.Con "IO" [unit]

name :: Int -> X.Name
name i = X.Name i "same"

binary :: P.Primitive -> X.Term -> X.Term -> X.Term
binary p a b = X.App (X.App (X.Primitive p []) a) b

choose :: T.Type -> X.Term -> X.Term -> X.Term -> X.Term
choose t c a b = X.App (X.App (X.App (X.Primitive P.IfThenElse [t]) c) a) b

printInt :: X.Term -> X.Term
printInt = X.App (X.Primitive P.PrintInt [])

sequenceIO :: [X.Term] -> X.Term
sequenceIO actions = foldr (\(i,a) b -> X.App (X.App (X.Primitive P.IOBind [unit,unit]) a) (X.Abs (name i) unit b))
  (X.App (X.Primitive P.IOReturn [unit]) (X.Constructor "Unit" [])) (zip [9000..] actions)

observe :: Backends -> Entry -> X.Term -> String -> IO ()
observe backends entry term expected = do
  result <- B.execute backends entry (Input "" False) term
  either (fail . show) pure (B.outcome result)
  unless (B.output result == expected) (fail (show result))

nativeOptimizationTests :: Backends -> [(String,IO ())]
nativeOptimizationTests backends =
  [ ("native optimization: tagged integer boundaries", do
      let limit = 2 ^ (62 :: Int)
          values = [-limit-1,-limit,-limit+1,-1,0,1,limit-1,limit,limit+1,2^(100 :: Int)]
          pairs = [(a,b) | a <- values, b <- values]
          number n = X.IntTerm n
          expression (a,b) = [printInt (binary p (number a) (number b)) | p <- [P.AddInt,P.SubInt]] ++
            [printInt (choose int (binary p (number a) (number b)) (number 1) (number 0)) | p <- [P.EqInt,P.LtInt]]
          expected (a,b) = map show [a+b,a-b,if a==b then 1 else 0,if a<b then 1 else 0]
      observe backends IOEntry (sequenceIO (concatMap expression pairs)) (unlines (concatMap expected pairs)))
  , ("native optimization: ordinary products and division preserve Integer boundaries", do
      let limit = 2 ^ (62 :: Int)
          values = [-limit-1,-limit,-limit+1,-1,0,1,limit-1,limit,limit+1,2^(100 :: Int)]
          operations a b = [(P.MulInt,a*b)] ++
            [(P.QuotInt,a `quot` b) | b /= 0] ++ [(P.RemInt,a `rem` b) | b /= 0]
          cases = [(p,a,b,want) | a <- values, b <- values, (p,want) <- operations a b]
          term = sequenceIO [printInt (binary p (X.IntTerm a) (X.IntTerm b)) | (p,a,b,_) <- cases]
      llvm <- either fail pure (emitLLVMIO term)
      unless ("= call { i64, i1 } @llvm.smul.with.overflow.i64(" `isInfixOf` llvm &&
              not ("define private ptr @mlf.numeric." `isInfixOf` llvm))
        (fail "ordinary arithmetic fixture did not exercise checked product lowering")
      observe backends IOEntry term (unlines [show want | (_,_,_,want) <- cases]))
  , ("native optimization: partial workers stay lazy", observe backends ProgramEntry partialWorker "")
  , ("native optimization: seq propagates saturated worker demands", do
      let term = seqWorker (X.IntTerm 19) (X.IntTerm 42)
      case Map.lookup (name 0) (Analysis.analyze (X.erase term)) of
        Just worker | Analysis.strict worker == Set.fromList [name 1,name 2] -> pure ()
        _ -> fail "saturated seq worker did not demand both arguments"
      observe backends IOEntry term "before\n42\n")
  , ("native optimization: seq worker forces both operands after preceding effects", forM_
      [(panicInt "first",X.IntTerm 42,"first"),
       (X.IntTerm 19,panicInt "second","second")] $ \(a,b,message) -> do
      result <- B.execute backends IOEntry (Input "" False) (seqWorker a b)
      unless (either ((== message) . show) (const False) (B.outcome result) &&
        B.events result == [B.Write "before\n"]) (fail (show result)))
  , ("native optimization: partial seq stays lazy", observe backends ProgramEntry partialSeq "")
  , ("native optimization: function captures and mutual recursion", do
      observe backends IOEntry captureWorkers "42\n"
      parsed <- either fail pure (XP.parseTerm "<native worker round trip>" (prettyTerm (captureWorkersAt 1000)))
      original <- either fail pure (emitLLVMIO captureWorkers)
      serialized <- either fail pure (emitLLVMIO parsed)
      unless (original == serialized) (fail "worker symbols depend on parser-assigned identities"))
  , ("native optimization: identities reused in disjoint scopes", observe backends IOEntry disjointIdentities "42\n")
  , ("native optimization: packed and general constructor layouts", do
      observe backends IOEntry constructorLayouts "42\n"
      _ <- either fail pure (Check.checkClosed constructorLayouts)
      -- Exercise lowering directly: optimization may legitimately project
      -- away the constructor, while both backends above use the full pipeline.
      (_,code) <- either fail pure (Codegen.generate
        (Map.fromList [("Unit",(0,0)),("One",(1,1)),("Three",(2,3))]) (X.erase constructorLayouts))
      let llvm = unlines code
      unless ("call ptr @mlf_constructor_new(" `isInfixOf` llvm &&
        not ("call ptr @mlf_application(" `isInfixOf` llvm))
        (fail "saturated constructor still builds generic application nodes"))
  , ("native optimization: wide constructors keep fields lazy and recursive", observe backends IOEntry wideConstructor "42\n")
  , ("native optimization: five-field constructor returned from numeric region", do
      term <- either (fail . show) (pure . compiledTerm) (compile "<numeric constructor>" numericConstructorSource)
      observe backends IOEntry term "42\n47\n"
      llvm <- either fail pure (emitLLVMIO term)
      let workers = [takeWhile (/= "}") body | line:body <- tails (lines llvm),
                      "define private ptr @mlf.numeric." `isPrefixOf` line]
      unless (any (any ("call ptr @mlf_constructor_new(" `isInfixOf`)) workers)
        (fail "numeric constructor fixture did not exercise direct field construction"))
  , ("native optimization: general fields retain captured worker values", do
      observe backends IOEntry capturedConstructorField "42\n43\n"
      let functions = Analysis.analyze (X.erase capturedConstructorField)
      unless (Analysis.needed functions (X.EVar (name 8)) == Set.singleton (name 7))
        (fail "field fixture did not expose its recursive worker capture")
      llvm <- rawFiveCode capturedConstructorField
      unless (not ("call ptr @mlf_field(" `isInfixOf` llvm) &&
        length (filter ("= load ptr," `isInfixOf`) (lines llvm)) == 2 &&
        any ("i64 56" `isInfixOf`) (lines llvm))
        (fail "general case did not load only its captured last field"))
  , ("native optimization: dead and wildcard fields need no environment", do
      observe backends IOEntry discardedConstructorFields "7\n"
      llvm <- rawFiveCode discardedConstructorFields
      unless (not ("call ptr @mlf_field(" `isInfixOf` llvm) &&
        not ("= load ptr," `isInfixOf` llvm))
        (fail "unused constructor fields still access their environment"))
  ] ++
  [("native optimization: " ++ label, do
      term <- either (fail . show) (pure . compiledTerm) (compile "<native optimization>" source)
      observe backends IOEntry term expected) | (label,source,expected) <- sources]
  where
    sources =
      [ ("recursive encoding is structural",
          "data Roll a = Roll (Roll a -> a); let tie : forall a. (a -> a) -> a = \\step -> " ++
          "let unroll = \\rolled -> case rolled of { Roll fn -> step (fn rolled) } in unroll (Roll unroll) in " ++
          "let sum : Int -> Int = tie (\\again n -> ifThenElse (eqInt n 0) 0 (addInt n (again (subInt n 1)))) in printInt (sum 100)",
          "5050\n")
      , ("escaping recursive function",
          "data Roll a = Roll (Roll a -> a); let tie : forall a. (a -> a) -> a = \\f -> " ++
          "let go = \\r -> case r of { Roll next -> f (next r) } in go (Roll go) in " ++
          "let sum : Int -> Int = tie (\\again n -> ifThenElse (eqInt n 0) 0 (addInt n (again (subInt n 1)))) in " ++
          "do { f <- return sum; printInt (f 10); printInt (sum 2) }", "55\n3\n")
      , ("captured closures survive collection",
          "data Roll a = Roll (Roll a -> a); let tie : forall a. (a -> a) -> a = \\f -> " ++
          "let go = \\r -> case r of { Roll next -> f (next r) } in go (Roll go) in " ++
          "let repeat : Int -> IO Unit = tie (\\again n -> ifThenElse (eqInt n 0) (return ()) " ++
          "(do { ignored <- return (addInt n 1); again (subInt n 1) })) in " ++
          "do { x <- return (addInt 19 20); let f = \\y z -> addInt x (addInt y z) in " ++
          "do { saved <- return (f 1); repeat 300; printInt (saved 2); printInt (f 3 0) } }", "42\n42\n")
      , ("lazy recursive fields and conditional demands",
          "data Roll a = Roll (Roll a -> a); data Pair = Pair Int Int; " ++
          "let spin : Int = let go = \\r -> case r of { Roll next -> next r } in go (Roll go) in " ++
          "let choose = \\flag x y -> ifThenElse flag (addInt x 1) (subInt y 1) in " ++
          "case Pair spin 41 of { Pair bottom n -> do { printInt (choose true n bottom); printInt (choose false bottom 43) } }", "42\n42\n")
      , ("seq demands stay inside the chosen branch",
          "let pick = \\flag x y -> if flag then seq x 11 else seq y 22 in " ++
          "do { printInt (pick true 1 (panic \"right\")); printInt (pick false (panic \"left\") 2) }",
          "11\n22\n")
      , ("seq preserves ignored arguments and unused results",
          "let keep = \\x ignored -> x in let force = \\x y -> seq x y in " ++
          "do { printInt (keep 42 (force (panic \"unused first\") (panic \"unused second\"))); " ++
          "return (force (panic \"unused result\") 3); printInt 7 }", "42\n7\n")
      , ("three-field constructor partially applied",
          "data Triple = Triple Int Int Int; do { ctor <- return Triple; partial <- return (ctor 10 12); " ++
          "case partial 20 of { Triple a b c -> printInt (addInt a (addInt b c)) } }", "42\n")
      , ("generic arithmetic crosses immediate range",
          "do { add <- return addInt; sub <- return subInt; less <- return ltInt; " ++
          "printInt (add 4611686018427387903 1); printInt (sub (-4611686018427387904) 1); " ++
          "printInt (add 4611686018427387904 (-1)); printInt (ifThenElse (less (-1) 4611686018427387904) 1 0) }",
          "4611686018427387904\n-4611686018427387905\n4611686018427387903\n1\n")
      ]

-- Saturating f demands x, but the first application returns a closure.
partialWorker :: X.Term
partialWorker = X.LetRec
  [(bottom,int,X.VarTerm bottom), (f,T.Arrow int (T.Arrow int int),X.Abs x int (X.Abs y int body))]
  (X.App (X.VarTerm f) (X.VarTerm bottom))
  where
    bottom = name 0; f = name 1; x = name 2; y = name 3
    body = choose int (binary P.EqInt (X.VarTerm y) (X.IntTerm 0))
      (binary P.AddInt (X.VarTerm x) (X.IntTerm 1))
      (X.App (X.App (X.VarTerm f) (X.VarTerm x)) (binary P.SubInt (X.VarTerm y) (X.IntTerm 1)))

panicInt :: String -> X.Term
panicInt message = X.App (X.Primitive P.Panic [int]) (X.StringTerm message)

seqWorker :: X.Term -> X.Term -> X.Term
seqWorker a b = X.Let (name 0)
  (X.Abs (name 1) int (X.Abs (name 2) int
    (X.App (X.App (X.Primitive P.Seq [int,int]) (X.VarTerm (name 1))) (X.VarTerm (name 2)))))
  (sequenceIO [X.App (X.Primitive P.PutStrLn []) (X.StringTerm "before"),
    printInt (X.App (X.App (X.VarTerm (name 0)) a) b)])

-- A partial primitive application is a value even if its first operand is bottom.
partialSeq :: X.Term
partialSeq = X.LetRec [(name 2,int,X.VarTerm (name 2))] $
  X.Let (name 0) (X.Abs (name 1) int
    (X.App (X.Primitive P.Seq [int,int]) (X.VarTerm (name 1))))
    (X.App (X.VarTerm (name 0)) (X.VarTerm (name 2)))

-- Both workers transitively capture a lazy outer binding. g escapes into IO
-- and then is called through the ordinary closure ABI.
captureWorkers :: X.Term
captureWorkers = captureWorkersAt 0

captureWorkersAt :: Int -> X.Term
captureWorkersAt offset = X.Let saved (binary P.AddInt (X.IntTerm 19) (X.IntTerm 23)) $
  X.LetRec [(f,fn,X.Abs x int (X.App (X.VarTerm g) (X.VarTerm x))),
            (g,fn,X.Abs y int (choose int (binary P.EqInt (X.VarTerm y) (X.IntTerm 0))
              (X.VarTerm saved) (X.App (X.VarTerm f) (binary P.SubInt (X.VarTerm y) (X.IntTerm 1)))))] $
    X.App (X.App (X.Primitive P.IOBind [fn,unit]) (X.App (X.Primitive P.IOReturn [fn]) (X.VarTerm g)))
      (X.Abs escaped fn (printInt (X.App (X.VarTerm escaped) (X.IntTerm 20))))
  where
    fn = T.Arrow int int
    local i = name (offset + i)
    saved = local 0; f = local 1; g = local 2; x = local 3; y = local 4; escaped = local 5

disjointIdentities :: X.Term
disjointIdentities = printInt $ X.App
  (X.Let (name 0) (X.IntTerm 19) (X.Abs (name 1) int (binary P.AddInt (X.VarTerm (name 0)) (X.VarTerm (name 1)))))
  (X.Let (name 0) (X.IntTerm 23) (X.VarTerm (name 0)))

constructorLayouts :: X.Term
constructorLayouts = X.WithData
  [D.DataDecl "One" [] [D.ConstructorDecl "One" [D.Applied "Int" []]],
   D.DataDecl "Three" [] [D.ConstructorDecl "Three" [D.Applied "One" [],D.Applied "Int" [],D.Applied "Three" []]]] $
  X.LetRec [(tree,T.Con "Three" [],foldl X.App (X.Constructor "Three" [])
    [X.App (X.Constructor "One" []) (X.IntTerm 19),X.IntTerm 23,X.VarTerm tree])] $
  X.Case (X.VarTerm tree) ioUnit [X.Alternative (X.ConstructorPattern "Three" [Just a,Just b,Nothing])
    (X.Case (X.VarTerm a) ioUnit [X.Alternative (X.ConstructorPattern "One" [Just c])
      (printInt (binary P.AddInt (X.VarTerm b) (X.VarTerm c)))])]
  where tree = name 0; a = name 1; b = name 2; c = name 3

-- The first field must stay unevaluated, the last ties a recursive knot, and
-- the intervening fields exercise ordering and an escaping captured function.
-- Seventeen fields also covers records larger than argument-register sets.
wideConstructor :: X.Term
wideConstructor = X.WithData [declaration] $
  X.Let captured (binary P.AddInt (X.IntTerm 100) (X.IntTerm 47)) $
  X.LetRec [(tree,wide,foldl X.App (X.Constructor "Wide" []) fields)] $
  X.Case (X.VarTerm tree) ioUnit
    [X.Alternative (X.ConstructorPattern "Wide" (replicate 15 Nothing ++ [Just function,Just next])) $
      X.Case (X.VarTerm next) ioUnit
        [X.Alternative (X.ConstructorPattern "Wide" (Nothing : map Just numbers ++ [Nothing,Nothing])) $
          printInt (X.App (X.VarTerm function) (foldr (binary P.AddInt . X.VarTerm) (X.IntTerm 0) numbers))]]
  where
    wide = T.Con "Wide" []
    declaration = D.DataDecl "Wide" [] [D.ConstructorDecl "Wide"
      (replicate 15 (D.Applied "Int" []) ++
        [D.Function (D.Applied "Int" []) (D.Applied "Int" []),D.Applied "Wide" []])]
    captured = name 0; tree = name 1; argument = name 2; function = name 3; next = name 4
    numbers = map name [10..23]
    fields = panicInt "unused wide field" : map X.IntTerm [1..14] ++
      [X.Abs argument int (binary P.SubInt (X.VarTerm captured) (X.VarTerm argument)),X.VarTerm tree]

-- Two uses and a body larger than the inliner threshold retain the numeric
-- worker. Its returned constructor is consumed outside the numeric region.
numericConstructorSource :: String
numericConstructorSource =
  "data Five = Five Int Int Int Int Int; let make = \\n -> ioReturn " ++
  "(Five n (addInt n 1) (addInt n 2) (addInt n 3) (addInt n 6)) in " ++
  "do { first <- make 6; second <- make 7; " ++
  "case first of { Five a b c d e -> printInt (addInt a (addInt b (addInt c (addInt d e)))) }; " ++
  "case second of { Five a b c d e -> printInt (addInt a (addInt b (addInt c (addInt d e)))) } }"

rawFiveCode :: X.Term -> IO String
rawFiveCode term = do
  _ <- either fail pure (Check.checkClosed term)
  (_,code) <- either fail pure (Codegen.generate
    (Map.fromList [("Unit",(0,0)),("Five",(1,5))]) (X.erase term))
  -- Closure-environment loads also use direct slots. Count field loads only
  -- in the function scrutinizing the record, independently of its callbacks.
  let alternatives = [unlines body | line:rest <- tails (lines (unlines code)),
        "define private ptr " `isPrefixOf` line,
        let body = takeWhile (/= "}") rest, any ("switch i64 " `isInfixOf`) body]
  case alternatives of
    [body] -> pure body
    _ -> fail "field-liveness fixture did not retain exactly one constructor case"

-- Returning the constructor and its partial application through IO keeps the
-- scrutinee opaque to projection. Four poisoned fields stay lazy when the
-- generic application path completes the five-field constructor.
constructorFieldsInput :: [Maybe X.Name] -> X.Term -> X.Term
constructorFieldsInput fields body = X.WithData
  [D.DataDecl "Five" [] [D.ConstructorDecl "Five" (replicate 5 (D.Applied "Int" []))]] $
  bind constructorType (ret constructorType (X.Constructor "Five" [])) constructor $
  bind partialType (ret partialType (foldl X.App (X.VarTerm constructor)
    [panicInt ("unused field " ++ show i) | i <- [0..3 :: Int]])) partial $
  bind five (ret five (X.App (X.VarTerm partial) (X.IntTerm 41))) record $
    X.Case (X.VarTerm record) ioUnit [X.Alternative (X.ConstructorPattern "Five" fields) body]
  where
    five = T.Con "Five" []
    constructorType = foldr T.Arrow five (replicate 5 int)
    partialType = T.Arrow int five
    constructor = name 0; partial = name 1; record = name 2
    ret ty value = X.App (X.Primitive P.IOReturn [ty]) value
    bind ty action variable next = X.App (X.App (X.Primitive P.IOBind [ty,unit]) action) (X.Abs variable ty next)

capturedConstructorField :: X.Term
capturedConstructorField = constructorFieldsInput [Just (name 3),Just (name 4),Nothing,Just (name 6),Just captured] $
  X.LetRec [(worker,fn,X.Abs counter int
    (choose int (binary P.EqInt (X.VarTerm counter) (X.IntTerm 0)) (X.VarTerm captured)
      (binary P.AddInt (X.IntTerm 1) (X.App (X.VarTerm worker)
        (binary P.SubInt (X.VarTerm counter) (X.IntTerm 1))))))] $
  X.App (X.App (X.Primitive P.IOBind [fn,unit]) (X.App (X.Primitive P.IOReturn [fn]) (X.VarTerm worker)))
    (X.Abs escaped fn (sequenceIO
      [printInt (X.App (X.VarTerm escaped) (X.IntTerm 1)),
       printInt (X.App (X.VarTerm worker) (X.IntTerm 2))]))
  where
    captured = name 7; worker = name 8; counter = name 9; escaped = name 10
    fn = T.Arrow int int

discardedConstructorFields :: X.Term
discardedConstructorFields = constructorFieldsInput
  [Just (name 3),Nothing,Just (name 5),Nothing,Just (name 7)] (printInt (X.IntTerm 7))
