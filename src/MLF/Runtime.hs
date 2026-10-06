-- | A lazy interpreter for checked xMLF erasure. Evaluating a term constructs
-- IO actions; only the action interpreter below can call the backend.
module MLF.Runtime
  ( IOBackend (..), consoleBackend, RuntimeError (..), runTerm
  ) where

import Control.Exception (IOException, displayException, try)
import Control.Monad (unless)
import Data.Bifunctor (first)
import qualified Data.Map.Lazy as Map
import System.IO (hFlush, hPutStr, stdout)
import qualified MLF.Data as D
import MLF.Primitive
import qualified MLF.X.Check as C
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

data IOBackend = IOBackend
  { readLine :: IO String
  , writeText :: String -> IO ()
  }

consoleBackend :: IOBackend
consoleBackend = IOBackend getLine (\text -> hPutStr stdout text >> hFlush stdout)

newtype RuntimeError = RuntimeError String deriving Eq
instance Show RuntimeError where show (RuntimeError message) = message

type Result a = Either RuntimeError a
type Thunk = Result Value
type Env = Map.Map X.Name Thunk

data Value
  = IntegerValue Integer
  | BooleanValue Bool
  | StringValue String
  | Closure Env X.Name X.Erased
  | ConstructorValue String [Thunk]
  | PrimitiveValue Primitive [Thunk]
  | ActionValue Action

data Action
  = ReturnAction Thunk
  | BindAction Thunk Thunk
  | ReadLineAction
  | WriteAction Bool Thunk
  | PrintIntAction Thunk

failure :: String -> Result a
failure = Left . RuntimeError

-- | Check even caller-constructed target terms before executing any effects.
-- The result value of the final IO action is discarded, as with a main action.
runTerm :: IOBackend -> X.Term -> IO (Result ())
runTerm backend term = case prepare of
  Left err -> pure (Left err)
  Right ds -> do
    outcome <- try (fmap (fmap (const ())) (runAction ds backend (evaluate ds Map.empty (X.erase term))))
      :: IO (Either IOException (Result ()))
    pure (either (Left . RuntimeError . ("IO error: " ++) . displayException) id outcome)
  where
    prepare = do
      ty <- first (RuntimeError . ("target verification failed: " ++)) (C.checkClosed term)
      unless (isIO ty) (failure "program must have type IO a to run")
      first RuntimeError (D.validateDeclarations (case term of X.WithData ds _ -> ds; _ -> []))
    isIO (T.Forall _ _ body) = isIO body
    isIO (T.Con "IO" [_]) = True
    isIO _ = False

