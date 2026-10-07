-- | Checked xMLF to native LLVM functions. Type computations are erased only
-- after the independent target checker accepts the complete term.
module MLF.LLVM (emitLLVM, emitLLVMIO) where

import Control.Monad (foldM, forM, forM_, when)
import Control.Monad.State.Strict
import Data.Bifunctor (first)
import Data.Bits ((.&.), shiftR)
import Data.Char (ord)
import Data.List (intercalate)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import Numeric (showHex)
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Scope = Map.Map X.Name String
type Constructors = Map.Map String (Int,Int)
data Output = Output
  { serial :: !Int, instructions :: [String]
  , definitions :: [String], constants :: [String]
  }
type Build = StateT Output (Either String)

-- | Emit a module with mlf_entry and main. Link it with runtime/mlf_runtime.c
-- and GMP. IO entries execute their action; other entries evaluate to weak
-- head normal form and discard the result, without implicitly printing it.
emitLLVM :: X.Term -> Either String String
emitLLVM = emitEntry False

-- | Require an IO entry, matching MLF.Runtime.runTerm. The ordinary emitter
-- retains its existing automatic IO/pure program convention.
emitLLVMIO :: X.Term -> Either String String
emitLLVMIO = emitEntry True

emitEntry :: Bool -> X.Term -> Either String String
emitEntry requireIO term = do
  ty <- first ("LLVM target verification failed: " ++) (Check.checkClosed term)
  let declarations = case term of X.WithData ds _ -> ds; _ -> []
      constructors = Map.fromList (("Unit",(0,0)) :
        [(D.constructorName c,(i,length (D.constructorFields c))) |
          (i,c) <- zip [1..] (concatMap D.datatypeConstructors declarations)])
      ioType (T.Forall _ _ body) = ioType body
      ioType (T.Con "IO" [_]) = True
      ioType _ = False
  when (requireIO && not (ioType ty)) (Left "program must have type IO a to run")
  (entry,out) <- runStateT (function constructors [] Nothing (X.erase term))
    (Output 0 [] [] [])
  pure $ unlines (["; Generated from independently checked xMLF.",
    "source_filename = \"emlf\"", ""] ++ runtimeDeclarations ++
    reverse (constants out) ++ reverse (definitions out) ++
    [ "define ptr @mlf_entry() {"
    , "  %root = call ptr " ++ entry ++ "(ptr null, ptr null)"
    , "  ret ptr %root", "}"
    , "define i32 @main() {"
    , "  %root = call ptr @mlf_entry()"
    , "  %status = call i32 @mlf_run(ptr %root, i64 " ++ (if ioType ty then "1" else "0") ++ ")"
    , "  ret i32 %status", "}"
    ])

fresh :: String -> Build String
fresh prefix = do
  n <- gets serial
  modify' (\s -> s { serial = n + 1 })
  pure (prefix ++ show n)

emit :: String -> Build ()
emit line = modify' (\s -> s { instructions = line : instructions s })

result :: String -> Build String
result expression = do
  register <- fresh "%v"
  emit ("  " ++ register ++ " = " ++ expression)
  pure register

call :: String -> [String] -> Build String
call name arguments = result ("call ptr @" ++ name ++ "(" ++ intercalate ", " arguments ++ ")")

pointer :: String -> String
pointer = ("ptr " ++)

number :: Int -> String
number = ("i64 " ++) . show

lookupName :: Scope -> X.Name -> Build String
lookupName scope name = maybe (lift (Left ("LLVM unbound identity: " ++ show name))) pure (Map.lookup name scope)

lookupConstructor :: Constructors -> String -> Build (Int,Int)
lookupConstructor constructors name = maybe (lift (Left ("LLVM unknown constructor: " ++ name))) pure
  (Map.lookup name constructors)

-- Environment slots are ordered by resolved identity, never by display name.
environment :: Scope -> [X.Name] -> Build String
environment _ [] = pure "null"
environment scope names = do
  env <- call "mlf_env_new" [number (length names)]
  forM_ (zip [0..] names) $ \(index,name) -> do
    value <- lookupName scope name
    emit ("  call void @mlf_env_set(" ++ intercalate ", " [pointer env,number index,pointer value] ++ ")")
  pure env

