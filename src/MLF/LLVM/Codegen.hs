-- | Native workers for known saturated functions, with memoized closures for
-- everything that remains lazy or higher order. Demand information is only
-- used at saturation, never while constructing a partial application.
module MLF.LLVM.Codegen (generate) where

import Control.Monad (foldM, forM, forM_, unless, when, (>=>))
import Control.Monad.State.Strict
import Data.Bits ((.&.), shiftR)
import Data.Char (ord)
import Data.List (intercalate)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import Numeric (showHex)
import GHC.Float (castDoubleToWord64)
import qualified MLF.LLVM.Analysis as A
import qualified MLF.LLVM.Kernel as K
import MLF.LLVM.Optimize (applications)
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X

data Binding = Binding { operand :: String, evaluated :: Bool }
type Scope = Map.Map X.Name Binding
type Constructors = Map.Map String (Int,Int)
data Output = Output
  { serial :: !Int, instructions :: [String], block :: String
  , definitions :: [String], constants :: [String]
  , constructors :: Constructors, functions :: A.Functions
  , workers :: Set.Set X.Name, wrappers :: Map.Map X.Name String
  , numericKernels :: Set.Set X.Name, kernelWorkers :: Set.Set X.Name
  , kernelEntries :: Map.Map X.Name String
  , inlinePrimitives :: Bool
  , scalarRanges :: Map.Map String (Integer,Integer)
  , arrayViews :: Map.Map String (String,String)
  }
type Build = StateT Output (Either String)

generate :: Constructors -> X.Erased -> Either String (String,[String])
generate cs term = do
  let fs = A.analyze term
  (entry,out) <- runStateT (callback [] Nothing term)
    (Output 0 [] "entry" [] [] cs fs Set.empty Map.empty (K.kernels fs) Set.empty Map.empty True Map.empty Map.empty)
  pure (entry, runtimeDeclarations ++ reverse (constants out) ++ reverse (definitions out))

fresh :: String -> Build String
fresh prefix = do
  n <- gets serial
  modify' (\s -> s { serial = n + 1 })
  pure (prefix ++ show n)

emit :: String -> Build ()
emit line = modify' (\s -> s { instructions = line : instructions s })

label :: String -> Build ()
label name = emit (name ++ ":") >> modify' (\s -> s { block = name })

result :: String -> Build String
result expression = do
  register <- fresh "%v"
  emit ("  " ++ register ++ " = " ++ expression)
  pure register

call :: String -> [String] -> Build String
call name arguments = result ("call ptr " ++ name ++ "(" ++ intercalate ", " arguments ++ ")")

pointer :: String -> String
pointer = ("ptr " ++)

number :: Int -> String
number = ("i64 " ++) . show

immediate :: Integer -> String
immediate n = "inttoptr (i64 " ++ show n ++ " to ptr)"

definition :: String -> [String] -> Build String -> Build ()
definition name args body = do
  saved <- gets (\s -> (instructions s,block s,scalarRanges s,arrayViews s))
  modify' (\s -> s { instructions = [], block = "entry", scalarRanges = Map.empty, arrayViews = Map.empty })
  value <- body
  emit ("  ret ptr " ++ value)
  code <- gets (reverse . instructions)
  let attributes = if take 13 name == "@mlf.numeric." && take 19 name /= "@mlf.numeric.entry." then " alwaysinline" else ""
      text = unlines (["define private ptr " ++ name ++ "(" ++ intercalate ", " args ++ ")" ++ attributes ++ " {", "entry:"] ++ code ++ ["}"])
  let (savedInstructions,savedBlock,savedRanges,savedViews) = saved
  modify' (\s -> s { instructions = savedInstructions, block = savedBlock,
    scalarRanges = savedRanges, arrayViews = savedViews, definitions = text : definitions s })

lookupConstructor :: String -> Build (Int,Int)
lookupConstructor name = gets (Map.lookup name . constructors) >>= maybe
  (lift (Left ("LLVM unknown constructor: " ++ name))) pure

lookupName :: Scope -> X.Name -> Build Binding
lookupName scope name = case Map.lookup name scope of
  Just v -> pure v
  Nothing -> do
    function <- gets (Map.lookup name . functions)
    case function of
      Nothing -> lift (Left ("LLVM unbound identity: " ++ show name))
      Just f -> do
        code <- wrapper name f
        env <- environment scope (A.captures f)
        Binding <$> call "@mlf_closure" [pointer code,pointer env] <*> pure True

forceBinding :: Binding -> Build String
forceBinding binding
  | evaluated binding = pure (operand binding)
  | otherwise = call "@mlf_force" [pointer (operand binding)]

environment :: Scope -> [X.Name] -> Build String
environment _ [] = pure "null"
environment scope names = do
  env <- call "@mlf_env_new" [number (length names)]
  forM_ (zip [0..] names) $ \(index,name) -> do
    value <- operand <$> lookupName scope name
    emit ("  call void @mlf_env_set(" ++ intercalate ", " [pointer env,number index,pointer value] ++ ")")
  pure env

