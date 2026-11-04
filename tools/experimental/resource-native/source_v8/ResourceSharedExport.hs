{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Standalone diagnostic producer. Not export/3 and never a native credential.
module ResourceSharedExport (main, exportCaptured, normalizeSharedChecked) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.X.Checked as K;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified MLF.ResourceModules as Modules;
  import qualified MLF.ResourceProjection as Projection;
  import qualified MLF.ResourceExport as E;
  import qualified Package.Json as J;

  -- Reuse only structural proof parsing and closed, capture-avoiding type
  -- substitution. Never call closedVisit/closedLetAction/normalization routes
  -- that specialize a shared let or use erased paths for raw syntax.
  pathJson path = J.Array (L.map J.String path);
  child path key = L.append path [key];
  stateNode state path term = J.Object [
    ("state", J.num state), ("path", pathJson path),
    ("subtree", Modules.rawTerm term)];
  identity action = case action of { E.ClosedIdentity -> True; _ -> False };
  prefixNode ((,) binder bound) = J.Object [
    ("id", J.num (T.tyVarId binder)), ("bound", Modules.rawType bound)];
  substitutionNode ((,) ((,) binder _) argument) = J.Object [
    ("binder", J.num (T.tyVarId binder)), ("argument", Modules.rawType argument)];

  -- Diagnostic eligibility uses only the immutable outer declarations of the
  -- freshly K-checked input. Python independently enforces backend field rules.
  nominalArgument declarations argument = case argument of {
    XCon name [] -> case L.filter (\d -> eqString name (D.datatypeName d)) declarations of {
      [declaration] -> L.null (D.datatypeBinders declaration) && L.not (E.closedArgument argument);
      _ -> False
    };
    _ -> False
  };
  arrowArgument argument = case argument of { XArrow _ _ -> True; _ -> False };
  -- Only finite monomorphic arrows; nominal leaves stay exact closed atoms.
  -- Raw XMLF arrows carry no Once/result-identity refinements. The independent
  -- backend still checks recursively Repeat/unknown before runtime admission.
  sharedArgument declarations argument = sharedArgumentAt declarations 1 argument;
  sharedArgumentAt declarations depth argument = depth <= 32 && (case argument of {
    XArrow a b -> sharedArgumentAt declarations (depth + 1) a &&
      sharedArgumentAt declarations (depth + 1) b;
    _ -> E.closedArgument argument || nominalArgument declarations argument
  });
  applySharedPrefix declarations term arguments = case arguments of {
    [] -> do { L.ensure (L.null (E.closedPrefix term)) "partial shared closed forall elimination"; Right term };
    (:) argument rest -> case term of {
      XTypeAbs binder bound body -> do {
        L.ensure (E.bottomStar bound && sharedArgument declarations argument)
          "shared substitution requires a checked closed type and bottom Star";
        substituted <- E.closedSubstituteTerm binder argument body;
        applySharedPrefix declarations substituted rest
      };
      _ -> Left "extra shared closed forall elimination"
    }
  };

  -- A single leftmost outermost rewrite, with exact pre/post subtrees. The
  -- enclosing traversal rebuilds only the path to this one occurrence.
  direct nominals state path term = case term of {
    XTypeApp value witness -> case E.closedSpine term of { (,) base proofs -> do {
      actions <- E.closedActions proofs;
      let { arguments = E.closedActionArguments actions; prefix = E.closedPrefix base;
        scalar = L.all E.closedArgument arguments;
        extended = L.not scalar && L.all (sharedArgument nominals) arguments;
        dialect = if scalar then 1 else if L.any arrowArgument arguments then 3 else 2 };
      if L.not (L.null prefix) && L.not (L.null arguments) && (scalar || extended)
      then do {
        E.closedValidatePrefix prefix;
        L.ensure (L.length prefix == L.length arguments)
          "shared diagnostic: partial or extra immediate closed vector";
        output <- if scalar then E.closedApplyPrefix base arguments
          else applySharedPrefix nominals base arguments;
        let { step = J.Object [
          ("rule", J.String "instantiate_direct_closed"),
          ("input", stateNode state path term),
          ("type_binders", J.Array (L.map prefixNode prefix)),
          ("arguments", J.Array (L.map Modules.rawType arguments)),
          ("witnesses", J.Array (L.map E.computationNode proofs)),
          ("substitutions", J.Array (L.map substitutionNode (L.zip prefix arguments))),
          ("output", stateNode (state + 1) path output)] };
        Right (Just ((,) output ((,) step dialect)))
      } else do {
        outer <- E.closedProofActions witness;
        if L.all identity outer then Right (Just ((,) value ((,) (J.Object [
          ("rule", J.String "erase_refl"), ("input", stateNode state path term),
          ("witness", E.computationNode witness),
          ("output", stateNode (state + 1) path value)]) 1)))
        else Right Nothing
      }
    } };
    _ -> Right Nothing
  };
  lift constructor result = case result of {
    Nothing -> Nothing;
    Just ((,) value step) -> Just ((,) (constructor value) step)
  };
  visit nominals state path term = do {
    here <- direct nominals state path term;
    case here of {
      Just _ -> Right here;
      Nothing -> case term of {
        XAbs binder annotation body -> do {
          next <- visit nominals state (child path "body") body;
          Right (lift (XAbs binder annotation) next)
        };
        XApp function argument -> do {
          first <- visit nominals state (child path "function") function;
          case first of {
            Just _ -> Right (lift (\value -> XApp value argument) first);
            Nothing -> do {
              second <- visit nominals state (child path "argument") argument;
              Right (lift (XApp function) second)
            }
          }
        };
        XTypeAbs binder bound body -> do {
          next <- visit nominals state (child path "body") body;
          Right (lift (XTypeAbs binder bound) next)
        };
        XTypeApp value witness -> do {
          -- Unlike ResourceExport.closedVisit, the wrapper remains in the path.
          next <- visit nominals state (child path "value") value;
          Right (lift (\inner -> XTypeApp inner witness) next)
        };
        XLet binder value body -> do {
          first <- visit nominals state (child path "value") value;
          case first of {
            Just _ -> Right (lift (\rhs -> XLet binder rhs body) first);
            Nothing -> do {
              second <- visit nominals state (child path "body") body;
              Right (lift (XLet binder value) second)
            }
          }
        };
        XLetRec bindings body -> do {
          first <- visitBindings nominals state path 0 bindings;
          case first of {
            Just ((,) values step) -> Right (Just ((,) (XLetRec values body) step));
            Nothing -> do {
              second <- visit nominals state (child path "body") body;
              Right (lift (XLetRec bindings) second)
            }
          }
        };
        XCase subject result alternatives -> do {
          first <- visit nominals state (child path "scrutinee") subject;
          case first of {
            Just _ -> Right (lift (\value -> XCase value result alternatives) first);
            Nothing -> do {
              second <- visitAlternatives nominals state path 0 alternatives;
              case second of {
                Nothing -> Right Nothing;
                Just ((,) values step) -> Right (Just ((,) (XCase subject result values) step))
              }
            }
          }
        };
        XWithData declarations body -> do {
          next <- visit nominals state (child path "body") body;
          Right (lift (XWithData declarations) next)
        };
        XVarTerm _ -> Right Nothing;
        XIntTerm _ -> Right Nothing;
        XDoubleTerm _ -> Right Nothing;
        XBoolTerm _ -> Right Nothing;
        XStringTerm _ -> Right Nothing;
        XPrimitive _ _ -> Right Nothing;
        XConstructor _ _ -> Right Nothing
      }
    }
  };
  visitBindings nominals state path index bindings = case bindings of {
    [] -> Right Nothing;
    (:) ((,,) binder annotation value) rest -> do {
      first <- visit nominals state (L.append path ["bindings", showInt index, "value"]) value;
      case first of {
        Just ((,) rhs step) -> Right (Just ((,) ((:) ((,,) binder annotation rhs) rest) step));
        Nothing -> do {
          second <- visitBindings nominals state path (index + 1) rest;
          case second of {
            Nothing -> Right Nothing;
            Just ((,) values step) -> Right (Just ((,) ((:) ((,,) binder annotation value) values) step))
          }
        }
      }
    }
  };
  visitAlternatives nominals state path index alternatives = case alternatives of {
    [] -> Right Nothing;
    (:) (XAlternative pattern body) rest -> do {
      first <- visit nominals state (L.append path ["alternatives", showInt index, "body"]) body;
      case first of {
        Just ((,) value step) -> Right (Just ((,) ((:) (XAlternative pattern value) rest) step));
        Nothing -> do {
          second <- visitAlternatives nominals state path (index + 1) rest;
          case second of {
            Nothing -> Right Nothing;
            Just ((,) values step) -> Right (Just ((,) ((:) (XAlternative pattern body) values) step))
          }
        }
      }
    }
  };

  -- Include ALL JSON cells and type/proof/declaration children, not just terms.
  -- This finite stack walk precedes recursive normalization of the retained AST.
  boundRetained value = cells 0 [((,) 1 value)];
  cells count pending = case pending of {
    [] -> Right ();
    (:) ((,) depth value) rest -> do {
      let { next = count + 1 };
      L.ensure (next <= 10000 && depth <= 100)
        "shared diagnostic: retained JSON exceeds 10000 cells or depth100";
      let { children = case value of {
        J.Object fields -> L.map L.snd fields;
        J.Array values -> values;
        _ -> []
      } };
      cells next (L.append (L.map (\v -> (,) (depth + 1) v) children) rest)
    }
  };
  boundedUTF8 limit text = bytes 0 0 where {
    bytes index total = if index >= stringLength text then Right total else do {
      let { code = stringCodeAt text index;
        width = if code <= 127 then 1 else if code <= 2047 then 2 else if code <= 65535 then 3 else 4;
        next = total + width };
      L.ensure (code >= 0 && code <= 1114111 && L.not (code >= 55296 && code <= 57343))
        "shared diagnostic: invalid Unicode scalar";
      L.ensure (next <= limit) "shared diagnostic: UTF-8 byte budget exceeded";
      seq next (bytes (index + 1) next)
    }
  };
  declarations term = case term of {
    XWithData ds body -> (:) (Modules.rawDeclarations ds) (declarations body);
    XAbs _ _ body -> declarations body;
    XTypeAbs _ _ body -> declarations body;
    XTypeApp body _ -> declarations body;
    XApp a b -> L.append (declarations a) (declarations b);
    XLet _ a b -> L.append (declarations a) (declarations b);
    XLetRec bindings body -> L.append (L.concatMap (\((,,) _ _ rhs) -> declarations rhs) bindings) (declarations body);
    XCase subject _ alternatives -> L.append (declarations subject)
      (L.concatMap (\(XAlternative _ body) -> declarations body) alternatives);
    _ -> []
  };
  normalizeSharedChecked supplied = do {
    result <- normalizeSharedDialect supplied;
    case result of { (,,,) original checked steps _ -> Right ((,,) original checked steps) }
  };
  normalizeSharedDialect supplied = do {
    boundRetained (Modules.rawTerm (K.term supplied));
    original <- K.check (K.term supplied);
    L.ensure (T.alphaEq (K.typeOf supplied) (K.typeOf original))
      "shared diagnostic: supplied checked root changed";
    result <- loop (E.closedDeclarations (K.term original)) 0 (K.term original) [] 2 1;
    case result of { (,,) term steps dialect -> do {
      checked <- K.check term;
      L.ensure (T.alphaEq (K.typeOf original) (K.typeOf checked))
        "shared diagnostic: normalized root type changed";
      L.ensure (X.equalErased (X.erase (K.term original)) (X.erase term))
        "shared diagnostic: ordinary erasure/sharing changed";
      L.ensure (J.equal (J.Array (declarations (K.term original))) (J.Array (declarations term)))
        "shared diagnostic: declaration syntax changed";
      Right ((,,,) original checked steps dialect)
    } }
  };
  loop nominals state term reversedSteps stepBytes usedDialect = do {
    next <- visit nominals state [] term;
    case next of {
      Nothing -> Right ((,,) term (L.reverse reversedSteps) usedDialect);
      Just ((,) output ((,) step dialect)) -> do {
        L.ensure (state < 2048) "shared diagnostic: normalization exceeds2048 rewrites";
        boundRetained (Modules.rawTerm output);
        L.ensure (X.equalErased (X.erase term) (X.erase output))
          "shared diagnostic: a type rewrite changed ordinary erasure";
        let { separator = if state == 0 then 0 else 1 };
        width <- boundedUTF8 (4194304 - stepBytes - separator) (J.render step);
        loop nominals (state + 1) output ((:) step reversedSteps) (stepBytes + separator + width)
          (if dialect > usedDialect then dialect else usedDialect)
      }
    }
  };

  exportCaptured captured = do {
    projected <- Projection.projectChecked (Modules.checkedTerm captured);
    normalized <- normalizeSharedDialect (Projection.projected projected);
    case normalized of { (,,,) before after steps dialect -> do {
      let { original = Projection.original projected;
        normalization = J.Object [
          ("policy", J.String (if dialect == 3 then "shared-rank1-callable/3"
            else if dialect == 2 then "shared-rank1-callable/2" else "shared-rank1-callable/1")),
          ("input_checked_type", Modules.rawType (K.typeOf before)),
          ("input_annotated", Modules.rawTerm (K.term before)),
          ("input_erased", Modules.rawErased (X.erase (K.term before))),
          ("raw_normalized", Modules.rawTerm (K.term after)),
          ("steps", J.Array steps),
          ("original_rechecked", J.Boolean True), ("normalized_rechecked", J.Boolean True),
          ("root_type_alpha_equal", J.Boolean True), ("erasure_equal", J.Boolean True),
          ("declarations_equal", J.Boolean True)];
        output = J.Object [
          ("format", J.String "mlf-shared-source-capture/1"),
          ("status", J.String "diagnostic-not-runtime-admission"),
          ("producer", J.Object [("kind", J.String "standalone-haskell-diagnostic"),
            ("ordinary_api", J.String "MLF.ResourceModules.compileCaptured")]),
          ("module_custody", Modules.moduleCustody captured),
          ("original", J.Object [
            ("checked_type", Modules.rawType (K.typeOf original)),
            ("annotated", Modules.rawTerm (K.term original)),
            ("erased", Modules.rawErased (X.erase (K.term original))),
            ("source_erased", Modules.rawErased (Modules.sourceErasure captured)),
            ("binder_origins", Modules.binderOrigins captured),
            ("ordinary_whole_check_passed", J.Boolean True),
            ("root_type_alpha_equal", J.Boolean True), ("source_erasure_equal", J.Boolean True)]),
          ("projection", Projection.evidence projected),
          ("normalization", normalization),
          ("annotated", Modules.rawTerm (K.term after)),
          ("erased", Modules.rawErased (X.erase (K.term after))),
          ("checked_type", Modules.rawType (K.typeOf after)),
          ("limitations", J.Array (L.map J.String [
            "Not mlf-checked-module-export/3 and not source/native admission",
            "No complete polymorphism/representation/runtime-inventory join",
            "No source-to-IR carrier/allocation/term correspondence claim",
            "No source evaluation, specialization, inlining or body cloning"]))] };
      L.ensure (X.equalErased (X.erase (K.term original)) (Modules.sourceErasure captured))
        "shared diagnostic: captured source erasure differs from ordinary original";
      boundedUTF8 4194304 (J.render (J.Array steps));
      let { rendered = J.render output };
      boundedUTF8 33554432 rendered;
      Right rendered
    } }
  };
  fatal message = do { putErr (message ++ "\n"); exitWith 1 };
  main = do {
    count <- getArgCount;
    if count /= 1 then fatal "usage: shared-source-capture --capture-shared < root.emlf" else do {
      option <- getArg 0;
      if L.not (eqString option "--capture-shared") then fatal "expected --capture-shared" else do {
        input <- getContents;
        case boundedUTF8 1048576 input of {
          Left error -> fatal error;
          Right _ -> do {
            captured <- Modules.compileCaptured "<stdin>" input;
            case captured of {
              Left error -> fatal (Compiler.prettyError error);
              Right result -> case exportCaptured result of {
                Left error -> fatal ("SharedCapture: " ++ error);
                Right output -> putStrLn output
              }
            }
          }
        }
      }
    }
  };
}
