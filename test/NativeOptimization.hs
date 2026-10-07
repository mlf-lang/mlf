-- Independent interpreter/native observations for optimizer and runtime
-- boundaries. Expected integers are calculated with Haskell Integer.
module NativeOptimization (nativeOptimizationTests) where

import Control.Monad (unless)
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X
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
  , ("native optimization: partial workers stay lazy", observe backends ProgramEntry partialWorker "")
  , ("native optimization: function captures and mutual recursion", do
      observe backends IOEntry captureWorkers "42\n"
      parsed <- either fail pure (XP.parseTerm "<native worker round trip>" (prettyTerm (captureWorkersAt 1000)))
      original <- either fail pure (emitLLVMIO captureWorkers)
      serialized <- either fail pure (emitLLVMIO parsed)
      unless (original == serialized) (fail "worker symbols depend on parser-assigned identities"))
  , ("native optimization: identities reused in disjoint scopes", observe backends IOEntry disjointIdentities "42\n")
  , ("native optimization: packed and general constructor layouts", observe backends IOEntry constructorLayouts "42\n")
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