readEnvironment :: [X.Name] -> Build Scope
readEnvironment names = Map.fromList <$> forM (zip [0..] names) (\(index,n) -> do
  value <- call "@mlf_env_get" ["ptr %env",number index]
  pure (n,Binding value False))

callback :: [X.Name] -> Maybe X.Name -> X.Erased -> Build String
callback captures argument body = do
  name <- fresh "@mlf.code."
  definition name ["ptr %env","ptr %arg"] $ do
    scope <- readEnvironment captures
    evaluate (maybe scope (\n -> Map.insert n (Binding "%arg" False) scope) argument) body
  pure name

worker :: X.Name -> A.Function -> Build String
worker name f = do
  let symbol = "@mlf.worker." ++ show (X.nameId name)
      names = A.captures f ++ A.parameters f
      registers = ["%a" ++ show i | i <- [0 :: Int .. length names - 1]]
  seen <- gets (Set.member name . workers)
  unless seen $ do
    modify' (\s -> s { workers = Set.insert name (workers s) })
    inline <- gets inlinePrimitives
    native <- gets (Set.member name . numericKernels)
    when native (modify' (\s -> s { inlinePrimitives = False }))
    definition symbol (map pointer registers) $
      evaluate (Map.fromList [(n,Binding r (Set.member n (A.strict f))) | (n,r) <- zip names registers]) (A.functionBody f)
    modify' (\s -> s { inlinePrimitives = inline })
  pure symbol

-- The wrapper retains the ordinary unary closure ABI for escaping functions.
-- Only its final application enters the worker and forces strict arguments.
wrapper :: X.Name -> A.Function -> Build String
wrapper name f = do
  previous <- gets (Map.lookup name . wrappers)
  case previous of
    Just symbol -> pure symbol
    Nothing -> do
      symbol <- fresh "@mlf.curry."
      modify' (\s -> s { wrappers = Map.insert name symbol (wrappers s) })
      buildWrapper symbol (A.captures f) (A.parameters f)
      pure symbol
  where
    buildWrapper _ _ [] = lift (Left "LLVM empty function wrapper")
    buildWrapper symbol captured (arg:rest) = definition symbol ["ptr %env","ptr %arg"] $ do
      saved <- readEnvironment captured
      let scope = Map.insert arg (Binding "%arg" False) saved
      if null rest then invoke scope name f (map X.EVar (A.parameters f)) else do
        next <- fresh "@mlf.curry."
        buildWrapper next (captured ++ [arg]) rest
        env <- environment scope (captured ++ [arg])
        call "@mlf_closure" [pointer next,pointer env]

invoke :: Scope -> X.Name -> A.Function -> [X.Erased] -> Build String
invoke scope name f args = do
  native <- gets (Set.member name . numericKernels)
  if native then kernelAction scope name f args else invokeOrdinary scope name f args

invokeOrdinary :: Scope -> X.Name -> A.Function -> [X.Erased] -> Build String
invokeOrdinary scope name f args = do
  symbol <- worker name f
  captured <- forM (A.captures f) $ \n -> lookupName scope n >>= \b ->
    if Set.member n (A.strict f) then forceBinding b else pure (operand b)
  values <- forM (zip (A.parameters f) args) $ \(n,a) ->
    if Set.member n (A.strict f) then evaluate scope a else thunk scope a
  call symbol (map pointer (captured ++ values))

-- A native action is repeatable, just like an ordinary IO description. Its
-- entry peeks at arguments without evaluating them; an unevaluated argument
-- takes the original lazy worker. Only the successful guard enters the eager
-- numeric region, so unused errors/divergence cannot move across IO effects.
kernelAction :: Scope -> X.Name -> A.Function -> [X.Erased] -> Build String
kernelAction scope name f args = do
  old <- gets (Map.lookup name . kernelEntries)
  entry <- case old of
    Just symbol -> pure symbol
    Nothing -> do
      symbol <- fresh "@mlf.numeric.entry."
      modify' (\s -> s { kernelEntries = Map.insert name symbol (kernelEntries s) })
      let names = A.captures f ++ A.parameters f
      definition symbol ["ptr %env","ptr %arg"] $ do
        saved <- readEnvironment names
        values <- mapM (\n -> call "@mlf_peek" [pointer (operand (saved Map.! n))]) names
        checks <- mapM (\v -> result ("icmp ne ptr " ++ v ++ ", null")) values
        ready <- foldM (\a b -> result ("and i1 " ++ a ++ ", " ++ b)) "true" checks
        choose "ptr" ready
          (do code <- kernelWorker name f
              value <- call code (map pointer values)
              call "@mlf_prim1" [number 0,pointer value])
          (invokeOrdinary saved name f (map X.EVar (A.parameters f)))
      pure symbol
  captured <- forM (A.captures f) $ \n -> lookupName scope n >>= \b ->
    if Set.member n (A.strict f) then forceBinding b else pure (operand b)
  values <- forM (zip (A.parameters f) args) $ \(n,a) ->
    if Set.member n (A.strict f) then evaluate scope a else thunk scope a
  env <- call "@mlf_env_new" [number (length captured + length values)]
  forM_ (zip [0..] (captured ++ values)) $ \(i,v) ->
    emit ("  call void @mlf_env_set(" ++ intercalate ", " [pointer env,number i,pointer v] ++ ")")
  call "@mlf_native_io" [pointer entry,pointer env]

data Scalar = Boxed String | Floating String
type NumericScope = Map.Map X.Name Scalar

boxed :: Scalar -> Build String
boxed (Boxed v) = pure v
boxed (Floating v) = call "@mlf_double" ["double " ++ v]

floating :: Scalar -> Build String
floating (Floating v) = pure v
floating (Boxed v) = loadAt "double" v 24

kernelWorker :: X.Name -> A.Function -> Build String
kernelWorker name f = do
  let symbol = "@mlf.numeric." ++ show (X.nameId name)
      names = A.captures f ++ A.parameters f
      registers = ["%a" ++ show i | i <- [0 :: Int .. length names - 1]]
  seen <- gets (Set.member name . kernelWorkers)
  unless seen $ do
    modify' (\s -> s { kernelWorkers = Set.insert name (kernelWorkers s) })
    definition symbol (map pointer registers) $
      executeNumeric (Map.fromList (zip names (map Boxed registers))) (A.functionBody f) >>= boxed
  pure symbol

numericValue :: NumericScope -> X.Name -> Build Scalar
numericValue scope n = maybe (lift (Left ("LLVM numeric region unbound identity: " ++ show n))) pure (Map.lookup n scope)

numericCondition :: Scalar -> Build String
numericCondition v = boxed v >>= \p -> result ("icmp eq ptr " ++ p ++ ", " ++ immediate 6)

numericChoose :: String -> Build Scalar -> Build Scalar -> Build Scalar
numericChoose condition yes no = Boxed <$> choose "ptr" condition (yes >>= boxed) (no >>= boxed)

-- No allocation is needed for array reads or floating intermediates. A
-- Double is boxed only at a region's result/argument boundary. Int retains
-- the ordinary checked tagged representation with arbitrary-precision fallback.
scalarValue :: NumericScope -> X.Erased -> Build Scalar
scalarValue scope expression = case expression of
  X.EVar n -> numericValue scope n
  X.EInt n -> do
    v <- evaluate Map.empty expression
    when (n >= negate (2^(62::Int)) && n < 2^(62::Int)) (recordRange v (n,n))
    pure (Boxed v)
  X.EDouble n -> let bits = showHex (castDoubleToWord64 n) ""
                in pure (Floating ("0x" ++ replicate (16 - length bits) '0' ++ bits))
  X.ELet n a b -> do
    v <- scalarValue scope a
    scalarValue (Map.insert n v scope) b
  _ -> case applications expression of
    (X.EPrimitive P.AddInt,[a,X.EInt 0]) -> scalarValue scope a
    (X.EPrimitive P.AddInt,[X.EInt 0,a]) -> scalarValue scope a
    (X.EPrimitive P.SubInt,[a,X.EInt 0]) -> scalarValue scope a
    (X.EPrimitive P.EqInt,[X.EVar a,X.EVar b]) | a == b -> pure (Boxed (immediate 6))
    (X.EPrimitive P.IfThenElse,[c,a,b]) -> do
      condition <- scalarValue scope c >>= numericCondition
      numericChoose condition (scalarValue scope a) (scalarValue scope b)
    (X.EPrimitive p,args) -> do
      values <- mapM (scalarValue scope) args
      case (p,values) of
        (P.IntToDouble,[a]) -> do
          v <- boxed a
          bits <- result ("ptrtoint ptr " ++ v ++ " to i64")
          tag <- result ("and i64 " ++ bits ++ ", 1") >>= \x -> result ("icmp ne i64 " ++ x ++ ", 0")
          Floating <$> choose "double" tag
            (result ("ashr i64 " ++ bits ++ ", 1") >>= \x -> result ("sitofp i64 " ++ x ++ " to double"))
            (result ("call double @mlf_int_to_double(ptr " ++ v ++ ")"))
        (P.SqrtDouble,[a]) -> do
          x <- floating a
          Floating <$> result ("call double @llvm.sqrt.f64(double " ++ x ++ ")")
        (_,[a,b]) | p `elem` [P.AddDouble,P.SubDouble,P.MulDouble,P.DivDouble,P.EqDouble,P.LtDouble] -> do
          x <- floating a; y <- floating b
          if p == P.EqDouble || p == P.LtDouble then do
            test <- result ("fcmp " ++ (if p == P.EqDouble then "oeq" else "olt") ++ " double " ++ x ++ ", " ++ y)
            Boxed <$> result ("select i1 " ++ test ++ ", ptr " ++ immediate 6 ++ ", ptr " ++ immediate 2)
          else do
            let op = case p of P.AddDouble -> "fadd"; P.SubDouble -> "fsub"; P.MulDouble -> "fmul"; _ -> "fdiv"
            Floating <$> result (op ++ " double " ++ x ++ ", " ++ y)
        _ -> do
          vs <- mapM boxed values
          Boxed <$> case (p,vs) of
            (_,[a,b]) | p `elem` [P.AddInt,P.SubInt,P.EqInt,P.LtInt] -> numericInteger p a b
            _ -> call ("@mlf_prim" ++ show (length args)) (number (primitiveCode p) : map pointer vs)
    (X.EVar n,args) -> do
      fs <- gets functions
      f <- maybe (lift (Left "LLVM missing numeric function")) pure (Map.lookup n fs)
      values <- mapM (scalarValue scope) args
      scalarValue (Map.union (Map.fromList (zip (A.parameters f) values)) scope) (A.functionBody f)
    (X.EConstructor c,args) | not (null args) -> do
      values <- mapM (scalarValue scope >=> boxed) args
      (tag,arity) <- lookupConstructor c
      if arity == length args && arity <= 2 then
        Boxed <$> call ("@mlf_constructor" ++ show arity) (number tag : map pointer values)
      else do
        constructor <- call "@mlf_constructor" [number tag,number arity]
        Boxed <$> foldM (\f a -> call "@mlf_application" [pointer f,pointer a] >>= \v ->
          call "@mlf_force" [pointer v]) constructor values
    _ -> Boxed <$> evaluate Map.empty expression

executeNumeric :: NumericScope -> X.Erased -> Build Scalar
executeNumeric scope expression = case expression of
  X.ELet n a b -> scalarValue scope a >>= \v -> executeNumeric (Map.insert n v scope) b
  X.ELetRec _ b -> executeNumeric scope b
  _ -> case applications expression of
    (X.EPrimitive P.IOBind,[a,X.EAbs n b]) -> do
      v <- executeNumeric scope a
      executeNumeric (Map.insert n v scope) b
    (X.EPrimitive P.IOReturn,[a]) -> scalarValue scope a
    (X.EPrimitive P.IfThenElse,[c,a,b]) -> do
      condition <- scalarValue scope c >>= numericCondition
      numericChoose condition (executeNumeric scope a) (executeNumeric scope b)
    (X.EVar n,args) -> do
      fs <- gets functions
      let f = fs Map.! n
      code <- kernelWorker n f
      captured <- mapM (numericValue scope >=> boxed) (A.captures f)
      values <- mapM (scalarValue scope >=> boxed) args
      Boxed <$> call code (map pointer (captured ++ values))
    (X.EPrimitive p,args) | p `elem` [P.ReadIntArray,P.ReadDoubleArray,P.WriteIntArray,P.WriteDoubleArray,
                                    P.LengthIntArray,P.LengthDoubleArray,
                                    P.ReadByteArray,P.WriteByteArray,P.LengthByteArray] -> do
      values <- mapM (scalarValue scope) args
      array <- case values of a:_ -> boxed a; [] -> lift (Left "LLVM missing array operand")
      (len,cells) <- arrayView array
      if p `elem` [P.LengthIntArray,P.LengthDoubleArray,P.LengthByteArray] then do
        bits <- result ("shl i64 " ++ len ++ ", 1") >>= \v -> result ("or i64 " ++ v ++ ", 1")
        Boxed <$> result ("inttoptr i64 " ++ bits ++ " to ptr")
      else do
        index <- boxed (values !! 1)
        bits <- result ("ptrtoint ptr " ++ index ++ " to i64")
        i <- result ("ashr i64 " ++ bits ++ ", 1")
        -- Valid indices always fit the immediate range (length <= 2^60-1).
        tag <- result ("and i64 " ++ bits ++ ", 1") >>= \v -> result ("icmp ne i64 " ++ v ++ ", 0")
        bounds <- result ("icmp ult i64 " ++ i ++ ", " ++ len)
        ok <- result ("and i1 " ++ tag ++ ", " ++ bounds)
        valid <- fresh "array.valid."; invalid <- fresh "array.invalid."
        emit ("  br i1 " ++ ok ++ ", label %" ++ valid ++ ", label %" ++ invalid)
        label invalid
        emit "  call void @mlf_bounds_failure()"
        emit "  unreachable"
        label valid
        recordRange index (0,2^(60::Int)-2)
        let byteArray = p `elem` [P.ReadByteArray,P.WriteByteArray]
        address <- result ("getelementptr " ++ (if byteArray then "i8" else "i64") ++ ", ptr " ++ cells ++ ", i64 " ++ i)
        case p of
          P.ReadByteArray -> do
            x <- result ("load i8, ptr " ++ address ++ ", align 1")
            wide <- result ("zext i8 " ++ x ++ " to i64")
            tagged <- result ("shl i64 " ++ wide ++ ", 1") >>= \v -> result ("or i64 " ++ v ++ ", 1")
            v <- result ("inttoptr i64 " ++ tagged ++ " to ptr")
            recordRange v (0,255)
            pure (Boxed v)
          P.WriteByteArray -> do
            v <- boxed (values !! 2)
            x <- result ("call i8 @mlf_byte(ptr " ++ v ++ ")")
            emit ("  store i8 " ++ x ++ ", ptr " ++ address ++ ", align 1")
            pure (Boxed (immediate 4))
          P.ReadDoubleArray -> Floating <$> result ("load double, ptr " ++ address ++ ", align 8")
          P.ReadIntArray -> Boxed <$> result ("load ptr, ptr " ++ address ++ ", align 8")
          P.WriteDoubleArray -> do
            v <- floating (values !! 2)
            emit ("  store double " ++ v ++ ", ptr " ++ address ++ ", align 8")
            pure (Boxed (immediate 4))
          _ -> do
            v <- boxed (values !! 2)
            emit ("  store ptr " ++ v ++ ", ptr " ++ address ++ ", align 8")
            pure (Boxed (immediate 4))
    _ -> lift (Left "LLVM unsupported numeric IO region")

recordRange :: String -> (Integer,Integer) -> Build ()
recordRange value bounds = modify' (\s -> s { scalarRanges = Map.insertWith
  (\(a,b) (c,d) -> (max a c,min b d)) value bounds (scalarRanges s) })