evaluate :: D.DataEnv -> Env -> X.Erased -> Thunk
evaluate ds env expression = case expression of
  X.EVar n -> maybe (failure ("unbound runtime variable: " ++ X.nameHint n)) id (Map.lookup n env)
  X.EAbs n body -> pure (Closure env n body)
  X.EApp f a -> evaluate ds env f >>= \function -> apply ds function (evaluate ds env a)
  X.ELet n a b -> evaluate ds (Map.insert n (evaluate ds env a) env) b
  X.ELetRec bindings body ->
    let recursive = Map.union (Map.fromList [(n,evaluate ds recursive rhs) | (n,rhs) <- bindings]) env
    in evaluate ds recursive body
  X.EInt n -> pure (IntegerValue n)
  X.EBool b -> pure (BooleanValue b)
  X.EString s -> pure (StringValue s)
  X.EPrimitive p -> primitive p []
  X.EConstructor c -> D.lookupConstructor ds c `orError` \_ -> pure (ConstructorValue c [])
  X.ECase scrutinee alternatives -> choose alternatives
    where
      value = evaluate ds env scrutinee
      choose [] = failure "non-exhaustive runtime case"
      choose (X.ErasedAlternative pattern' body:rest) = case pattern' of
        X.DefaultPattern name -> evaluate ds (maybe env (\n -> Map.insert n value env) name) body
        X.ConstructorPattern c names -> do
          v <- value
          case v of
            ConstructorValue tag fields | c == tag -> do
              unless (length names == length fields) (failure "runtime constructor pattern arity mismatch")
              let locals = Map.fromList [(n,field) | (Just n,field) <- zip names fields]
              evaluate ds (Map.union locals env) body
            ConstructorValue _ _ -> choose rest
            _ -> failure "constructor pattern matched a non-data value"
  X.EEvidenceHole _ -> failure "unresolved runtime dictionary evidence"

orError :: Either String a -> (a -> Result b) -> Result b
orError value next = first RuntimeError value >>= next

apply :: D.DataEnv -> Value -> Thunk -> Thunk
apply ds function argument = case function of
  Closure env name body -> evaluate ds (Map.insert name argument env) body
  ConstructorValue name fields -> D.lookupConstructor ds name `orError` \(_,constructor) -> do
    unless (length fields < length (D.constructorFields constructor)) (failure "runtime constructor overapplication")
    pure (ConstructorValue name (fields ++ [argument]))
  PrimitiveValue p arguments -> primitive p (arguments ++ [argument])
  _ -> failure "runtime application of a non-function"

primitive :: Primitive -> [Thunk] -> Thunk
primitive p arguments
  | length arguments < primitiveArity p = pure (PrimitiveValue p arguments)
  | otherwise = case (p,arguments) of
      (IOReturn,[value]) -> pure (ActionValue (ReturnAction value))
      (IOBind,[action,next]) -> pure (ActionValue (BindAction action next))
      (GetLine,[]) -> pure (ActionValue ReadLineAction)
      (PutStr,[value]) -> pure (ActionValue (WriteAction False value))
      (PutStrLn,[value]) -> pure (ActionValue (WriteAction True value))
      (PrintInt,[value]) -> pure (ActionValue (PrintIntAction value))
      (ConcatString,[a,b]) -> StringValue <$> ((++) <$> string a <*> string b)
      (ShowInt,[value]) -> StringValue . show <$> integer value
      (AddInt,[a,b]) -> IntegerValue <$> ((+) <$> integer a <*> integer b)
      (SubInt,[a,b]) -> IntegerValue <$> ((-) <$> integer a <*> integer b)
      (EqInt,[a,b]) -> BooleanValue <$> ((==) <$> integer a <*> integer b)
      (LtInt,[a,b]) -> BooleanValue <$> ((<) <$> integer a <*> integer b)
      (EqString,[a,b]) -> BooleanValue <$> ((==) <$> string a <*> string b)
      -- Branches are thunks: only the selected branch is evaluated, and an
      -- IO-valued branch still needs to be executed by runAction.
      (IfThenElse,[condition,yes,no]) -> do
        choice <- boolean condition
        if choice then yes else no
      _ -> failure ("runtime primitive arity mismatch: " ++ primitiveName p)

string :: Thunk -> Result String
string thunk = do
  value <- thunk
  case value of
    StringValue s -> pure s
    _ -> failure "runtime primitive expected String"

integer :: Thunk -> Result Integer
integer thunk = do
  value <- thunk
  case value of
    IntegerValue n -> pure n
    _ -> failure "runtime primitive expected Int"

boolean :: Thunk -> Result Bool
boolean thunk = do
  value <- thunk
  case value of
    BooleanValue b -> pure b
    _ -> failure "runtime primitive expected Bool"

runAction :: D.DataEnv -> IOBackend -> Thunk -> IO (Result Thunk)
runAction ds backend thunk = case thunk of
  Left err -> pure (Left err)
  Right (ActionValue action) -> perform action
  Right _ -> pure (failure "runtime expected an IO action")
  where
    unit = pure (ConstructorValue "Unit" [])
    perform (ReturnAction value) = pure (Right value)
    perform (BindAction firstAction next) = do
      result <- runAction ds backend firstAction
      case result of
        Left err -> pure (Left err)
        Right value -> runAction ds backend (next >>= \function -> apply ds function value)
    perform ReadLineAction = do
      line <- readLine backend
      pure (Right (pure (StringValue line)))
    perform (WriteAction newline value) = case string value of
      Left err -> pure (Left err)
      Right text -> do
        writeText backend (text ++ if newline then "\n" else "")
        pure (Right unit)
    perform (PrintIntAction value) = case integer value of
      Left err -> pure (Left err)
      Right n -> do
        writeText backend (show n ++ "\n")
        pure (Right unit)