function :: Constructors -> [X.Name] -> Maybe X.Name -> X.Erased -> Build String
function constructors captures argument body = do
  name <- fresh "@mlf.code."
  saved <- gets instructions
  modify' (\s -> s { instructions = [] })
  bindings <- forM (zip [0..] captures) $ \(index,n) -> do
    value <- call "mlf_env_get" ["ptr %env",number index]
    pure (n,value)
  let scope = maybe id (\n -> Map.insert n "%arg") argument (Map.fromList bindings)
  evaluate constructors scope body
  lines' <- gets (reverse . instructions)
  let definition = unlines (["define private ptr " ++ name ++ "(ptr %env, ptr %arg) {", "entry:"] ++ lines' ++ ["}"])
  modify' (\s -> s { instructions = saved, definitions = definition : definitions s })
  pure name

-- Building an application does not force its function or argument. Complex
-- arguments and let RHSs become memoized thunks; recursive holes are filled
-- before any generated code can force the recursive environment.
thunk :: Constructors -> Scope -> X.Erased -> Build String
thunk constructors scope expression = case expression of
  X.EVar n -> lookupName scope n
  X.EInt n -> do
    (literal,_) <- stringConstant (show n)
    call "mlf_integer" [pointer literal]
  X.EBool b -> call "mlf_boolean" [number (if b then 1 else 0)]
  X.EString text -> do
    (literal,size) <- stringConstant text
    call "mlf_string" [pointer literal,number size]
  X.EPrimitive p -> call "mlf_primitive" [number (primitiveCode p)]
  X.EConstructor c -> do
    (tag,arity) <- lookupConstructor constructors c
    call "mlf_constructor" [number tag,number arity]
  X.EApp f a -> do
    f' <- thunk constructors scope f
    a' <- thunk constructors scope a
    call "mlf_application" [pointer f',pointer a']
  X.EAbs n body -> do
    let captures = Set.toAscList (Set.delete n (free body))
    code <- function constructors captures (Just n) body
    env <- environment scope captures
    call "mlf_closure" [pointer code,pointer env]
  X.EEvidenceHole _ -> lift (Left "LLVM unresolved dictionary evidence")
  _ -> do
    let captures = Set.toAscList (free expression)
    code <- function constructors captures Nothing expression
    env <- environment scope captures
    call "mlf_thunk" [pointer code,pointer env]

-- Every path ends in ret. Case alternatives become native basic blocks,
-- rather than a runtime AST or bytecode dispatch table.
evaluate :: Constructors -> Scope -> X.Erased -> Build ()
evaluate constructors scope expression = case expression of
  X.ELet n rhs body -> do
    value <- thunk constructors scope rhs
    evaluate constructors (Map.insert n value scope) body
  X.ELetRec bindings body -> do
    holes <- forM bindings $ \(n,_) -> do
      hole <- call "mlf_hole" []
      pure (n,hole)
    let recursive = Map.union (Map.fromList holes) scope
    forM_ bindings $ \(n,rhs) -> do
      value <- thunk constructors recursive rhs
      hole <- lookupName recursive n
      emit ("  call void @mlf_fill(ptr " ++ hole ++ ", ptr " ++ value ++ ")")
    evaluate constructors recursive body
  X.ECase scrutinee alternatives -> do
    value <- thunk constructors scope scrutinee
    case alternatives of
      -- The interpreter's variable/wildcard-only case is non-strict.
      [X.ErasedAlternative (X.DefaultPattern name) body] ->
        evaluate constructors (maybe scope (\n -> Map.insert n value scope) name) body
      _ -> do
        tag <- result ("call i64 @mlf_tag(ptr " ++ value ++ ")")
        labelled <- forM alternatives $ \alternative -> do
          label <- fresh "case."
          pure (label,alternative)
        missing <- fresh "case.missing."
        let fallback = case [label | (label,X.ErasedAlternative (X.DefaultPattern _) _) <- labelled] of
              label:_ -> label
              [] -> missing
        entries <- forM [(label,c) | (label,X.ErasedAlternative (X.ConstructorPattern c _) _) <- labelled] $ \(label,c) -> do
          (identity,_) <- lookupConstructor constructors c
          pure ("    i64 " ++ show identity ++ ", label %" ++ label)
        emit ("  switch i64 " ++ tag ++ ", label %" ++ fallback ++ " [")
        mapM_ emit entries
        emit "  ]"
        forM_ labelled $ \(label,X.ErasedAlternative pattern' body) -> do
          emit (label ++ ":")
          local <- case pattern' of
            X.DefaultPattern name -> pure (maybe scope (\n -> Map.insert n value scope) name)
            X.ConstructorPattern _ names -> foldM (\env (index,name) -> case name of
              Nothing -> pure env
              Just n -> do
                field <- call "mlf_field" [pointer value,number index]
                pure (Map.insert n field env)) scope (zip [0..] names)
          evaluate constructors local body
        when (fallback == missing) $ do
          emit (missing ++ ":")
          emit "  call void @mlf_match_failure()"
          emit "  unreachable"
  _ -> thunk constructors scope expression >>= emit . ("  ret ptr " ++)

free :: X.Erased -> Set.Set X.Name
free expression = case expression of
  X.EVar n -> Set.singleton n
  X.EAbs n body -> Set.delete n (free body)
  X.EApp f a -> free f `Set.union` free a
  X.ELet n a b -> free a `Set.union` Set.delete n (free b)
  X.ELetRec ds body -> Set.unions (free body : map (free . snd) ds) `Set.difference` Set.fromList (map fst ds)
  X.ECase s bs -> free s `Set.union` Set.unions
    [free body `Set.difference` Set.fromList (X.patternNames p) | X.ErasedAlternative p body <- bs]
  _ -> Set.empty

-- Length-delimited UTF-8 preserves embedded NULs. LLVM byte escapes also
-- prevent source strings, quotes, and newlines from becoming IR syntax.
stringConstant :: String -> Build (String,Int)
stringConstant text = do
  bytes <- lift (concat <$> mapM utf8 text)
  name <- fresh "@mlf.bytes."
  let escape byte = '\\' : (if byte < 16 then "0" else "") ++ showHex byte ""
      definition = name ++ " = private unnamed_addr constant [" ++ show (length bytes + 1) ++
        " x i8] c\"" ++ concatMap escape (bytes ++ [0]) ++ "\", align 1"
  modify' (\s -> s { constants = definition : constants s })
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

-- Stable runtime ABI codes, deliberately independent of the derived Enum.
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
  , "declare ptr @mlf_integer(ptr)", "declare ptr @mlf_boolean(i64)"
  , "declare ptr @mlf_string(ptr, i64)", "declare ptr @mlf_primitive(i64)"
  , "declare ptr @mlf_constructor(i64, i64)", "declare i64 @mlf_tag(ptr)"
  , "declare ptr @mlf_field(ptr, i64)", "declare void @mlf_match_failure() noreturn"
  , "declare i32 @mlf_run(ptr, i64)", ""
  ]