-- Successful checked indexing proves a small nonnegative integer. Carry that
-- proof to subsequent scalar operations in the same dominating region, so
-- field offsets do not repeat overflow/GMP branches. No assumption is made
-- about an unchecked argument or a value loaded from an IntArray.
numericInteger :: P.Primitive -> String -> String -> Build String
numericInteger p a b = do
  facts <- gets scalarRanges
  case (Map.lookup a facts,Map.lookup b facts) of
    (Just (lo,hi),Just (lo',hi')) -> do
      let bounds = if p == P.AddInt then (lo+lo',hi+hi') else (lo-hi',hi-lo')
          fits = fst bounds >= negate (2^(62::Int)) && snd bounds < 2^(62::Int)
      if p `elem` [P.EqInt,P.LtInt] || fits then do
        x <- result ("ptrtoint ptr " ++ a ++ " to i64")
        y <- result ("ptrtoint ptr " ++ b ++ " to i64")
        if p `elem` [P.EqInt,P.LtInt] then do
          test <- result ("icmp " ++ (if p == P.EqInt then "eq" else "slt") ++ " i64 " ++ x ++ ", " ++ y)
          result ("select i1 " ++ test ++ ", ptr " ++ immediate 6 ++ ", ptr " ++ immediate 2)
        else do
          offset <- result ("sub i64 " ++ y ++ ", 1")
          bits <- result ((if p == P.AddInt then "add" else "sub") ++ " nsw i64 " ++ x ++ ", " ++ offset)
          v <- result ("inttoptr i64 " ++ bits ++ " to ptr")
          recordRange v bounds
          pure v
      else integerOperation p a b
    _ -> integerOperation p a b

