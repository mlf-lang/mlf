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
import MLF.LLVM.Optimize (applications, free)
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
  , numericKernels :: Set.Set X.Name, kernelWorkers :: Set.Set (X.Name,[NativeMode])
  , collectingKernels :: Set.Set X.Name
  , kernelEntries :: Map.Map X.Name String
  , inlinePrimitives :: Bool
  , scalarRanges :: Map.Map String (Integer,Integer)
  , arrayViews :: Map.Map String (String,String)
  , unboxedDoubles :: Map.Map String String
  }
type Build = StateT Output (Either String)

generate :: Constructors -> X.Erased -> Either String (String,[String])
generate cs term = do
  let fs = A.analyze term
      ks = K.kernels fs
  (entry,out) <- runStateT (callback [] Nothing term)
    (Output 0 [] "entry" [] [] cs fs Set.empty Map.empty ks Set.empty (K.collecting fs ks) Map.empty True Map.empty Map.empty Map.empty)
  pure (entry, runtimeDeclarations ++ aliasMetadata ++ reverse (constants out) ++ reverse (definitions out))

-- Managed headers and external array storage are disjoint allocations. The
-- source language cannot cast an array cell pointer to a managed object.
-- Do not claim that two arrays are disjoint: aliases retain their usual IO
-- semantics. Runtime calls remain conservative, including pool reuse by GC.
aliasMetadata :: [String]
aliasMetadata =
  [ "!0 = !{!\"MLF storage\"}"
  , "!1 = !{!\"managed object\", !0}"
  , "!2 = !{!\"array cells\", !0}"
  , "!3 = !{!1, !1, i64 0}"
  , "!4 = !{!2, !2, i64 0}"
  ]

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
definition name args body = definitionBody name args $ do
  value <- body
  emit ("  ret ptr " ++ value)

