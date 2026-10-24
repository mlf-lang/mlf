{-# LANGUAGE OverloadedStrings #-}
-- Focused actual-MLF controls for the builtin-only standalone scope boundary.
module Main where
import Prelude
import System.IO (hSetBuffering, stdout, BufferMode(LineBuffering))
import Data.Time.Clock (getCurrentTime)
import System.Environment (getArgs)
import System.Timeout (timeout)
import qualified Data.List as L
import qualified Bootstrap.Types as T
import qualified Bootstrap.Standalone as S
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Check as Check
import qualified MLF.Host.Base as B

ls = foldr (:) []
str = B.literal
v = T.SVar . str
ty n args = T.SCon (str n) (ls args)
ann t = T.SAnnotation [] t
app = T.SApp
lit n = T.SIntLit n
lam n = T.SLam (str n) T.Nothing
let_ n = T.SLet (str n)
program = T.SProgram []
text s = T.SAnn
  (app (v "$MLF.Primitive.fromString") (app (T.SPrimitive T.PTextToChars) (T.SStringLit (str s))))
  (ann (ty "String" []))
withMarker e = let_ "ignoredString" (text "test") e
compile = compileWith S.normalizeDemanded
compileWith normalizer mode p = case normalizer mode p of
  T.Left e -> T.Left e
  T.Right T.Nothing -> case C.compileProgramWithPrelude mode p of
    T.Left e -> T.Left (C.prettyError e)
    T.Right c -> T.Right c
  T.Right (T.Just ((,,) imported normalized _)) -> case Classes.lowerClassesWithImports imported normalized of
    T.Left e -> T.Left e
    T.Right lowered -> case C.finishCompilation lowered of
      T.Left e -> T.Left (C.prettyError e)
      T.Right c -> T.Right c
result mode p = case compile mode p of
  T.Left e -> T.Left e
  T.Right c -> case Check.checkClosed (C.compiledTerm c) of
    T.Left e -> T.Left e
    T.Right _ -> case R.prepare False (C.compiledTerm c) of
      T.Left e -> T.Left e
      T.Right ((,) env _) -> R.evaluate env (R.REnv M.empty) (X.erase (C.compiledTerm c))
announce label action = do { now <- getCurrentTime; putStrLn (show now++" BEGIN "++label); answer <- action; end <- getCurrentTime; putStrLn (show end++" END "++label); return answer }
check label ok = if ok then putStrLn ("PASS "++label) else error ("FAIL "++label)
integer label mode p expected = announce label $ case result mode p of
  T.Right (R.RInteger n) -> check label (n==expected)
  T.Left e -> error (label++": "++B.unpack e)
  _ -> error (label++": expected integer")
opaque label mode p expected = announce label $ case result mode p of
  T.Right (R.RString s) -> check label (B.unpack s==expected)
  T.Left e -> error (label++": "++B.unpack e)
  _ -> error (label++": expected text")
reject label mode p = announce label $ case compile mode p of
  T.Left _ -> check label True
  _ -> error (label++": unexpectedly accepted")
noChange label p = announce label $ case S.normalize T.ImplicitPrelude p of
  T.Right T.Nothing -> check label True
  T.Left e -> error (label++": "++B.unpack e)
  _ -> error (label++": changed ordinary AST")
abstract = T.SLam "x" (T.Just (ann (T.SArrow (ty "List" [ty "Int" []]) (ty "Pair" [ty "Bool" [],ty "Int" []])))) (v "x")
localEq = T.SClassDecl "Eq" (ls [(,) "a" T.Star]) []
  (ls [(,) "==" (T.SArrow (T.STVar "a") (T.SArrow (T.STVar "a") (ty "Int" [])))])
localEqInstance = T.SInstanceDecl [] [] "Eq" (ls [ty "Int" []])
  (ls [(,) "==" (lam "x" (lam "y" (lit 42)))])
localMonad = T.SClassDecl "Monad" (ls [(,) "a" T.Star]) []
  (ls [(,) "bind" (T.SArrow (T.STVar "a") (ty "Int" []))])
localMonadInstance = T.SInstanceDecl [] [] "Monad" (ls [ty "Int" []])
  (ls [(,) "bind" (lam "x" (lit 42))])
main = do
  hSetBuffering stdout LineBuffering
  args <- getArgs
  if args == ["--scope-timing"] then scopeTiming else if args == ["--equivalence"] then equivalence else if args == ["--source-boundaries"] then sourceBoundaries else allChecks
equivalence = do
  let compareOne label p = announce label $ case
        (compileWith S.normalize T.ImplicitPrelude p, compileWith S.normalizeDemanded T.ImplicitPrelude p) of
          (T.Right a,T.Right b) -> do
            check (label++" inferred type") (XT.alphaEq (C.inferredType a) (C.inferredType b))
            case (Check.checkClosed (C.compiledTerm a),Check.checkClosed (C.compiledTerm b)) of
              (T.Right ta,T.Right tb) -> check (label++" checked target") (XT.alphaEq ta tb)
              _ -> error "target check failed"
          (T.Left e,_) -> error (B.unpack e)
          (_,T.Left e) -> error (B.unpack e)
  compareOne "whole/demanded abstract nominal marker" (program (withMarker abstract))
  compareOne "whole/demanded Eq default with tuple context"
    (program (app (app (v "/=") (app (app (T.SConstructor "(,)") (lit 1)) (lit 2)))
      (app (app (T.SConstructor "(,)") (lit 1)) (lit 3))))
scopeTiming = do
  let one normalizer label = announce label $ case compileWith normalizer T.ImplicitPrelude (program (text "ok")) of
        T.Left e -> error (B.unpack e)
        T.Right c -> case Check.checkClosed (C.compiledTerm c) of
          T.Left e -> error (B.unpack e)
          T.Right target -> check label (XT.alphaEq target (C.inferredType c))
  a <- timeout 45000000 (one S.normalize "whole builtin reference")
  check "whole reference completed within45seconds" (maybe False (const True) a)
  b <- timeout 45000000 (one S.normalizeDemanded "demanded builtin candidate")
  check "demanded candidate completed within45seconds" (maybe False (const True) b)
sourceBoundaries = do
  let typed label source = case Parser.parseExpr "<standalone typed boundary>" source of
        T.Right (T.SLam "x" (T.Just _) _) -> check label True
        T.Left e -> error (B.unpack e)
        _ -> error (label ++ ": expected annotated lambda")
      cons label source = case Parser.parseExpr "<standalone cons boundary>" source of
        T.Right (T.SEquations [([T.SNestedPattern ":" [_,_]],_)]) -> check label True
        T.Right (T.SEquations [([T.SConstructorPattern ":" [_,_]],_)]) -> check label True
        T.Left e -> error (B.unpack e)
        _ -> error (label ++ ": expected canonical cons pattern, not annotation")
  typed "legacy forall annotation retains colon" "\\(x : forall a. a -> a) -> x x"
  typed "explicit double-colon annotation remains unambiguous" "\\(x :: Nil) -> x"
  cons "legacy canonical variable-tail cons pattern retains colon" "\\(x:xs) -> x"
  cons "legacy canonical constructor-tail cons pattern wins ambiguity" "\\(x:Nil) -> x"
  case Parser.parseExpr "<negative double>" "(-0.025)" of
    T.Right (T.SDoubleLit value) -> check "legacy negative Double parser preserves value" (value == -0.025)
    T.Left e -> error (B.unpack e)
    _ -> error "negative Double changed representation"
  case Parser.parseExpr "<legacy Bool>" "True" of
    T.Right expression -> do
      noChange "legacy Bool keeps class-free path" (program expression)
      case (C.compileProgram (program expression), C.compileProgram (program (T.SBoolLit True))) of
        (T.Right a,T.Right b) -> check "legacy Bool preserves target type and erasure"
          (XT.alphaEq (C.inferredType a) (C.inferredType b) && X.equalErased (X.erase (C.compiledTerm a)) (X.erase (C.compiledTerm b)))
        _ -> error "legacy Bool failed compilation"
    T.Left e -> error (B.unpack e)
  let branch name n = T.SAlternative (T.SConstructorPattern name []) (lit n)
  integer "source Boolean constructor marker is resolved" T.ImplicitPrelude
    (program (T.SCase (T.SConstructor "$MLF.Source.True")
      [branch "$MLF.Source.True" 42,branch "$MLF.Source.False" 0])) 42
  integer "source Boolean spelling respects local constructor identity" T.ImplicitPrelude
    (T.SProgram [T.DataDecl "OwnBoolean" [] [T.ConstructorDecl "True" []]]
      (T.SCase (T.SConstructor "$MLF.Source.True") [branch "$MLF.Source.True" 42])) 42
allChecks = do
  sourceBoundaries
  noChange "ordinary primitive reference fastpath" (program (v "addInt"))
  noChange "ordinary polymorphic identity fastpath" (program (lam "x" (v "x")))
  noChange "unknown abstract List/Pair annotations untouched" (program abstract)
  putStrLn "BEGIN mixed abstract nominal differential"
  case (compile T.ImplicitPrelude (program abstract),compile T.ImplicitPrelude (program (withMarker abstract))) of
    (T.Right a,T.Right b) -> check "mixed canonical marker preserves abstract nominal inferred type" (XT.alphaEq (C.inferredType a) (C.inferredType b))
    (T.Left e,_) -> error (B.unpack e)
    (_,T.Left e) -> error (B.unpack e)
  case (C.compileProgram (program abstract),compile T.ImplicitPrelude (program abstract)) of
    (T.Right a,T.Right b) -> do
      check "ordinary target type alphaEq" (XT.alphaEq (C.inferredType a) (C.inferredType b))
      check "ordinary target erasure unchanged" (X.equalErased (X.erase (C.compiledTerm a)) (X.erase (C.compiledTerm b)))
    _ -> error "ordinary differential compile failed"
  opaque "generated string bypasses local fromString" T.ImplicitPrelude
    (program (let_ "fromString" (lit 9) (text "ok"))) "ok"
  integer "ordinary fromString binder remains local" T.ImplicitPrelude
    (program (let_ "fromString" (lit 42) (withMarker (v "fromString")))) 42
  integer "ordinary mlfCallStack binder remains local" T.ImplicitPrelude
    (program (let_ "mlfCallStack" (lit 42) (withMarker (v "mlfCallStack")))) 42
  reject "free private accessor spelling is not captured" T.ImplicitPrelude
    (program (withMarker (v "mlfCallStack")))
  opaque "NoImplicitPrelude generated string still uses genuine builtin" T.NoImplicitPrelude (program (text "ok")) "ok"
  reject "NoImplicitPrelude ordinary facade name stays unavailable" T.NoImplicitPrelude
    (program (withMarker (v "pure")))
  integer "explicit equality uses lexical binder" T.ImplicitPrelude
    (program (let_ "==" (lam "a" (lam "b" (lit 42)))
      (withMarker (app (app (v "==") (lit 1)) (lit 2))))) 42
  integer "user Eq class identity remains independent" T.ImplicitPrelude
    (T.SClassProgram [] (ls [localEq]) (ls [localEqInstance])
      (withMarker (app (app (v "==") (lit 1)) (lit 2)))) 42
  case result T.ImplicitPrelude (T.SClassProgram [] (ls [localEq]) (ls [localEqInstance])
      (app (app (v "$MLF.Primitive.==") (lit 1)) (lit 2))) of
    T.Right (R.RBoolean False) -> check "generated equality ignores same-basename user class" True
    T.Left e -> error (B.unpack e)
    _ -> error "wrong canonical equality"
  reject "user Monad class cannot satisfy generated bind" T.ImplicitPrelude
    (T.SClassProgram [] (ls [localMonad]) (ls [localMonadInstance])
      (app (app (v "$MLF.Primitive.>>=") (lit 1)) (lam "x" (lit 2))))
  reject "unknown generated method fails closed" T.NoImplicitPrelude
    (program (v "$MLF.Primitive.notAReviewedHook"))
  reject "abstract List is not canonical list alias" T.ImplicitPrelude
    (program (withMarker (T.SAnn (T.SConstructor "[]") (ann (ty "List" [ty "Int" []])))))
  let used = ["ModuleEntity"++show n | n<-[0..250::Int]] ++ ["moduleEntity"++show n | n<-[0..250::Int]]
      guarded = foldr (\name e -> T.SLam (str name) (T.Just (ann (ty name []))) e) (text "ok") used
  case S.normalize T.ImplicitPrelude (program guarded) of
    T.Right (T.Just ((,,) imported _ _)) -> check "allocation avoids all binder and annotation names"
      (all (\n -> not (B.unpack n `elem` used)) (toList (Set.toList imported)))
    T.Left e -> error (B.unpack e)
    _ -> error "missing normalized allocation"
  integer "NoImplicitPrelude local pure remains local" T.NoImplicitPrelude
    (program (let_ "pure" (lit 42) (withMarker (v "pure")))) 42
  integer "NoImplicitPrelude intentional primitive spelling retained" T.NoImplicitPrelude
    (program (withMarker (app (app (v "addInt") (lit 20)) (lit 22)))) 42
  let privateType = T.DataDecl "MLFStackEvidence" [] (ls [T.ConstructorDecl "MLFStackEvidence" []])
      privateProgram = T.SProgram (ls [privateType])
        (withMarker (T.SCase (T.SAnn (T.SConstructor "MLFStackEvidence") (ann (ty "MLFStackEvidence" [])))
          (ls [T.SAlternative (T.SConstructorPattern "MLFStackEvidence" []) (lit 42)])))
  case S.normalize T.ImplicitPrelude privateProgram of
    T.Right (T.Just ((,,) _ normalized display)) -> case normalized of
      T.SClassProgram ds _ _ _ -> case toList ds of
        [T.DataDecl internal _ _] -> check "private local printed type name restored"
          (B.unpack (Modules.displayNames display internal)=="MLFStackEvidence" && internal/="MLFStackEvidence")
        _ -> error "private datatype inventory changed"
      _ -> error "private normalization shape"
    T.Left e -> error (B.unpack e)
    _ -> error "private declaration was not renamed"
  integer "local private type and constructor receive distinct identities" T.ImplicitPrelude privateProgram 42
  let privateClass = T.SClassDecl "MLFHasCallStack" (ls [(,) "a" T.Star]) []
        (ls [(,) "localStack" (T.SArrow (T.STVar "a") (ty "Int" []))])
      privateInstance = T.SInstanceDecl [] [] "MLFHasCallStack" (ls [ty "Int" []])
        (ls [(,) "localStack" (lam "x" (lit 42))])
  integer "local managed-looking class is not compiler evidence" T.ImplicitPrelude
    (T.SClassProgram [] (ls [privateClass]) (ls [privateInstance])
      (withMarker (app (v "localStack") (lit 1)))) 42
  let singleton x = app (app (T.SConstructor ":") x) (T.SConstructor "[]")
      firstOrZero e = T.SCase e (ls
        [T.SAlternative (T.SConstructorPattern ":" (ls [T.Just "first",T.Nothing])) (v "first"),
         T.SAlternative (T.SConstructorPattern "[]" []) (lit 0)])
      directDo = T.SDo (ls [T.SDoBind (T.SDefaultPattern (T.Just "x")) (singleton (lit 42))]) (singleton (v "x"))
  integer "raw direct-AST list do uses genuine Monad" T.ImplicitPrelude (program (firstOrZero directDo)) 42
  integer "raw do bypasses ordinary let-bound bind" T.ImplicitPrelude
    (program (let_ "bind" (lam "a" (lam "f" (singleton (lit 99)))) (firstOrZero directDo))) 42
  integer "raw direct-AST refutable bind dispatches MonadFail" T.NoImplicitPrelude
    (program (firstOrZero (T.SDo (ls [T.SDoBind (T.SIntPattern 0) (singleton (lit 1))]) (singleton (lit 42))))) 0
  let ownUnit = T.DataDecl "Unit" [] [T.ConstructorDecl "Unit" []]
      ownUnitBody = T.SCase (T.SAnn (T.SConstructor "Unit") (ann (ty "Unit" [])))
        [T.SAlternative (T.SConstructorPattern "Unit" []) (lit 42)]
  integer "user Unit is an ordinary distinct datatype" T.ImplicitPrelude
    (T.SProgram [ownUnit] (withMarker ownUnitBody)) 42
  reject "canonical unit cannot become user Unit" T.ImplicitPrelude
    (T.SProgram [ownUnit] (withMarker (T.SAnn (T.SConstructor "()") (ann (ty "Unit" [])))))
  let ownTombstone = T.DataDecl "MLFLegacyUnit" [] [T.ConstructorDecl "MLFLegacyUnit" []]
      ownTombstoneBody = T.SCase (T.SAnn (T.SConstructor "MLFLegacyUnit") (ann (ty "MLFLegacyUnit" [])))
        [T.SAlternative (T.SConstructorPattern "MLFLegacyUnit" []) (lit 42)]
  integer "user tombstone basename receives a private-free local identity" T.ImplicitPrelude
    (T.SProgram [ownTombstone] (withMarker ownTombstoneBody)) 42
  putStrLn "standalone scope controls passed"
toList []=[]
toList ((:) a as)=a:toList as