-- Atoms and constructors already are values. A compound lazy expression is
-- one memoized callback, rather than a heap application at every syntax node.
thunk :: Scope -> X.Erased -> Build String
thunk scope expression = case expression of
  X.EVar n -> operand <$> lookupName scope n
  X.EInt _ -> evaluate scope expression
  X.EDouble _ -> evaluate scope expression
  X.EBool _ -> evaluate scope expression
  X.EString _ -> evaluate scope expression
  X.EPrimitive _ -> evaluate scope expression
  X.EConstructor _ -> evaluate scope expression
  X.EAbs _ _ -> evaluate scope expression
  X.EEvidenceHole _ -> lift (Left "LLVM unresolved dictionary evidence")
  _ -> case applications expression of
    (X.EConstructor c,args) -> do
      (_,arity) <- lookupConstructor c
      if length args == arity then evaluate scope expression else suspended
    _ -> suspended
  where
    suspended = do
      fs <- gets functions
      let captures = Set.toAscList (A.needed fs expression)
      code <- callback captures Nothing expression
      env <- environment scope captures
      call "@mlf_thunk" [pointer code,pointer env]

evaluate :: Scope -> X.Erased -> Build String
evaluate scope expression = case expression of
  X.EVar n -> lookupName scope n >>= forceBinding
  X.EInt n | n >= negate (2 ^ (62 :: Int)) && n < 2 ^ (62 :: Int) -> pure (immediate (2*n+1))
           | otherwise -> do
               (literal,_) <- stringConstant (show n)
               call "@mlf_integer" [pointer literal]
  X.EDouble n -> do
    let bits = showHex (castDoubleToWord64 n) ""
    call "@mlf_double" ["double 0x" ++ replicate (16 - length bits) '0' ++ bits]
  X.EBool b -> pure (immediate (if b then 6 else 2))
  X.EString text -> do
    (literal,size) <- stringConstant text
    call "@mlf_string" [pointer literal,number size]
  X.EPrimitive p -> call "@mlf_primitive" [number (primitiveCode p)]
  X.EConstructor c -> do
    (tag,arity) <- lookupConstructor c
    if arity == 0 then pure (immediate (toInteger tag * 8 + 4)) else
      call "@mlf_constructor" [number tag,number arity]
  X.EAbs n body -> do
    fs <- gets functions
    let captures = Set.toAscList (Set.delete n (A.needed fs body))
    code <- callback captures (Just n) body
    env <- environment scope captures
    call "@mlf_closure" [pointer code,pointer env]
  X.ELet n rhs body -> do
    fs <- gets functions
    if Map.member n fs then evaluate scope body else do
      let strict = Set.member n (A.demanded fs body)
      value <- if strict then evaluate scope rhs else thunk scope rhs
      evaluate (Map.insert n (Binding value strict) scope) body
  X.ELetRec bindings body -> do
    fs <- gets functions
    let values = [(n,a) | (n,a) <- bindings, Map.notMember n fs]
    holes <- forM values $ \(n,_) -> do
      hole <- call "@mlf_hole" []
      pure (n,Binding hole False)
    let recursive = Map.union (Map.fromList holes) scope
    forM_ values $ \(n,rhs) -> do
      value <- thunk recursive rhs
      hole <- operand <$> lookupName recursive n
      emit ("  call void @mlf_fill(ptr " ++ hole ++ ", ptr " ++ value ++ ")")
    evaluate recursive body
  X.ECase scrutinee alternatives -> case alternatives of
    [X.ErasedAlternative (X.DefaultPattern name) body] -> do
      value <- thunk scope scrutinee
      evaluate (maybe scope (\n -> Map.insert n (Binding value False) scope) name) body
    _ -> do
      value <- evaluate scope scrutinee
      tag <- constructorTag value
      labelled <- forM alternatives $ \a -> (,) <$> fresh "case." <*> pure a
      missing <- fresh "case.missing."
      join <- fresh "case.join."
      let fallback = case [l | (l,X.ErasedAlternative (X.DefaultPattern _) _) <- labelled] of
            l:_ -> l
            [] -> missing
      entries <- forM [(l,c) | (l,X.ErasedAlternative (X.ConstructorPattern c _) _) <- labelled] $ \(l,c) -> do
        (identity,_) <- lookupConstructor c
        pure ("    i64 " ++ show identity ++ ", label %" ++ l)
      emit ("  switch i64 " ++ tag ++ ", label %" ++ fallback ++ " [")
      mapM_ emit entries
      emit "  ]"
      incoming <- forM labelled $ \(l,X.ErasedAlternative pattern' body) -> do
        label l
        local <- case pattern' of
          X.DefaultPattern name -> pure (maybe scope (\n -> Map.insert n (Binding value True) scope) name)
          X.ConstructorPattern c names -> do
            (_,arity) <- lookupConstructor c
            foldM (\env (index,name) -> case name of
              Nothing -> pure env
              Just n -> do
                field <- if arity <= 2 then loadAt "ptr" value (32 + 8*index) else
                  call "@mlf_field" [pointer value,number index]
                pure (Map.insert n (Binding field False) env)) scope (zip [0..] names)
        v <- evaluate local body
        from <- gets block
        emit ("  br label %" ++ join)
        pure (v,from)
      when (fallback == missing) $ do
        label missing
        emit "  call void @mlf_match_failure()"
        emit "  unreachable"
      label join
      phi "ptr" incoming
  X.EApp _ _ -> application scope expression
  X.EEvidenceHole _ -> lift (Left "LLVM unresolved dictionary evidence")

application :: Scope -> X.Erased -> Build String
application scope expression = do
  fs <- gets functions
  case applications expression of
    (X.EVar n,args) | Just f <- Map.lookup n fs, length args == length (A.parameters f) -> invoke scope n f args
    (X.EPrimitive P.IfThenElse,[c,a,b]) -> do
      condition <- evaluate scope c
      truth <- result ("call i64 @mlf_truth(ptr " ++ condition ++ ")")
      test <- result ("icmp ne i64 " ++ truth ++ ", 0")
      choose "ptr" test (evaluate scope a) (evaluate scope b)
    (X.EPrimitive p,args) | length args == A.primitiveArity p -> do
      let strict = P.primitiveStrict p
      values <- mapM (if strict then evaluate scope else thunk scope) args
      inline <- gets inlinePrimitives
      if not inline then call ("@mlf_prim" ++ show (length args)) (number (primitiveCode p) : map pointer values)
      else case (p,values) of
        (P.AddInt,[a,b]) -> integerOperation p a b
        (P.SubInt,[a,b]) -> integerOperation p a b
        (P.EqInt,[a,b]) -> integerOperation p a b
        (P.LtInt,[a,b]) -> integerOperation p a b
        (P.SqrtDouble,[a]) -> do
          x <- loadAt "double" a 24
          n <- result ("call double @llvm.sqrt.f64(double " ++ x ++ ")")
          call "@mlf_double" ["double " ++ n]
        (_, [a,b]) | p `elem` [P.AddDouble,P.SubDouble,P.MulDouble,P.DivDouble,P.EqDouble,P.LtDouble] ->
          doubleOperation p a b
        _ -> call ("@mlf_prim" ++ show (length args)) (number (primitiveCode p) : map pointer values)
    (X.EConstructor c,args) -> do
      (tag,arity) <- lookupConstructor c
      if arity <= 2 && length args == arity then do
        fields <- mapM (thunk scope) args
        call ("@mlf_constructor" ++ show arity) (number tag : map pointer fields)
      else generic
    _ -> generic
  where
    generic = case expression of
      X.EApp f a -> do
        function <- thunk scope f
        argument <- thunk scope a
        app <- call "@mlf_application" [pointer function,pointer argument]
        call "@mlf_force" [pointer app]
      _ -> lift (Left "LLVM expected application")

phi :: String -> [(String,String)] -> Build String
phi ty incoming = result ("phi " ++ ty ++ " " ++ intercalate ", " ["[ " ++ v ++ ", %" ++ l ++ " ]" | (v,l) <- incoming])

choose :: String -> String -> Build String -> Build String -> Build String
choose ty condition yes no = do
  before <- gets scalarRanges
  viewsBefore <- gets arrayViews
  yesLabel <- fresh "yes."
  noLabel <- fresh "no."
  join <- fresh "join."
  emit ("  br i1 " ++ condition ++ ", label %" ++ yesLabel ++ ", label %" ++ noLabel)
  label yesLabel
  a <- yes
  aBlock <- gets block
  afterYes <- gets scalarRanges
  viewsYes <- gets arrayViews
  emit ("  br label %" ++ join)
  label noLabel
  modify' (\s -> s { scalarRanges = before, arrayViews = viewsBefore })
  b <- no
  bBlock <- gets block
  afterNo <- gets scalarRanges
  viewsNo <- gets arrayViews
  emit ("  br label %" ++ join)
  label join
  modify' (\s -> s { scalarRanges = Map.intersectionWith
    (\(lo,hi) (lo',hi') -> (min lo lo',max hi hi')) afterYes afterNo,
    arrayViews = Map.filterWithKey (\key value -> Map.lookup key viewsNo == Just value) viewsYes })
  phi ty [(a,aBlock),(b,bBlock)]

