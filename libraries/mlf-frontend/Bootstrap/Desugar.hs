-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Desugar where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Data as D;
  patternVariables :: SPattern -> [] String;
  patternVariables pattern =
    case pattern of {
      SAsPattern name inner -> (:) name (patternVariables inner);
      SLazyPattern inner -> patternVariables inner;
      SDefaultPattern name ->
        case name of {
          Nothing -> [];
          Just n -> (:) n []
        };
      SConstructorPattern _ names ->
        concatMap
          (\n ->
             case n of {
               Nothing -> [];
               Just a -> (:) a []
             })
          names;
      SNestedPattern _ patterns -> concatMap patternVariables patterns;
      SAnnotatedPattern n _ -> (:) n [];
      _ -> []
    };
  allNames :: SExpr -> [] String;
  allNames expression = namesBefore expression [];
  -- Thread the following occurrences through each subtree in source order.
  namesBefore expression rest = case expression of {
    SSourceDefinition body -> namesBefore body rest;
    SCallSite _ _ body -> namesBefore body rest;
    SSharedBind pattern action body binding failure -> append (patternVariables pattern)
      (namesBefore action (namesBefore body (namesBefore binding (namesBefore failure rest))));
    SVar n -> (:) n rest;
    SGlobal _ n -> (:) n rest;
    SDeclScope _ body -> namesBefore body rest;
    SWantedRefs n candidates -> (:) n (foldr (\candidate more -> (:) (termRefName (snd candidate)) more) rest candidates);
    SConstructor n -> (:) n rest;
    SLam n _ body -> (:) n (namesBefore body rest);
    SApp f a -> namesBefore f (namesBefore a rest);
    SLet n rhs body -> (:) n (namesBefore rhs (namesBefore body rest));
    SAnn body _ -> namesBefore body rest;
    SSignature body _ -> namesBefore body rest;
    SCase body arms -> namesBefore body (foldr (\(SAlternative pat rhs) more ->
      append (patternVariables pat) (namesBefore rhs more)) rest arms);
    SEquations rows -> foldr (\((,) ps rhs) more ->
      foldr (\pat tail -> append (patternVariables pat) tail) (namesBefore rhs more) ps) rest rows;
    SLetRec definitions body -> foldr definitionNamesBefore (namesBefore body rest) definitions;
    SDo statements body -> foldr statementNamesBefore (namesBefore body rest) statements;
    SChecked _ body -> namesBefore body rest;
    SWanted n candidates -> (:) n (foldr (\candidate more -> (:) (snd candidate) more) rest candidates);
    _ -> rest
  };
  -- Class initialization needs a set of spellings. Consume application
  -- operands and their enclosing binders directly in the same order as
  -- allNames, leaving uncommon forms to its ordinary name enumeration.
  reservedExpressionNames expression following = let {
    visit state term = case term of {
      SApp f a -> let { next = visit state f } in seq next (visit next a);
      SCallSite _ _ value -> visit state value;
      SSourceDefinition value -> visit state value; SDeclScope _ value -> visit state value;
      SVar name -> reserveName state name; SGlobal _ name -> reserveName state name;
      SConstructor name -> reserveName state name;
      SPrimitive _ -> state; SIntLit _ -> state; SBoolLit _ -> state;
      SStringLit _ -> state; SDoubleLit _ -> state;
      SLam name _ value -> let { next = reserveName state name } in seq next (visit next value);
      SLet name value body -> let {
        named = reserveName state name; next = seq named (visit named value)
      } in seq next (visit next body);
      SLetRec defs body -> let {
        definition prior ((,,) name _ value) = let { named = reserveName prior name } in seq named (visit named value);
        next = foldlStrict definition state defs
      } in seq next (visit next body);
      _ -> foldlStrict reserveName state (allNames term)
    };
    initial = visit NoNames expression
  } in seq initial (finishedNames (foldlStrict reserveName initial following));
  definitionNamesBefore ((,,) n _ expr) rest = (:) n (namesBefore expr rest);
  statementNames :: SStatement -> [] String;
  statementNames statement = statementNamesBefore statement [];
  statementNamesBefore statement rest = case statement of {
    SDoBind pat e -> append (patternVariables pat) (namesBefore e rest);
    SDoThen e -> namesBefore e rest;
    SDoLet n _ e -> (:) n (namesBefore e rest);
    SDoLetRec ds -> foldr definitionNamesBefore rest ds
  };
  -- Refutability is a property of resolved datatype families, not constructor
  -- spelling or how many constructors happen to be imported into scope.
  patternCannotFail :: DataEnv -> SPattern -> Either String Bool;
  patternCannotFail env pattern = case pattern of {
    SDefaultPattern _ -> Right True;
    SAnnotatedPattern _ _ -> Right True;
    SLazyPattern _ -> Right True;
    SAsPattern _ inner -> patternCannotFail env inner;
    SConstructorPattern name _ -> do {
      found <- D.lookupConstructor env name;
      case found of { (,) declaration _ -> Right (length (D.datatypeConstructors declaration) == 1) }
    };
    SNestedPattern name patterns -> do {
      found <- D.lookupConstructor env name;
      case found of {
        (,) declaration _ -> if length (D.datatypeConstructors declaration) /= 1 then Right False
          else do { results <- mapM (patternCannotFail env) patterns; Right (all (\x -> x) results) }
      }
    };
    _ -> Right False
  };
  lowerSharedDo :: DataEnv -> SExpr -> Either String SExpr;
  lowerSharedDo env expression = runFresh (allNames expression) (sharedGo env expression);
  sharedGo :: DataEnv -> SExpr -> Fresh SExpr;
  sharedGo env expression = case expression of {
    SSharedBind pattern action body binding failure -> do {
      a <- sharedGo env action; b <- sharedGo env body;
      f <- sharedGo env binding;
      name <- case pattern of {
        SDefaultPattern (Just n) -> freshPure n;
        _ -> freshName "sharedPatternValue"
      };
      continuation <- case pattern of {
        SDefaultPattern _ -> freshPure b;
        _ -> do {
          cannotFail <- case patternCannotFail env pattern of { Left e -> freshFail e; Right result -> freshPure result };
          fallback <- if cannotFail then freshPure [] else do {
            e <- sharedGo env failure;
            freshPure ((:) (SAlternative (SDefaultPattern Nothing) e) [])
          };
          freshPure (SCase (SVar name) ((:) (SAlternative pattern b) fallback))
        }
      };
      freshPure (SApp (SApp f a) (SLam name Nothing continuation))
    };
    SDeclScope ids body -> do { b <- sharedGo env body; freshPure (SDeclScope ids b) };
    SSourceDefinition body -> do { b <- sharedGo env body; freshPure (SSourceDefinition b) };
    SCallSite n location body -> do { b <- sharedGo env body; freshPure (SCallSite n location b) };
    SLam n annotation body -> do { b <- sharedGo env body; freshPure (SLam n annotation b) };
    SApp a b -> do { x <- sharedGo env a; y <- sharedGo env b; freshPure (SApp x y) };
    SLet n a b -> do { x <- sharedGo env a; y <- sharedGo env b; freshPure (SLet n x y) };
    SAnn a ty -> do { x <- sharedGo env a; freshPure (SAnn x ty) };
    SSignature a ty -> do { x <- sharedGo env a; freshPure (SSignature x ty) };
    SCase a branches -> do {
      x <- sharedGo env a;
      bs <- mapM (\(SAlternative p b) -> do { y <- sharedGo env b; freshPure (SAlternative p y) }) branches;
      freshPure (SCase x bs)
    };
    SEquations rows -> do {
      rs <- mapM (\((,) ps b) -> do { y <- sharedGo env b; freshPure ((,) ps y) }) rows;
      freshPure (SEquations rs)
    };
    SLetRec definitions body -> do {
      ds <- mapM (\((,,) n ty b) -> do { y <- sharedGo env b; freshPure ((,,) n ty y) }) definitions;
      b <- sharedGo env body; freshPure (SLetRec ds b)
    };
    SChecked ty body -> do { b <- sharedGo env body; freshPure (SChecked ty b) };
    SDo _ _ -> sharedGo env (desugarDo expression);
    _ -> freshPure expression
  };
  desugarDo :: SExpr -> SExpr;
  desugarDo expression =
    case runFresh (allNames expression) (go expression) of {
      Left error -> panic error;
      Right result -> result
    };
  go :: SExpr -> Fresh SExpr;
  go expression =
    case expression of {
      SDeclScope ids body -> do { b <- go body; freshPure (SDeclScope ids b) };
      SSourceDefinition body -> do { b <- go body; freshPure (SSourceDefinition b) };
      SCallSite name location body -> do {
        result <- go body; freshPure (SCallSite name location result)
      };
      SSharedBind pattern action body binding failure -> do {
        a <- go action; b <- go body; f <- go binding; e <- go failure;
        freshPure (SSharedBind pattern a b f e)
      };
      SLam n a b ->
        do {
          body <- go b;
          freshPure (SLam n a body)
        };
      SApp a b ->
        do {
          f <- go a;
          x <- go b;
          freshPure (SApp f x)
        };
      SLet n a b ->
        do {
          value <- go a;
          body <- go b;
          freshPure (SLet n value body)
        };
      SAnn a t ->
        do {
          value <- go a;
          freshPure (SAnn value t)
        };
      SSignature a t ->
        do {
          value <- go a;
          freshPure (SSignature value t)
        };
      SCase a alternatives ->
        do {
          value <- go a;
          branches <-
            mapM
              (\(SAlternative p b) ->
                 do {
                   body <- go b;
                   freshPure (SAlternative p body)
                 })
              alternatives;
          freshPure (SCase value branches)
        };
      SEquations rows ->
        do {
          rows2 <-
            mapM
              (\((,) ps b) ->
                 do {
                   body <- go b;
                   freshPure ((,) ps body)
                 })
              rows;
          freshPure (SEquations rows2)
        };
      SDo statements result ->
        do {
          end <- go result;
          block statements end
        };
      SLetRec definitions body ->
        do {
          ds <- mapM goDefinition definitions;
          end <- go body;
          freshPure (SLetRec ds end)
        };
      SChecked ty a ->
        do {
          value <- go a;
          freshPure (SChecked ty value)
        };
      _ -> freshPure expression
    };
  goDefinition :: (,,) String RecursiveMode SExpr -> Fresh ((,,) String RecursiveMode SExpr);
  goDefinition ((,,) n mode a) =
    do {
      value <- go a;
      freshPure ((,,) n mode value)
    };
  block :: [] SStatement -> SExpr -> Fresh SExpr;
  block statements result =
    case statements of {
      [] -> freshPure result;
      (:) statement rest ->
        do {
          continuation <- block rest result;
          case statement of {
            SDoLet n annotation value ->
              do {
                value2 <- go value;
                freshPure
                  (SLet n
                     (case annotation of {
                        Nothing -> value2;
                        Just a -> SSignature value2 a
                      })
                     continuation)
              };
            SDoThen action ->
              do {
                value <- go action;
                freshPure (SApp (SApp (SVar "$MLF.Primitive.>>") value) continuation)
              };
            SDoBind pattern action -> binding pattern action continuation;
            SDoLetRec definitions ->
              do {
                ds <- mapM goDefinition definitions;
                freshPure (SLetRec ds continuation)
              }
          }
        }
    };
  -- Public raw AST do nodes use the same canonical, deferred pattern path as
  -- source do. No ordinary lexical bind/fail name can intercept this lowering.
  binding :: SPattern -> SExpr -> SExpr -> Fresh SExpr;
  binding pattern action continuation =
    do {
      value <- go action;
      freshPure (SSharedBind pattern value continuation (SVar "$MLF.Primitive.>>=")
        (SApp (SCallSite "a do statement"
          (SourceSpan "main" "<direct-ast>" "<generated>" 0 0 0 0)
          (SVar "$MLF.Primitive.fail"))
          (SApp (SPrimitive PTextToChars) (SStringLit "Pattern match failure in do expression"))))
    }
}
