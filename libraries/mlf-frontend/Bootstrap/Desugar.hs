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
  allNames expression =
    case expression of {
      SSourceDefinition body -> allNames body;
      SCallSite _ _ body -> allNames body;
      SSharedBind pattern action body binding failure ->
        append (patternVariables pattern) (concatMap allNames ((:) action ((:) body ((:) binding ((:) failure [])))));
      SVar name -> (:) name [];
      SConstructor name -> (:) name [];
      SLam name _ body -> (:) name (allNames body);
      SApp f a -> append (allNames f) (allNames a);
      SLet name a b -> (:) name (append (allNames a) (allNames b));
      SAnn a _ -> allNames a;
      SSignature a _ -> allNames a;
      SCase a alternatives ->
        append (allNames a)
          (concatMap (\(SAlternative p b) -> append (patternVariables p) (allNames b))
             alternatives);
      SEquations rows ->
        concatMap (\((,) ps b) -> append (concatMap patternVariables ps) (allNames b)) rows;
      SLetRec definitions body ->
        append (concatMap (\((,,) n _ e) -> (:) n (allNames e)) definitions) (allNames body);
      SDo statements result -> append (concatMap statementNames statements) (allNames result);
      SChecked _ a -> allNames a;
      SWanted n candidates -> (:) n (map snd candidates);
      _ -> []
    };
  statementNames :: SStatement -> [] String;
  statementNames statement =
    case statement of {
      SDoBind p e -> append (patternVariables p) (allNames e);
      SDoThen e -> allNames e;
      SDoLet n _ e -> (:) n (allNames e);
      SDoLetRec ds -> concatMap (\((,,) n _ e) -> (:) n (allNames e)) ds
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