-- Layout is a small explicit 64-bit ABI, asserted by the runtime. Typed,
-- evaluated constructor cases cannot scrutinize partial constructors.
loadAt :: String -> String -> Int -> Build String
loadAt ty value offset = do
  address <- result ("getelementptr i8, ptr " ++ value ++ ", i64 " ++ show offset)
  result ("load " ++ ty ++ ", ptr " ++ address ++ ", align 8")

-- Reuse descriptor loads only along dominated paths within this function.
-- Cells may alias and mutate, but descriptors cannot change while a native
-- region executes (no collection occurs on that stack). This is deliberately
-- not invariant.load metadata: the pool can reuse the storage after GC.
arrayView :: String -> Build (String,String)
arrayView array = do
  known <- gets (Map.lookup array . arrayViews)
  case known of
    Just view -> pure view
    Nothing -> do
      len <- loadAt "i64" array 24
      cells <- loadAt "ptr" array 32
      let view = (len,cells)
      modify' (\s -> s { arrayViews = Map.insert array view (arrayViews s) })
      pure view

constructorTag :: String -> Build String
constructorTag value = do
  bits <- result ("ptrtoint ptr " ++ value ++ " to i64")
  low <- result ("and i64 " ++ bits ++ ", 7")
  nullary <- result ("icmp eq i64 " ++ low ++ ", 4")
  choose "i64" nullary (result ("lshr i64 " ++ bits ++ ", 3")) (loadAt "i64" value 24)

