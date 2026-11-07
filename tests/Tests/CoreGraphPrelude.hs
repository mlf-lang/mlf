-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.CoreGraphPrelude (prepareProvider, inspect) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.BuiltinPreludeLiteral as Literal;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.X.Type as T;

  -- Walk the returned production Typed tree without re-running generation.
  -- The tail accumulator retains both source site order and candidate order.
  sites :: Typed -> [] ([] EvidenceBinding) -> [] ([] EvidenceBinding);
  sites (Typed _ form) rest = case form of {
    FLambda _ _ child _ -> sites child rest;
    FApply left right _ _ -> sites left (sites right rest);
    FBinding _ rhs body _ -> sites rhs (sites body rest);
    FMatch subject _ branches -> sites subject
      (foldr (\(Branch _ body _) next -> sites body next) rest branches);
    FRecursive definitions body _ ->
      foldr (\(RecursiveDefinition _ _ rhs _ _) next -> sites rhs next)
        (sites body rest) definitions;
    FEvidence candidates -> (:) candidates rest;
    FChecked _ child _ -> sites child rest;
    _ -> rest
  };

  data Census = Census (Map String Int) Int;
  checkCandidate :: Map String XType -> Census -> EvidenceBinding -> Either String Census;
  checkCandidate provider original@(Census seen refs) candidate = case candidate of {
    EvidenceBinding _ (XName _ hint) _ _ ->
      if M.member compareString hint provider then Left "provider instance retained a graph-backed FEvidence reference"
      else Right original;
    DeclaredEvidenceBinding role (XName identity hint) ty ->
      case M.lookup compareString hint provider of {
        Nothing -> Right original;
        Just expected -> case role of {
          InstanceEvidence -> do {
            ensure (T.alphaEq ty expected) "direct FEvidence contract differs from the checked provider signature";
            case M.lookup compareString hint seen of {
              Just prior -> do {
                ensure (prior == identity) "direct FEvidence key used multiple lexical binders";
                Right (Census seen (refs + 1))
              };
              Nothing -> Right (Census (M.insert compareString hint identity seen) (refs + 1))
            }
          };
          _ -> Left "checked provider instance appeared under a non-instance FEvidence role"
        }
      }
  };
  providerSignatures :: Context.PreparedPrelude -> Either String (Map String XType);
  providerSignatures context = do {
    let { iface = Context.interface context;
          signatures = M.fromList compareString (Artifact.crateBindings iface);
          linked = Artifact.fragmentBindings (Context.linked context);
          keys = map fst (Artifact.crateInstances iface) };
    rows <- traverseEither (\key ->
      case (,) (M.lookup compareString key signatures) (M.lookup compareString key linked) of {
        (,) (Just ty) (Just ((,) _ actual)) -> do {
          ensure (T.alphaEq ty actual) "provider instance signature differs from the linked checked declaration";
          Right ((,) (C.targetNameHint key) ty)
        };
        _ -> Left "missing linked provider instance signature"
      }) keys;
    let { byHint = M.fromList compareString rows };
    ensure (M.size byHint == length keys) "provider instance hints are ambiguous";
    Right byHint
  };

  inspect :: Context.PreparedPrelude -> Constraints -> Either String ((,,) Int Int Int);
  inspect context constraints = do {
    provider <- providerSignatures context;
    let { wanted = sites (C.skeleton constraints) [] };
    result <- foldEither (foldEither (checkCandidate provider)) (Census M.empty 0) wanted;
    case result of {
      Census seen refs -> do {
        ensure (M.size seen == M.size provider) "checked provider instance missing from actual direct FEvidence";
        ensure (IS.size (IS.fromList (map snd (M.toList seen))) == M.size seen)
          "different checked provider instances shared a lexical binder";
        Right ((,,) (length wanted) (M.size seen) refs)
      }
    }
  };

  -- Use the current canonical source for the provider constraints and admit
  -- the actual build artifacts only if both checked images match those bytes.
  prepareProvider :: String -> String -> String -> IO (Either String ((,) Context.PreparedPrelude Constraints));
  prepareProvider identity interfaceFile objectFile =
    case Artifact.builtinPreludeWithConstraints of {
      Left message -> ioReturn (Left message);
      Right ((,) object constraints) -> do {
        rendered <- Literal.imageTexts object;
        case rendered of {
          Left message -> ioReturn (Left message);
          Right ((,) interfaceImage objectImage) -> do {
            interfaceEqual <- matchImage interfaceFile interfaceImage;
            objectEqual <- matchImage objectFile objectImage;
            ioReturn (do {
              interfaceEqual;
              objectEqual;
              context <- Context.prepareCheckedObject identity object;
              Right ((,) context constraints)
            })
          }
        }
      }
    };
  matchImage :: String -> String -> IO (Either String ());
  matchImage path image = do {
    raw <- Storage.readRaw path;
    decoded <- Storage.decodeBase64 image;
    case ((,) raw decoded) of {
      (,) (Right actual) (Right expected) -> do {
        same <- Storage.sameBytes actual expected;
        ioReturn (ensure same ("checked Prelude image differs: " ++ path))
      };
      (,) (Left message) _ -> ioReturn (Left message);
      (,) _ (Left message) -> ioReturn (Left message)
    }
  };

}
