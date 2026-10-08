-- | The implicit source prelude. Its dictionaries go through the same kind,
-- instance, inference, elaboration, and target checks as user declarations.
module MLF.Prelude (PreludeMode (..), withPrelude, monadClass, ioInstance) where

import qualified Data.Set as Set
import MLF.Kind
import qualified MLF.Primitive as P
import qualified MLF.Syntax as S
import qualified MLF.Surface as Surface

data PreludeMode = ImplicitPrelude | NoImplicitPrelude deriving (Eq, Show)

-- The set records imported class provenance, so local method names can shadow
-- imported methods without weakening duplicate checks among user declarations.
withPrelude :: PreludeMode -> S.Program -> (Set.Set String, S.Program)
withPrelude NoImplicitPrelude program = (Set.empty,program)
withPrelude ImplicitPrelude program
  -- A local class declaration shadows the imported class and its instances.
  | any ((== "Monad") . S.className) classes = (Set.empty,program)
  | not needed = (Set.empty,program)
  | otherwise = (Set.singleton "Monad",
      S.ClassProgram datatypes (monadClass : classes) (ioInstance : instances) body)
  where
    (datatypes,classes,instances,body) = case program of
      S.Program ds e -> (ds,[],[],e)
      S.ClassProgram ds cs is e -> (ds,cs,is,e)
    methods = Set.fromList [name | c <- classes, (name,_) <- S.classMethods c]
    expressions = body : [e | i <- instances, (_,e) <- S.instanceMethods i]
    names = Set.unions (map freeNames expressions) Set.\\ methods
    needed = not (Set.null (names `Set.intersection` Set.fromList ["return","bind"]))
      || any exprMentionsMonad expressions
      || any classMentionsMonad classes
      || any instanceMentionsMonad instances

monadClass :: S.ClassDecl
monadClass = S.ClassDecl "Monad" [("m",KArrow Star Star)] []
  [ ("return", forallType "a" (S.Arrow a (m a)))
  , ("bind", forallType "a" (forallType "b"
      (S.Arrow (m a) (S.Arrow (S.Arrow a (m b)) (m b)))))
  ]
  where
    a = S.TVar "a"
    b = S.TVar "b"
    m = S.TypeApp (S.TVar "m")
    forallType name = S.Forall S.Flexible name S.Bottom

ioInstance :: S.InstanceDecl
ioInstance = S.InstanceDecl [] [] "Monad" [S.Con "IO" []]
  [("return",S.Primitive P.IOReturn), ("bind",S.Primitive P.IOBind)]

-- Import only used declarations: pure eMLF terms should neither allocate
-- dictionaries nor change graph identities because an unused prelude exists.
-- In particular, do's implicit bind observes the same lexical scope as an
-- explicit application; a pattern or do-let scopes only over later statements.
freeNames :: S.Expr -> Set.Set String
freeNames expression = case expression of
  S.Var name -> Set.singleton name
  S.Lam name _ body -> Set.delete name (freeNames body)
  S.App f a -> freeNames f `Set.union` freeNames a
  S.Let name value body -> freeNames value `Set.union` Set.delete name (freeNames body)
  S.Ann value _ -> freeNames value
  S.Case value branches -> freeNames value `Set.union` Set.unions
    [freeNames body Set.\\ patternNames p | S.Alternative p body <- branches]
  S.Do statements result -> foldr statementNames (freeNames result) statements
  S.Equations _ -> Surface.freeNames expression
  S.LetRec definitions body -> Set.unions (freeNames body : [freeNames e | (_,_,e) <- definitions])
    Set.\\ Set.fromList [name | (name,_,_) <- definitions]
  S.Checked _ value -> freeNames value
  _ -> Set.empty
  where
    statementNames statement rest = case statement of
      S.DoBind p value -> Set.insert "bind" (freeNames value `Set.union` (rest Set.\\ patternNames p))
      S.DoThen value -> Set.insert "bind" (freeNames value `Set.union` rest)
      S.DoLet name _ value -> freeNames value `Set.union` Set.delete name rest
      S.DoLetRec ds -> Set.unions (rest : [freeNames a | (_,_,a) <- ds])
        Set.\\ Set.fromList [n | (n,_,_) <- ds]

patternNames :: S.Pattern -> Set.Set String
patternNames = Set.fromList . Surface.patternVariables

predicateMentionsMonad :: S.Predicate -> Bool
predicateMentionsMonad (S.Predicate name arguments) = name == "Monad" || any typeMentionsMonad arguments

typeMentionsMonad :: S.Type -> Bool
typeMentionsMonad ty = case ty of
  S.Qualified ps body -> any predicateMentionsMonad ps || typeMentionsMonad body
  S.Forall _ _ bound body -> typeMentionsMonad bound || typeMentionsMonad body
  S.Arrow a b -> typeMentionsMonad a || typeMentionsMonad b
  S.TypeApp f a -> typeMentionsMonad f || typeMentionsMonad a
  S.Con _ arguments -> any typeMentionsMonad arguments
  _ -> False

classMentionsMonad :: S.ClassDecl -> Bool
classMentionsMonad declaration = any predicateMentionsMonad (S.superclasses declaration)
  || any (typeMentionsMonad . snd) (S.classMethods declaration)

instanceMentionsMonad :: S.InstanceDecl -> Bool
instanceMentionsMonad declaration = S.instanceClass declaration == "Monad"
  || any predicateMentionsMonad (S.instanceContext declaration)
  || any typeMentionsMonad (S.instanceHead declaration)

exprMentionsMonad :: S.Expr -> Bool
exprMentionsMonad expression = case expression of
  S.Lam _ annotation body -> maybe False annotationMentionsMonad annotation || recurse body
  S.App f a -> recurse f || recurse a
  S.Let _ value body -> recurse value || recurse body
  S.Ann value annotation -> recurse value || annotationMentionsMonad annotation
  S.Case value branches -> recurse value || any (\(S.Alternative p body) -> patternMentionsMonad p || recurse body) branches
  S.Do statements result -> any statementMentionsMonad statements || recurse result
  S.Equations rows -> any (\(ps,b) -> any patternMentionsMonad ps || recurse b) rows
  S.LetRec definitions body -> any (\(_,a,e) -> annotationMentionsMonad a || recurse e) definitions || recurse body
  S.Checked ty value -> typeMentionsMonad ty || recurse value
  _ -> False
  where
    recurse = exprMentionsMonad
    annotationMentionsMonad (S.Annotation _ ty) = typeMentionsMonad ty
    statementMentionsMonad statement = case statement of
      S.DoBind p value -> patternMentionsMonad p || recurse value
      S.DoThen value -> recurse value
      S.DoLet _ annotation value -> maybe False annotationMentionsMonad annotation || recurse value
      S.DoLetRec ds -> any (\(_,a,e) -> annotationMentionsMonad a || recurse e) ds
    patternMentionsMonad p = case p of
      S.AnnotatedPattern _ a -> annotationMentionsMonad a
      S.NestedPattern _ ps -> any patternMentionsMonad ps
      _ -> False