integerOperation :: P.Primitive -> String -> String -> Build String
integerOperation p a b = do
  x <- result ("ptrtoint ptr " ++ a ++ " to i64")
  y <- result ("ptrtoint ptr " ++ b ++ " to i64")
  both <- result ("and i64 " ++ x ++ ", " ++ y)
  low <- result ("and i64 " ++ both ++ ", 1")
  small <- result ("icmp ne i64 " ++ low ++ ", 0")
  choose "ptr" small (fast x y) slow
  where
    slow = call (case p of P.AddInt -> "@mlf_add_int"; P.SubInt -> "@mlf_sub_int"; P.EqInt -> "@mlf_eq_int"; _ -> "@mlf_lt_int") [pointer a,pointer b]
    fast x y | p == P.EqInt || p == P.LtInt = do
      comparison <- result ("icmp " ++ (if p == P.EqInt then "eq" else "slt") ++ " i64 " ++ x ++ ", " ++ y)
      result ("select i1 " ++ comparison ++ ", ptr " ++ immediate 6 ++ ", ptr " ++ immediate 2)
    fast x y = do
      untagged <- result ("sub i64 " ++ y ++ ", 1")
      pair <- result ("call { i64, i1 } @llvm.s" ++ (if p == P.AddInt then "add" else "sub") ++ ".with.overflow.i64(i64 " ++ x ++ ", i64 " ++ untagged ++ ")")
      sum' <- result ("extractvalue { i64, i1 } " ++ pair ++ ", 0")
      overflow <- result ("extractvalue { i64, i1 } " ++ pair ++ ", 1")
      choose "ptr" overflow slow (result ("inttoptr i64 " ++ sum' ++ " to ptr"))

doubleOperation :: P.Primitive -> String -> String -> Build String
doubleOperation p a b = do
  x <- loadAt "double" a 24
  y <- loadAt "double" b 24
  if p == P.EqDouble || p == P.LtDouble then do
    comparison <- result ("fcmp " ++ (if p == P.EqDouble then "oeq" else "olt") ++ " double " ++ x ++ ", " ++ y)
    result ("select i1 " ++ comparison ++ ", ptr " ++ immediate 6 ++ ", ptr " ++ immediate 2)
  else do
    let opcode = case p of P.AddDouble -> "fadd"; P.SubDouble -> "fsub"; P.MulDouble -> "fmul"; _ -> "fdiv"
    n <- result (opcode ++ " double " ++ x ++ ", " ++ y)
    call "@mlf_double" ["double " ++ n]

-- Length-delimited UTF-8 preserves embedded NULs and escapes LLVM syntax.
stringConstant :: String -> Build (String,Int)
stringConstant text = do
  bytes <- lift (concat <$> mapM utf8 text)
  name <- fresh "@mlf.bytes."
  let escape byte = '\\' : (if byte < 16 then "0" else "") ++ showHex byte ""
      text' = name ++ " = private unnamed_addr constant [" ++ show (length bytes + 1) ++
        " x i8] c\"" ++ concatMap escape (bytes ++ [0]) ++ "\", align 1"
  modify' (\s -> s { constants = text' : constants s })
  pure (name,length bytes)
  where
    utf8 c
      | n >= 0xd800 && n <= 0xdfff = Left "LLVM string contains an invalid Unicode scalar"
      | n < 0x80 = pure [n]
      | n < 0x800 = pure [0xc0 + shiftR n 6,continuation n]
      | n < 0x10000 = pure [0xe0 + shiftR n 12,continuation (shiftR n 6),continuation n]
      | otherwise = pure [0xf0 + shiftR n 18,continuation (shiftR n 12),continuation (shiftR n 6),continuation n]
      where n = ord c
    continuation n = 0x80 + (n .&. 0x3f)