-- A terminating body can emit returns directly in both branches, preserving
-- tail position without relying on LLVM to collapse a result phi first.
definitionBody :: String -> [String] -> Build () -> Build ()
definitionBody name args body = do
  saved <- gets (\s -> (instructions s,block s,scalarRanges s,arrayViews s,unboxedDoubles s))
  modify' (\s -> s { instructions = [], block = "entry", scalarRanges = Map.empty,
    arrayViews = Map.empty, unboxedDoubles = Map.empty })
  body
  code <- gets (reverse . instructions)
  collectors <- gets collectingKernels
  let collectingWorker = any ((== takeWhile (/= '.') (drop 13 name)) . show . X.nameId) (Set.toList collectors)
      attributes = if take 13 name == "@mlf.numeric." && take 19 name /= "@mlf.numeric.entry." && not collectingWorker then " alwaysinline" else ""
      text = unlines (["define private ptr " ++ name ++ "(" ++ intercalate ", " args ++ ")" ++ attributes ++ " {", "entry:"] ++ code ++ ["}"])
  let (savedInstructions,savedBlock,savedRanges,savedViews,savedDoubles) = saved
  modify' (\s -> s { instructions = savedInstructions, block = savedBlock,
    scalarRanges = savedRanges, arrayViews = savedViews, unboxedDoubles = savedDoubles,
    definitions = text : definitions s })

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
          (do value <- invokeKernel name f (map Boxed values)
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
data NativeMode = General | UnboxedDouble | NonnegativeInt | SmallIndex deriving (Eq,Ord)
type NumericScope = Map.Map X.Name Scalar

boxed :: Scalar -> Build String
boxed (Boxed v) = pure v
boxed (Floating v) = call "@mlf_double" ["double " ++ v]

floating :: Scalar -> Build String
floating (Floating v) = pure v
floating (Boxed v) = do
  old <- gets (Map.lookup v . unboxedDoubles)
  case old of
    Just x -> pure x
    Nothing -> do
      x <- loadAt "double" v 24
      modify' (\s -> s { unboxedDoubles = Map.insert v x (unboxedDoubles s) })
      pure x

-- Specialize the private ABI from values already produced by native code.
-- A Floating argument is known to be a binary64 value, so recursive calls
-- can carry it in SSA instead of allocating a box at every iteration.
-- A proven nonnegative tagged counter carries its range into the worker,
-- widened to the whole nonnegative tagged range. Only zero-tested parameters
-- get this mode: specializing every array offset duplicates loops needlessly.
-- The guarded public entry retains the general boxed ABI and lazy fallback.
invokeKernel :: X.Name -> A.Function -> [Scalar] -> Build String
invokeKernel name f arguments = do
  (code,values) <- kernelCall name f arguments
  call code (map scalarArgument values)

scalarArgument :: Scalar -> String
scalarArgument (Floating x) = "double " ++ x
scalarArgument (Boxed x) = pointer x

isFloating :: Scalar -> Bool
isFloating (Floating _) = True
isFloating (Boxed _) = False

kernelCall :: X.Name -> A.Function -> [Scalar] -> Build (String,[Scalar])
kernelCall name f arguments = do
  facts <- gets scalarRanges
  doubles <- gets unboxedDoubles
  -- Reuse a dominating payload read: it also proves the boxed argument's
  -- representation, so subsequent calls can use the unboxed private ABI.
  let values = [case v of Boxed p | Just x <- Map.lookup p doubles -> Floating x; _ -> v | v <- arguments]
  let counters = zeroTested (A.functionBody f)
      indices = integerParameters (A.functionBody f)
  collects <- gets (Set.member name . collectingKernels)
  let narrow = not collects && indexLoop (A.functionBody f) && and
        [case v of Boxed p -> maybe False (\(lo,hi) -> lo >= 0 && hi < 2^(31::Int)) (Map.lookup p facts); _ -> False |
          (n,v) <- zip (A.captures f ++ A.parameters f) values, Set.member n indices]
      mode _ (Floating _) = UnboxedDouble
      mode n (Boxed v) = case Map.lookup v facts of
        _ | narrow && Set.member n indices -> SmallIndex
        Just (lo,hi) | Set.member n counters && lo >= 0 && hi < 2^(62::Int) -> NonnegativeInt
        _ -> General
      requested = zipWith mode (A.captures f ++ A.parameters f) values
  variants <- gets kernelWorkers
  -- Bound specialization when recursive calls permute mixed representations.
  let specialized = any (/= General)
      overflow = specialized requested && Set.notMember (name,requested) variants &&
        length [() | (n,ms) <- Set.toList variants, n == name, specialized ms] >= 8
  actual <- if overflow then mapM (fmap Boxed . boxed) values else pure values
  code <- kernelWorker name f (if overflow then replicate (length values) General else requested)
  pure (code,actual)

zeroTested :: X.Erased -> Set.Set X.Name
zeroTested expression = case applications expression of
  (X.EPrimitive P.EqInt,[X.EVar n,X.EInt 0]) -> Set.singleton n
  (X.EPrimitive P.EqInt,[X.EInt 0,X.EVar n]) -> Set.singleton n
  _ -> case expression of
    X.EAbs _ b -> zeroTested b
    X.EApp a b -> zeroTested a `Set.union` zeroTested b
    X.ELet _ a b -> zeroTested a `Set.union` zeroTested b
    X.ELetRec _ b -> zeroTested b
    _ -> Set.empty

-- Resolved primitive signatures identify integer operands after erasure.
-- This is only a request for a dynamic range guard, never a type/range guess.
integerParameters :: X.Erased -> Set.Set X.Name
integerParameters expression = direct `Set.union` nested
  where
    direct = case applications expression of
      (X.EPrimitive p,args) -> Set.fromList
        [n | (i,X.EVar n) <- zip [0::Int ..] args, i `elem` positions p]
      _ -> Set.empty

    positions p
      | p `elem` [P.AddInt,P.SubInt,P.MulInt,P.QuotInt,P.RemInt,P.AndInt,P.EqInt,P.LtInt,P.NewIntArray,P.NewByteArray] = [0,1]
      | p `elem` [P.IntToDouble,P.NewDoubleArray] = [0]
      | p `elem` [P.ReadIntArray,P.ReadDoubleArray,P.ReadByteArray,P.ReadIntTable,P.WriteDoubleArray] = [1]
      | p `elem` [P.WriteIntArray,P.WriteByteArray,P.WriteIntTable,P.PutBytes] = [1,2]
      | otherwise = []
    nested = case expression of
      X.EAbs _ b -> integerParameters b
      X.EApp a b -> integerParameters a `Set.union` integerParameters b
      X.ELet _ a b -> integerParameters a `Set.union` integerParameters b
      X.ELetRec _ b -> integerParameters b
      _ -> Set.empty

-- Range versioning pays for itself in checked indexed integer/byte loops.
-- Avoid duplicating floating kernels or table operations, whose cost is
-- dominated by other work and whose private ABI is already specialized.
indexLoop :: X.Erased -> Bool
indexLoop expression = any (`elem` ps) [P.ReadByteArray,P.WriteByteArray,P.ReadIntArray,P.WriteIntArray] &&
  not (any (`elem` ps) [P.ReadIntTable,P.WriteIntTable,P.AddDouble,P.SubDouble,P.MulDouble,
    P.DivDouble,P.SqrtDouble,P.IntToDouble,P.ReadDoubleArray,P.WriteDoubleArray])
  where
    ps = primitives expression
    primitives e = case e of
      X.EPrimitive p -> [p]
      X.EAbs _ b -> primitives b
      X.EApp a b -> primitives a ++ primitives b
      X.ELet _ a b -> primitives a ++ primitives b
      X.ELetRec _ b -> primitives b
      _ -> []

kernelWorker :: X.Name -> A.Function -> [NativeMode] -> Build String
kernelWorker name f modes = do
  let symbol = "@mlf.numeric." ++ show (X.nameId name) ++
        if any (/= General) modes then "." ++ map suffix modes else ""
      suffix m = case m of General -> 'p'; UnboxedDouble -> 'd'; NonnegativeInt -> 'n'; SmallIndex -> 'i'
      names = A.captures f ++ A.parameters f
      registers = ["%a" ++ show i | i <- [0 :: Int .. length names - 1]]
      key = (name,modes)
  seen <- gets (Set.member key . kernelWorkers)
  unless seen $ do
    modify' (\s -> s { kernelWorkers = Set.insert key (kernelWorkers s) })
    let arguments = zipWith (\m r -> (if m == UnboxedDouble then "double " else "ptr ") ++ r) modes registers
        values = zipWith (\m r -> if m == UnboxedDouble then Floating r else Boxed r) modes registers
    definitionBody symbol arguments $ do
      collects <- gets (Set.member name . collectingKernels)
      when collects $ do
        let roots = [r | (m,r) <- zip modes registers, m /= UnboxedDouble]
        slots <- rootSlots roots
        emit ("  call void @mlf_gc_check(" ++ number (length roots) ++ ", ptr " ++ slots ++ ")")
      forM_ (zip modes registers) $ \(m,r) ->
        case m of
          NonnegativeInt -> recordRange r (0,2^(62::Int)-1)
          SmallIndex -> recordRange r (0,2^(31::Int)-1)
          _ -> pure ()
      let scope = Map.fromList (zip names values)
          integers = integerParameters (A.functionBody f)
          narrow = [i | (i,(n,m)) <- zip [0::Int ..] (zip names modes),
                        Set.member n integers, m == General || m == NonnegativeInt]
          narrowed = [if i `elem` narrow then SmallIndex else m | (i,m) <- zip [0::Int ..] modes]
          ordinary = executeNumericReturn modes scope (A.functionBody f)
          body = case K.byteCopy name f of
            Just ns -> copyBytesReturn scope ns ordinary
            Nothing -> ordinary
      variants <- gets kernelWorkers
      let allowed = Set.member (name,narrowed) variants ||
            length [() | (n,ms) <- Set.toList variants, n == name, any (/= General) ms] < 8
      if K.byteCopy name f /= Nothing || collects || not (indexLoop (A.functionBody f)) || null narrow || not allowed then body else do
        tests <- forM narrow $ \i -> do
          bits <- result ("ptrtoint ptr " ++ registers !! i ++ " to i64")
          tag <- result ("and i64 " ++ bits ++ ", 1") >>= \v -> result ("icmp ne i64 " ++ v ++ ", 0")
          range <- result ("icmp ult i64 " ++ bits ++ ", 4294967296")
          result ("and i1 " ++ tag ++ ", " ++ range)
        ready <- foldM (\a b -> result ("and i1 " ++ a ++ ", " ++ b)) "true" tests
        fast <- fresh "range.fast."; slow <- fresh "range.general."
        emit ("  br i1 " ++ ready ++ ", label %" ++ fast ++ ", label %" ++ slow)
        label fast
        code <- kernelWorker name f narrowed
        v <- result ("musttail call ptr " ++ code ++ "(" ++ intercalate ", " (map scalarArgument values) ++ ")")
        emit ("  ret ptr " ++ v)
        label slow
        body
  pure symbol

copyBytesReturn :: NumericScope -> [X.Name] -> Build () -> Build ()
copyBytesReturn scope names fallback = do
  values <- mapM (numericValue scope >=> boxed) names
  case values of
    [source,dest,end,offset,index] -> do
      (sourceLength,sourceCells) <- arrayView source
      (destLength,destCells) <- arrayView dest
      bits <- mapM (\v -> result ("ptrtoint ptr " ++ v ++ " to i64")) [end,offset,index]
      tests <- forM bits $ \b -> result ("and i64 " ++ b ++ ", 1") >>= \t -> result ("icmp ne i64 " ++ t ++ ", 0")
      numbers <- mapM (\b -> result ("ashr i64 " ++ b ++ ", 1")) bits
      case numbers of
        [n,o,i] -> do
          validStart <- result ("icmp sge i64 " ++ i ++ ", 0")
          validEnd <- result ("icmp sge i64 " ++ n ++ ", " ++ i)
          validSource <- result ("icmp ule i64 " ++ n ++ ", " ++ sourceLength)
          validOffset <- result ("icmp ule i64 " ++ o ++ ", " ++ destLength)
          available <- result ("sub i64 " ++ destLength ++ ", " ++ o)
          validDest <- result ("icmp ule i64 " ++ n ++ ", " ++ available)
          count <- result ("sub i64 " ++ n ++ ", " ++ i)
          separate <- result ("icmp ne ptr " ++ sourceCells ++ ", " ++ destCells)
          samePosition <- result ("icmp eq i64 " ++ o ++ ", 0")
          disjoint <- result ("icmp uge i64 " ++ o ++ ", " ++ count)
          safeAlias <- result ("or i1 " ++ separate ++ ", " ++ samePosition) >>= \t -> result ("or i1 " ++ t ++ ", " ++ disjoint)
          ready <- foldM (\a b -> result ("and i1 " ++ a ++ ", " ++ b)) "true"
            (tests ++ [validStart,validEnd,validSource,validOffset,validDest,safeAlias])
          fast <- fresh "copy.bulk."; slow <- fresh "copy.scalar."
          emit ("  br i1 " ++ ready ++ ", label %" ++ fast ++ ", label %" ++ slow)
          label fast
          from <- result ("getelementptr i8, ptr " ++ sourceCells ++ ", i64 " ++ i)
          start <- result ("add i64 " ++ o ++ ", " ++ i)
          to <- result ("getelementptr i8, ptr " ++ destCells ++ ", i64 " ++ start)
          emit ("  call void @llvm.memmove.p0.p0.i64(ptr " ++ to ++ ", ptr " ++ from ++ ", i64 " ++ count ++ ", i1 false)")
          emit ("  ret ptr " ++ immediate 4)
          label slow
          fallback
        _ -> lift (Left "LLVM invalid copy indices")
    _ -> lift (Left "LLVM invalid copy operands")

numericValue :: NumericScope -> X.Name -> Build Scalar
numericValue scope n = maybe (lift (Left ("LLVM numeric region unbound identity: " ++ show n))) pure (Map.lookup n scope)

rootSlots :: [String] -> Build String
rootSlots [] = pure "null"
rootSlots roots = do
  slots <- result ("alloca [" ++ show (length roots) ++ " x ptr], align 8")
  forM_ (zip [0::Int ..] roots) $ \(i,v) -> do
    slot <- result ("getelementptr ptr, ptr " ++ slots ++ ", i64 " ++ show i)
    emit ("  store ptr " ++ v ++ ", ptr " ++ slot ++ ", align 8")
  pure slots

-- Collection only occurs at explicitly rooted native IO entries. Protect
-- the caller's live values over a non-tail call to such an entry. Tail calls
-- need only the callee's parameters, rooted by its entry before collection.
withNumericRoots :: X.Name -> NumericScope -> Build a -> Build a
withNumericRoots name scope action = do
  collects <- gets (Set.member name . collectingKernels)
  if not collects then action else do
    let roots = Set.toAscList (Set.fromList [v | Boxed v <- Map.elems scope])
    slots <- rootSlots roots
    frame <- result "alloca [3 x ptr], align 8"
    emit ("  call void @mlf_roots_enter(ptr " ++ frame ++ ", " ++ number (length roots) ++ ", ptr " ++ slots ++ ")")
    value <- action
    emit ("  call void @mlf_roots_leave(ptr " ++ frame ++ ")")
    pure value

numericCondition :: Scalar -> Build String
numericCondition v = boxed v >>= \p -> result ("icmp eq ptr " ++ p ++ ", " ++ immediate 6)

numericChoose :: String -> Build Scalar -> Build Scalar -> Build Scalar
numericChoose condition yes no = Boxed <$> choose "ptr" condition (yes >>= boxed) (no >>= boxed)

numericBranch :: NumericScope -> X.Erased -> Build Scalar -> Build Scalar -> Build Scalar
numericBranch scope expression yes no = do
  condition <- scalarValue scope expression >>= numericCondition
  numericChoose condition (refineNumeric scope expression True >> yes) (refineNumeric scope expression False >> no)

-- Equality with an interval endpoint narrows either branch. Only existing
-- tagged-Int proofs are refined; unknown or GMP values remain general.
refineNumeric :: NumericScope -> X.Erased -> Bool -> Build ()
refineNumeric scope expression truth = case applications expression of
  (X.EPrimitive P.EqInt,[X.EVar n,X.EInt k]) -> endpoint n k
  (X.EPrimitive P.EqInt,[X.EInt k,X.EVar n]) -> endpoint n k
  (X.EPrimitive P.LtInt,[a,b]) -> do
    facts <- gets scalarRanges
    case (reference a,reference b) of
      (Just x,Just y) | Just (lo,hi) <- Map.lookup x facts, Just (lo',hi') <- Map.lookup y facts -> do
        let xs = if truth then (lo,min hi (hi'-1)) else (max lo lo',hi)
            ys = if truth then (max lo' (lo+1),hi') else (lo',min hi' hi)
        when (uncurry (<=) xs) (recordRange x xs)
        when (uncurry (<=) ys) (recordRange y ys)
      _ -> pure ()
  _ -> pure ()
  where
    reference (X.EVar n) = case Map.lookup n scope of Just (Boxed v) -> Just v; _ -> Nothing
    reference (X.EInt n) | n >= negate (2^(62::Int)) && n < 2^(62::Int) = Just (immediate (n*2+1))
    reference _ = Nothing
    endpoint n k = case Map.lookup n scope of
      Just (Boxed v) -> do
        bounds <- gets (Map.lookup v . scalarRanges)
        case bounds of
          Just (lo,hi) -> do
            let (lo',hi') | truth = (max lo k,min hi k)
                          | k == lo = (lo+1,hi)
                          | k == hi = (lo,hi-1)
                          | otherwise = (lo,hi)
            when (lo' <= hi') (recordRange v (lo',hi'))
          _ -> pure ()
      _ -> pure ()

-- Guaranteed tail calls for matching private ABIs. No pointer here refers
-- to a caller's stack: values/environments are managed heap objects or tags.
-- Different arities/Double representations use an ordinary call; recursive
-- loops with a stable representation use musttail even at LLVM -O0.
executeNumericReturn :: [NativeMode] -> NumericScope -> X.Erased -> Build ()
executeNumericReturn modes scope expression
  | Just update <- tableUpdate expression = do
      (local,rest) <- executeTableUpdate scope update
      executeNumericReturn modes local rest
  | otherwise = case expression of
  X.ELet n a b -> scalarValue scope a >>= \v -> executeNumericReturn modes (Map.insert n v scope) b
  X.ELetRec _ b -> executeNumericReturn modes scope b
  _ -> case applications expression of
    (X.EPrimitive P.IOBind,[a,X.EAbs n b]) -> do
      v <- executeNumeric scope a
      executeNumericReturn modes (Map.insert n v scope) b
    (X.EPrimitive P.IfThenElse,[c,a,b]) -> do
      condition <- scalarValue scope c >>= numericCondition
      before <- gets (\s -> (scalarRanges s,arrayViews s,unboxedDoubles s))
      yes <- fresh "tail.yes."; no <- fresh "tail.no."
      emit ("  br i1 " ++ condition ++ ", label %" ++ yes ++ ", label %" ++ no)
      label yes
      refineNumeric scope c True
      executeNumericReturn modes scope a
      let (ranges,views,doubles) = before
      modify' (\s -> s { scalarRanges = ranges, arrayViews = views, unboxedDoubles = doubles })
      label no
      refineNumeric scope c False
      executeNumericReturn modes scope b
    (X.EVar n,args) -> do
      fs <- gets functions
      let f = fs Map.! n
      captured <- mapM (numericValue scope) (A.captures f)
      values <- mapM (scalarValue scope) args
      (code,actual) <- kernelCall n f (captured ++ values)
      let marker = if map (== UnboxedDouble) modes == map isFloating actual then "musttail " else ""
      v <- result (marker ++ "call ptr " ++ code ++ "(" ++ intercalate ", " (map scalarArgument actual) ++ ")")
      emit ("  ret ptr " ++ v)
    _ -> do
      v <- executeNumeric scope expression >>= boxed
      emit ("  ret ptr " ++ v)

-- No allocation is needed for array reads or floating intermediates. A
-- Double is boxed at a general ABI or result boundary. Int retains
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
    (X.EPrimitive P.IfThenElse,[c,a,b]) ->
      numericBranch scope c (scalarValue scope a) (scalarValue scope b)
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
            (_,[a,b]) | p `elem` [P.MulInt,P.QuotInt,P.RemInt] -> numericProduct p a b
            (P.AndInt,[a,b]) -> numericAnd a b
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
executeNumeric scope expression
  | Just update <- tableUpdate expression = do
      (local,rest) <- executeTableUpdate scope update
      executeNumeric local rest
  | otherwise = case expression of
  X.ELet n a b -> scalarValue scope a >>= \v -> executeNumeric (Map.insert n v scope) b
  X.ELetRec _ b -> executeNumeric scope b
  _ -> case applications expression of
    (X.EPrimitive P.IOBind,[a,X.EAbs n b]) -> do
      v <- executeNumeric scope a
      executeNumeric (Map.insert n v scope) b
    (X.EPrimitive P.IOReturn,[a]) -> scalarValue scope a
    (X.EPrimitive P.IfThenElse,[c,a,b]) ->
      numericBranch scope c (executeNumeric scope a) (executeNumeric scope b)
    (X.EVar n,args) -> do
      fs <- gets functions
      let f = fs Map.! n
      captured <- mapM (numericValue scope) (A.captures f)
      values <- mapM (scalarValue scope) args
      Boxed <$> withNumericRoots n scope (invokeKernel n f (captured ++ values))
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
            x <- result ("load i8, ptr " ++ address ++ ", align 1, !tbaa !4")
            wide <- result ("zext i8 " ++ x ++ " to i64")
            tagged <- result ("shl i64 " ++ wide ++ ", 1") >>= \v -> result ("or i64 " ++ v ++ ", 1")
            v <- result ("inttoptr i64 " ++ tagged ++ " to ptr")
            recordRange v (0,255)
            pure (Boxed v)
          P.WriteByteArray -> do
            v <- boxed (values !! 2)
            x <- numericByte v
            emit ("  store i8 " ++ x ++ ", ptr " ++ address ++ ", align 1, !tbaa !4")
            pure (Boxed (immediate 4))
          P.ReadDoubleArray -> Floating <$> result ("load double, ptr " ++ address ++ ", align 8, !tbaa !4")
          P.ReadIntArray -> Boxed <$> result ("load ptr, ptr " ++ address ++ ", align 8, !tbaa !4")
          P.WriteDoubleArray -> do
            v <- floating (values !! 2)
            emit ("  store double " ++ v ++ ", ptr " ++ address ++ ", align 8, !tbaa !4")
            pure (Boxed (immediate 4))
          _ -> do
            v <- boxed (values !! 2)
            emit ("  store ptr " ++ v ++ ", ptr " ++ address ++ ", align 8, !tbaa !4")
            pure (Boxed (immediate 4))
    (X.EPrimitive p,args) | p `elem` [P.ReadIntTable,P.WriteIntTable] -> do
      values <- mapM (scalarValue scope >=> boxed) args
      Boxed <$> call (if p == P.ReadIntTable then "@mlf_read_int_table" else "@mlf_write_int_table")
        (map pointer values)
    (X.EPrimitive p,args) | p `elem` [P.GetByteLine,P.NewByteArray,P.NewIntArray,P.NewDoubleArray,
                                    P.ByteArrayFromString,P.PutBytes,P.NewIntTable] -> do
      values <- mapM (scalarValue scope >=> boxed) args
      let (symbol,prefix) = case p of
            P.GetByteLine -> ("@mlf_get_byte_line",[])
            P.NewIntTable -> ("@mlf_new_int_table",[])
            P.ByteArrayFromString -> ("@mlf_bytes_from_string",[])
            P.PutBytes -> ("@mlf_put_bytes",[])
            _ -> ("@mlf_new_array",[number (primitiveCode p)])
      Boxed <$> call symbol (prefix ++ map pointer values)
    _ -> lift (Left "LLVM unsupported numeric IO region")

-- Fuse adjacent operations on the identical table/key, with no intervening
-- effect. The increment must not depend on the old value; that value stays
-- available as a snapshot after the update. Only total native operands reach
-- this path, so eager evaluation cannot reorder a language error or divergence.
type TableUpdate = (X.Name,X.Erased,X.Erased,X.Erased,X.Name,X.Erased)

tableUpdate :: X.Erased -> Maybe TableUpdate
tableUpdate expression = do
  (readAction,old,body) <- bindParts expression
  (X.EPrimitive P.ReadIntTable,[table,key]) <- pure (applications readAction)
  (writeAction,done,rest) <- bindParts body
  (X.EPrimitive P.WriteIntTable,[table',key',value]) <- pure (applications writeAction)
  (X.EPrimitive P.AddInt,[a,b]) <- pure (applications value)
  delta <- if a == X.EVar old then Just b else if b == X.EVar old then Just a else Nothing
  if table == table' && key == key' && not (Set.member old (free delta))
    then Just (old,table,key,delta,done,rest) else Nothing
  where
    bindParts e = case applications e of
      (X.EPrimitive P.IOBind,[a,X.EAbs n b]) -> Just (a,n,b)
      _ -> Nothing

executeTableUpdate :: NumericScope -> TableUpdate -> Build (NumericScope,X.Erased)
executeTableUpdate scope (old,table,key,delta,done,rest) = do
  values <- mapM (scalarValue scope >=> boxed) [table,key,delta]
  previous <- call "@mlf_add_int_table" (map pointer values)
  pure (Map.insert done (Boxed (immediate 4)) (Map.insert old (Boxed previous) scope),rest)

recordRange :: String -> (Integer,Integer) -> Build ()
recordRange value bounds = modify' (\s -> s { scalarRanges = Map.insertWith
  (\(a,b) (c,d) -> (max a c,min b d)) value bounds (scalarRanges s) })

