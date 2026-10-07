-- | Native workers for known saturated functions, with memoized closures for
-- everything that remains lazy or higher order. Demand information is only
-- used at saturation, never while constructing a partial application.
module MLF.LLVM.Codegen (generate) where

import Control.Monad (foldM, forM, forM_, unless, when)
import Control.Monad.State.Strict
import Data.Bits ((.&.), shiftR)
import Data.Char (ord)
import Data.List (intercalate)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import Numeric (showHex)
import qualified MLF.LLVM.Analysis as A
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
  }
type Build = StateT Output (Either String)

generate :: Constructors -> X.Erased -> Either String (String,[String])
generate cs term = do
  (entry,out) <- runStateT (callback [] Nothing term)
    (Output 0 [] "entry" [] [] cs (A.analyze term) Set.empty Map.empty)
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
  saved <- gets (\s -> (instructions s,block s))
  modify' (\s -> s { instructions = [], block = "entry" })
  value <- body
  emit ("  ret ptr " ++ value)
  code <- gets (reverse . instructions)
  let text = unlines (["define private ptr " ++ name ++ "(" ++ intercalate ", " args ++ ") {", "entry:"] ++ code ++ ["}"])
  modify' (\s -> s { instructions = fst saved, block = snd saved, definitions = text : definitions s })

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
    definition symbol (map pointer registers) $
      evaluate (Map.fromList [(n,Binding r (Set.member n (A.strict f))) | (n,r) <- zip names registers]) (A.functionBody f)
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
  symbol <- worker name f
  captured <- forM (A.captures f) $ \n -> lookupName scope n >>= \b ->
    if Set.member n (A.strict f) then forceBinding b else pure (operand b)
  values <- forM (zip (A.parameters f) args) $ \(n,a) ->
    if Set.member n (A.strict f) then evaluate scope a else thunk scope a
  call symbol (map pointer (captured ++ values))

-- Atoms and constructors already are values. A compound lazy expression is
-- one memoized callback, rather than a heap application at every syntax node.
thunk :: Scope -> X.Erased -> Build String
thunk scope expression = case expression of
  X.EVar n -> operand <$> lookupName scope n
  X.EInt _ -> evaluate scope expression
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
      let strict = p `elem` [P.AddInt,P.SubInt,P.EqInt,P.LtInt,P.ConcatString,P.EqString,P.ShowInt]
      values <- mapM (if strict then evaluate scope else thunk scope) args
      case (p,values) of
        (P.AddInt,[a,b]) -> integerOperation p a b
        (P.SubInt,[a,b]) -> integerOperation p a b
        (P.EqInt,[a,b]) -> integerOperation p a b
        (P.LtInt,[a,b]) -> integerOperation p a b
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
  yesLabel <- fresh "yes."
  noLabel <- fresh "no."
  join <- fresh "join."
  emit ("  br i1 " ++ condition ++ ", label %" ++ yesLabel ++ ", label %" ++ noLabel)
  label yesLabel
  a <- yes
  aBlock <- gets block
  emit ("  br label %" ++ join)
  label noLabel
  b <- no
  bBlock <- gets block
  emit ("  br label %" ++ join)
  label join
  phi ty [(a,aBlock),(b,bBlock)]

-- Layout is a small explicit 64-bit ABI, asserted by the runtime. Typed,
-- evaluated constructor cases cannot scrutinize partial constructors.
loadAt :: String -> String -> Int -> Build String
loadAt ty value offset = do
  address <- result ("getelementptr i8, ptr " ++ value ++ ", i64 " ++ show offset)
  result ("load " ++ ty ++ ", ptr " ++ address ++ ", align 8")

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

runtimeDeclarations :: [String]
runtimeDeclarations =
  [ "declare ptr @mlf_env_new(i64)", "declare void @mlf_env_set(ptr, i64, ptr)"
  , "declare ptr @mlf_env_get(ptr, i64)", "declare ptr @mlf_thunk(ptr, ptr)"
  , "declare ptr @mlf_closure(ptr, ptr)", "declare ptr @mlf_application(ptr, ptr)"
  , "declare ptr @mlf_hole()", "declare void @mlf_fill(ptr, ptr)"
  , "declare ptr @mlf_integer(ptr)", "declare ptr @mlf_string(ptr, i64)"
  , "declare ptr @mlf_primitive(i64)", "declare ptr @mlf_prim1(i64, ptr)"
  , "declare ptr @mlf_prim2(i64, ptr, ptr)", "declare i64 @mlf_truth(ptr)"
  , "declare ptr @mlf_force(ptr)", "declare ptr @mlf_add_int(ptr, ptr)"
  , "declare ptr @mlf_sub_int(ptr, ptr)", "declare ptr @mlf_eq_int(ptr, ptr)"
  , "declare ptr @mlf_lt_int(ptr, ptr)", "declare ptr @mlf_constructor(i64, i64)"
  , "declare ptr @mlf_constructor1(i64, ptr)", "declare ptr @mlf_constructor2(i64, ptr, ptr)"
  , "declare ptr @mlf_field(ptr, i64)", "declare void @mlf_match_failure() noreturn"
  , "declare { i64, i1 } @llvm.sadd.with.overflow.i64(i64, i64)"
  , "declare { i64, i1 } @llvm.ssub.with.overflow.i64(i64, i64)"
  , "declare i32 @mlf_run(ptr, i64)", ""
  ]