primitiveCode :: P.Primitive -> Int
primitiveCode p = case p of
  P.IOReturn -> 0; P.IOBind -> 1; P.PutStr -> 2; P.PutStrLn -> 3
  P.GetLine -> 4; P.PrintInt -> 5; P.ConcatString -> 6; P.ShowInt -> 7
  P.AddInt -> 8; P.SubInt -> 9; P.EqInt -> 10; P.LtInt -> 11
  P.EqString -> 12; P.IfThenElse -> 13
  P.MulInt -> 14; P.QuotInt -> 15; P.RemInt -> 16; P.ReadInt -> 17
  P.AddDouble -> 18; P.SubDouble -> 19; P.MulDouble -> 20; P.DivDouble -> 21; P.SqrtDouble -> 22
  P.EqDouble -> 23; P.LtDouble -> 24; P.IntToDouble -> 25; P.FormatDouble -> 26
  P.NewIntArray -> 27; P.ReadIntArray -> 28; P.WriteIntArray -> 29; P.LengthIntArray -> 30
  P.NewDoubleArray -> 31; P.ReadDoubleArray -> 32; P.WriteDoubleArray -> 33; P.LengthDoubleArray -> 34
  P.NewByteArray -> 35; P.ReadByteArray -> 36; P.WriteByteArray -> 37; P.LengthByteArray -> 38
  P.ByteArrayFromString -> 39; P.PutBytes -> 40