numericAnd :: String -> String -> Build String
numericAnd a b = do
  x <- result ("ptrtoint ptr " ++ a ++ " to i64")
  y <- result ("ptrtoint ptr " ++ b ++ " to i64")
  bits <- result ("and i64 " ++ x ++ ", " ++ y)
  tag <- result ("and i64 " ++ bits ++ ", 1") >>= \v -> result ("icmp ne i64 " ++ v ++ ", 0")
  value <- choose "ptr" tag (result ("inttoptr i64 " ++ bits ++ " to ptr"))
    (call "@mlf_prim2" [number (primitiveCode P.AndInt),pointer a,pointer b])
  facts <- gets scalarRanges
  case [hi | v <- [a,b], Just (lo,hi) <- [Map.lookup v facts], lo >= 0] of
    [] -> pure ()
    bounds -> recordRange value (0,minimum bounds)
  pure value

numericByte :: String -> Build String
numericByte value = do
  facts <- gets scalarRanges
  bits <- result ("ptrtoint ptr " ++ value ++ " to i64")
  n <- result ("ashr i64 " ++ bits ++ ", 1")
  let narrow = result ("trunc i64 " ++ n ++ " to i8")
  case Map.lookup value facts of
    Just (lo,hi) | lo >= 0 && hi <= 255 -> narrow
    _ -> do
      small <- result ("and i64 " ++ bits ++ ", 1") >>= \v -> result ("icmp ne i64 " ++ v ++ ", 0")
      bounds <- result ("icmp ult i64 " ++ n ++ ", 256")
      valid <- result ("and i1 " ++ small ++ ", " ++ bounds)
      choose "i8" valid narrow (result ("call i8 @mlf_byte(ptr " ++ value ++ ")"))

