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
  patternVariables :: SPattern -> List String;
  patternVariables pattern =
    case pattern of {
      SAsPattern name inner -> Cons name (patternVariables inner);
      SLazyPattern inner -> patternVariables inner;
      SDefaultPattern name ->
        case name of {
          Nothing -> Nil;
          Just n -> Cons n Nil
        };
      SConstructorPattern _ names ->
        concatMap
          (\n ->
             case n of {
               Nothing -> Nil;
               Just a -> Cons a Nil
             })
          names;
      SNestedPattern _ patterns -> concatMap patternVariables patterns;
      SAnnotatedPattern n _ -> Cons n Nil;
      _ -> Nil
    };
  allNames :: SExpr -> List String;
  allNames expression =
    case expression of {
      SCallSite _ _ body -> allNames body;
      SSharedBind pattern action body binding failure ->
        append (patternVariables pattern) (concatMap allNames (Cons action (Cons body (Cons binding (Cons failure Nil)))));
      SVar name -> Cons name Nil;
      SConstructor name -> Cons name Nil;
      SLam name _ body -> Cons name (allNames body);
      SApp f a -> append (allNames f) (allNames a);
      SLet name a b -> Cons name (append (allNames a) (allNames b));
      SAnn a _ -> allNames a;
      SCase a alternatives ->
        append (allNames a)
          (concatMap (\(SAlternative p b) -> append (patternVariables p) (allNames b))
             alternatives);
      SEquations rows ->
        concatMap (\(Pair ps b) -> append (concatMap patternVariables ps) (allNames b)) rows;
      SLetRec definitions body ->
        append (concatMap (\(Triple n _ e) -> Cons n (allNames e)) definitions) (allNames body);
      SDo statements result -> append (concatMap statementNames statements) (allNames result);
      SChecked _ a -> allNames a;
      SWanted n candidates -> Cons n (map snd candidates);
      _ -> Nil
    };
  statementNames :: SStatement -> List String;
  statementNames statement =
    case statement of {
      SDoBind p e -> append (patternVariables p) (allNames e);
      SDoThen e -> allNames e;
      SDoLet n _ e -> Cons n (allNames e);
      SDoLetRec ds -> concatMap (\(Triple n _ e) -> Cons n (allNames e)) ds
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
      case found of { Pair declaration _ -> Right (length (D.datatypeConstructors declaration) == 1) }
    };
    SNestedPattern name patterns -> do {
      found <- D.lookupConstructor env name;
      case found of {
        Pair declaration _ -> if length (D.datatypeConstructors declaration) /= 1 then Right False
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
          fallback <- if cannotFail then freshPure Nil else do {
            e <- sharedGo env failure;
            freshPure (Cons (SAlternative (SDefaultPattern Nothing) e) Nil)
          };
          freshPure (SCase (SVar name) (Cons (SAlternative pattern b) fallback))
        }
      };
      freshPure (SApp (SApp f a) (SLam name Nothing continuation))
    };
    SCallSite n location body -> do { b <- sharedGo env body; freshPure (SCallSite n location b) };
    SLam n annotation body -> do { b <- sharedGo env body; freshPure (SLam n annotation b) };
    SApp a b -> do { x <- sharedGo env a; y <- sharedGo env b; freshPure (SApp x y) };
    SLet n a b -> do { x <- sharedGo env a; y <- sharedGo env b; freshPure (SLet n x y) };
    SAnn a ty -> do { x <- sharedGo env a; freshPure (SAnn x ty) };
    SCase a branches -> do {
      x <- sharedGo env a;
      bs <- mapM (\(SAlternative p b) -> do { y <- sharedGo env b; freshPure (SAlternative p y) }) branches;
      freshPure (SCase x bs)
    };
    SEquations rows -> do {
      rs <- mapM (\(Pair ps b) -> do { y <- sharedGo env b; freshPure (Pair ps y) }) rows;
      freshPure (SEquations rs)
    };
    SLetRec definitions body -> do {
      ds <- mapM (\(Triple n ty b) -> do { y <- sharedGo env b; freshPure (Triple n ty y) }) definitions;
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
              (\(Pair ps b) ->
                 do {
                   body <- go b;
                   freshPure (Pair ps body)
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
  goDefinition :: Triple String SAnnotation SExpr -> Fresh (Triple String SAnnotation SExpr);
  goDefinition (Triple n t a) =
    do {
      value <- go a;
      freshPure (Triple n t value)
    };
  block :: List SStatement -> SExpr -> Fresh SExpr;
  block statements result =
    case statements of {
      Nil -> freshPure result;
      Cons statement rest ->
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
                        Just a -> SAnn value2 a
                      })
                     continuation)
              };
            SDoThen action ->
              do {
                name <- freshName "doValue";
                binding (SDefaultPattern (Just name)) action continuation
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
  binding :: SPattern -> SExpr -> SExpr -> Fresh SExpr;
  binding pattern action continuation =
    do {
      value <- go action;
      result <-
        case pattern of {
          SDefaultPattern (Just name) -> freshPure (Pair name continuation);
          SDefaultPattern Nothing ->
            do {
              name <- freshName "doValue";
              freshPure (Pair name continuation)
            };
          _ ->
            do {
              name <- freshName "doValue";
              freshPure
                (Pair name (SCase (SVar name) (Cons (SAlternative pattern continuation) Nil)))
            }
        };
      case result of {
        Pair name body -> freshPure (SApp (SApp (SVar "bind") value) (SLam name Nothing body))
      }
    }
}