runtimeDeclarations :: [String]
runtimeDeclarations =
  [ "declare ptr @mlf_env_new(i64)", "declare void @mlf_env_set(ptr, i64, ptr)"
  , "declare ptr @mlf_env_get(ptr, i64)", "declare ptr @mlf_thunk(ptr, ptr)"
  , "declare ptr @mlf_closure(ptr, ptr)", "declare ptr @mlf_application(ptr, ptr)"
  , "declare ptr @mlf_hole()", "declare void @mlf_fill(ptr, ptr)"
  , "declare ptr @mlf_integer(ptr)", "declare ptr @mlf_string(ptr, i64)"
  , "declare ptr @mlf_double(double)", "declare double @llvm.sqrt.f64(double)"
  , "declare double @mlf_int_to_double(ptr)"
  , "declare i8 @mlf_byte(ptr)"
  , "declare ptr @mlf_peek(ptr)", "declare ptr @mlf_native_io(ptr, ptr)"
  , "declare void @mlf_bounds_failure() noreturn"
  , "declare ptr @mlf_primitive(i64)", "declare ptr @mlf_prim1(i64, ptr)"
  , "declare ptr @mlf_prim2(i64, ptr, ptr)", "declare i64 @mlf_truth(ptr)"
  , "declare ptr @mlf_prim3(i64, ptr, ptr, ptr)"
  , "declare ptr @mlf_force(ptr)", "declare ptr @mlf_add_int(ptr, ptr)"
  , "declare ptr @mlf_sub_int(ptr, ptr)", "declare ptr @mlf_eq_int(ptr, ptr)"
  , "declare ptr @mlf_lt_int(ptr, ptr)", "declare ptr @mlf_constructor(i64, i64)"
  , "declare ptr @mlf_constructor1(i64, ptr)", "declare ptr @mlf_constructor2(i64, ptr, ptr)"
  , "declare ptr @mlf_field(ptr, i64)", "declare void @mlf_match_failure() noreturn"
  , "declare { i64, i1 } @llvm.sadd.with.overflow.i64(i64, i64)"
  , "declare { i64, i1 } @llvm.ssub.with.overflow.i64(i64, i64)"
  , "declare i32 @mlf_run(ptr, i64)", ""
  ]