-- Int is still arbitrary precision. Only evaluated tagged operands take the
-- machine path; multiplication checks both machine overflow and the narrower
-- tagged range. Division keeps zero and the small-minimum / -1 case on the
-- runtime path, where errors and GMP promotion have their usual semantics.
numericProduct :: P.Primitive -> String -> String -> Build String
numericProduct p a b = do
  facts <- gets scalarRanges
  x <- result ("ptrtoint ptr " ++ a ++ " to i64")
  y <- result ("ptrtoint ptr " ++ b ++ " to i64")
  let slow = call "@mlf_prim2" [number (primitiveCode p),pointer a,pointer b]
      tagged n = do
        shifted <- result ("shl i64 " ++ n ++ ", 1")
        bits <- result ("or i64 " ++ shifted ++ ", 1")
        result ("inttoptr i64 " ++ bits ++ " to ptr")
      fast = do
        i <- result ("ashr i64 " ++ x ++ ", 1")
        j <- result ("ashr i64 " ++ y ++ ", 1")
        if p == P.MulInt then do
          pair <- result ("call { i64, i1 } @llvm.smul.with.overflow.i64(i64 " ++ i ++ ", i64 " ++ j ++ ")")
          n <- result ("extractvalue { i64, i1 } " ++ pair ++ ", 0")
          overflow <- result ("extractvalue { i64, i1 } " ++ pair ++ ", 1")
          noOverflow <- result ("xor i1 " ++ overflow ++ ", true")
          lower <- result ("icmp sge i64 " ++ n ++ ", -4611686018427387904")
          upper <- result ("icmp sle i64 " ++ n ++ ", 4611686018427387903")
          fits <- result ("and i1 " ++ lower ++ ", " ++ upper) >>= \v -> result ("and i1 " ++ v ++ ", " ++ noOverflow)
          choose "ptr" fits (tagged n) slow
        else do
          nonzero <- result ("icmp ne i64 " ++ j ++ ", 0")
          smallest <- result ("icmp eq i64 " ++ i ++ ", -4611686018427387904")
          negativeOne <- result ("icmp eq i64 " ++ j ++ ", -1")
          promotion <- result ("and i1 " ++ smallest ++ ", " ++ negativeOne)
          fits <- result ("xor i1 " ++ promotion ++ ", true") >>= \v -> result ("and i1 " ++ nonzero ++ ", " ++ v)
          choose "ptr" fits (result ((if p == P.QuotInt then "sdiv" else "srem") ++ " i64 " ++ i ++ ", " ++ j) >>= tagged) slow
  case (p,Map.lookup a facts,Map.lookup b facts) of
    (P.MulInt,Just (lo,hi),Just (lo',hi')) -> do
      let products = [lo*lo',lo*hi',hi*lo',hi*hi']
          bounds = (minimum products,maximum products)
      if fst bounds >= negate (2^(62::Int)) && snd bounds < 2^(62::Int) then do
        i <- result ("ashr i64 " ++ x ++ ", 1")
        j <- result ("ashr i64 " ++ y ++ ", 1")
        v <- result ("mul nsw i64 " ++ i ++ ", " ++ j) >>= tagged
        recordRange v bounds
        pure v
      else checked x y fast slow
    _ -> checked x y fast slow
  where
    checked x y fast slow = do
      both <- result ("and i64 " ++ x ++ ", " ++ y)
      tag <- result ("and i64 " ++ both ++ ", 1") >>= \v -> result ("icmp ne i64 " ++ v ++ ", 0")
      choose "ptr" tag fast slow

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
  doublesBefore <- gets unboxedDoubles
  yesLabel <- fresh "yes."
  noLabel <- fresh "no."
  join <- fresh "join."
  emit ("  br i1 " ++ condition ++ ", label %" ++ yesLabel ++ ", label %" ++ noLabel)
  label yesLabel
  a <- yes
  aBlock <- gets block
  afterYes <- gets scalarRanges
  viewsYes <- gets arrayViews
  doublesYes <- gets unboxedDoubles
  emit ("  br label %" ++ join)
  label noLabel
  modify' (\s -> s { scalarRanges = before, arrayViews = viewsBefore, unboxedDoubles = doublesBefore })
  b <- no
  bBlock <- gets block
  afterNo <- gets scalarRanges
  viewsNo <- gets arrayViews
  doublesNo <- gets unboxedDoubles
  emit ("  br label %" ++ join)
  label join
  modify' (\s -> s { scalarRanges = Map.intersectionWith
    (\(lo,hi) (lo',hi') -> (min lo lo',max hi hi')) afterYes afterNo,
    arrayViews = Map.filterWithKey (\key value -> Map.lookup key viewsNo == Just value) viewsYes,
    unboxedDoubles = Map.filterWithKey (\key value -> Map.lookup key doublesNo == Just value) doublesYes })
  value <- phi ty [(a,aBlock),(b,bBlock)]
  when (ty == "ptr") $ case (Map.lookup a afterYes,Map.lookup b afterNo) of
    (Just (lo,hi),Just (lo',hi')) -> recordRange value (min lo lo',max hi hi')
    _ -> pure ()
  pure value

-- Layout is a small explicit 64-bit ABI, asserted by the runtime. Typed,
-- evaluated constructor cases cannot scrutinize partial constructors.
loadAt :: String -> String -> Int -> Build String
loadAt ty value offset = do
  address <- result ("getelementptr i8, ptr " ++ value ++ ", i64 " ++ show offset)
  result ("load " ++ ty ++ ", ptr " ++ address ++ ", align 8, !tbaa !3")

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
  P.GetByteLine -> 41; P.NewIntTable -> 42; P.ReadIntTable -> 43; P.WriteIntTable -> 44
  P.AndInt -> 45

runtimeDeclarations :: [String]
runtimeDeclarations =
  [ "declare ptr @mlf_env_new(i64)", "declare void @mlf_env_set(ptr, i64, ptr)"
  , "declare ptr @mlf_env_get(ptr, i64)", "declare ptr @mlf_thunk(ptr, ptr)"
  , "declare ptr @mlf_closure(ptr, ptr)", "declare ptr @mlf_application(ptr, ptr)"
  , "declare ptr @mlf_hole()", "declare void @mlf_fill(ptr, ptr)"
  , "declare ptr @mlf_integer(ptr)", "declare ptr @mlf_string(ptr, i64)"
  , "declare ptr @mlf_double(double)", "declare double @llvm.sqrt.f64(double)"
  , "declare double @mlf_int_to_double(ptr)"
  , "declare ptr @mlf_read_int_table(ptr, ptr)", "declare ptr @mlf_write_int_table(ptr, ptr, ptr)"
  , "declare ptr @mlf_add_int_table(ptr, ptr, ptr)"
  , "declare void @mlf_roots_enter(ptr, i64, ptr)", "declare void @mlf_roots_leave(ptr)"
  , "declare void @mlf_gc_check(i64, ptr)"
  , "declare ptr @mlf_get_byte_line()", "declare ptr @mlf_new_array(i64, ptr, ptr)"
  , "declare ptr @mlf_bytes_from_string(ptr)", "declare ptr @mlf_put_bytes(ptr, ptr, ptr)"
  , "declare ptr @mlf_new_int_table()"
  , "declare void @llvm.memmove.p0.p0.i64(ptr, ptr, i64, i1)"
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
  , "declare { i64, i1 } @llvm.smul.with.overflow.i64(i64, i64)"
  , "declare { i64, i1 } @llvm.ssub.with.overflow.i64(i64, i64)"
  , "declare i32 @mlf_run(ptr, i64)", ""
  ]
