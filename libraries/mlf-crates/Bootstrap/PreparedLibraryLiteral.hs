-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedLibraryLiteral (rawLibrary, rawLibraryPieces) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.BuiltinPreludeLiteral as L;
  import qualified Bootstrap.PreparedLibraries as P;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.ArtifactStructure as Q;
  import qualified Bootstrap.Bitstream as W;

  -- An installed open object is one exact byte image plus its checked header.
  -- Ordinary package decoding supplies its fragments when an IR body is needed;
  -- no second AST can claim that image's identity.
  unitInterface value = case value of {
    Separate.UnitInterface identity dependencies exports declarations classes instances bindings fingerprint ->
      L.application "UnitInterface" [L.string identity, L.list (L.pair L.string L.string) dependencies,
        L.list L.entity exports, L.list L.declaration declarations, L.list L.sourceClass classes,
        L.list (L.pair L.string L.sourceInstance) instances,
        L.list (L.pair L.string L.typeLiteral) bindings, L.string fingerprint]
  };
  source value = case value of {
    P.LibrarySource identity path text digest syntax -> L.application "LibrarySource"
      [L.string identity, L.string path, L.string text, L.string digest, L.sourceSyntax syntax]
  };
  mode :: PreludeMode -> String;
  mode value = case value of {
    ImplicitPrelude -> "ImplicitPrelude";
    NoImplicitPrelude -> "NoImplicitPrelude"
  };
  rawLibrary :: P.RawLibrary -> IO (Either String String);
  rawLibrary value = do {
    result <- rawLibraryPieces value;
    ioReturn (mapEither (\((,) definitions expression) ->
      "let { " ++ definitions ++ " } in " ++ expression) result)
  };
  fragmentPiece value serial = let {
    pieces = L.termPieces (Separate.objectTerm value) serial;
    label = "mlfLiteralUnit" ++ showInt (L.pieceNext pieces);
    definition = label ++ " :: () -> UnitObject;\n" ++ label ++ " _ = " ++
      L.application "UnitObject" [unitInterface (Separate.objectInterface value), L.pieceText pieces] ++ ";\n"
  } in L.TermPieces (L.pieceNext pieces + 1)
    (append (L.pieceDefinitions pieces) [definition]) ("(" ++ label ++ " ())");
  closedObjectPiece value serial = let {
    units = L.listPieces (map fragmentPiece (Artifact.objectFragments value)) serial;
    label = "mlfLiteralObject" ++ showInt (L.pieceNext units);
    rendered = case value of {
      Artifact.OpenCrateObject _ _ -> panic "open literal dispatch invariant";
      Artifact.CrateObject iface _ -> L.application "CrateObject" [L.interface iface, L.pieceText units];
      Artifact.LegacyCrateObject iface _ -> L.application "LegacyCrateObject" [L.interface iface, L.pieceText units];
      Artifact.EnvelopeCrateObject legacy iface _ -> L.application "EnvelopeCrateObject"
        [L.boolean legacy, L.interface iface, L.pieceText units]
    };
    definition = label ++ " :: () -> CrateObject;\n" ++ label ++ " _ = " ++ rendered ++ ";\n"
  } in L.TermPieces (L.pieceNext units + 1) (append (L.pieceDefinitions units) [definition]) ("(" ++ label ++ " ())");
  encodedPiece metadata digest iface image serial = L.TermPieces serial []
    (L.application "EncodedLibraryObject" [L.string metadata, L.string digest, L.interface iface,
      L.application "(,)" ["(" ++ L.objectLiteral (fst image) ++ ")",
        "(" ++ L.objectLiteral (snd image) ++ ")"]]);
  recordedPiece :: [] Artifact.CrateInterface -> P.LibraryObject -> Int -> IO (Either String L.TermPieces);
  recordedPiece headers recorded serial = do {
    actual <- P.readLibraryObject headers recorded;
    case actual of {
      Left message -> ioReturn (Left message);
      Right object -> case if Artifact.envelopeMarked object || Artifact.openMarked object
          then checkObject object else Right () of {
        Left message -> ioReturn (Left message);
        Right () -> case recorded of {
          P.EncodedLibraryObject metadata digest iface image ->
            ioReturn (Right (encodedPiece metadata digest iface image serial));
          P.LibraryObject metadata digest value -> case value of {
            Artifact.OpenCrateObject iface package -> do {
              let { bytes = Open.packageBytes package };
              actualHash <- byteArrayDigest bytes;
              if not (eqString actualHash digest) then ioReturn (Left "prepared object image SHA mismatch") else do {
                size <- lengthByteArray bytes;
                image <- L.compilerImageFields bytes size;
                ioReturn (Right (encodedPiece metadata digest iface image serial))
              }
            };
            _ -> let { pieces = closedObjectPiece value serial } in ioReturn (Right
              (L.TermPieces (L.pieceNext pieces) (L.pieceDefinitions pieces)
                (L.application "LibraryObject" [L.string metadata, L.string digest, L.pieceText pieces])))
          }
        }
      }
    }
  };
  recordedPieces headers entries serial = case entries of {
    [] -> ioReturn (Right (L.TermPieces serial [] "[]"));
    (:) entry rest -> do {
      first <- recordedPiece headers entry serial;
      case first of {
        Left message -> ioReturn (Left message);
        Right pieces -> do {
          later <- recordedPieces headers rest (L.pieceNext pieces);
          ioReturn (mapEither (\tail -> L.TermPieces (L.pieceNext tail)
            (append (L.pieceDefinitions pieces) (L.pieceDefinitions tail))
            (L.application "(:)" [L.pieceText pieces, L.pieceText tail])) later)
        }
      }
    }
  };
  rawLibraryPieces :: P.RawLibrary -> IO (Either String ((,) String String));
  rawLibraryPieces value = case value of {
    P.RawLibrary identity schema prelude sources objects witnesses -> do {
      result <- recordedPieces (map P.libraryInterface objects) objects 0;
      ioReturn (mapEither (\pieces -> (,) (concatStringList (L.pieceDefinitions pieces))
        (L.application "RawLibrary"
          [L.string identity, L.string schema, mode prelude, L.list source sources, L.pieceText pieces,
           L.list L.sourceModule witnesses])) result)
    }
  };

  -- Literal generation preserves the ACTUAL interface instance bodies. The
  -- wire schema deliberately strips those bodies, so wire admission alone
  -- cannot bound this extra input. These adapters differ only at that field.
  unitValue :: Separate.UnitInterface -> W.Value;
  unitValue value = case value of {
    Separate.UnitInterface a b c d e f g h -> W.VNode 240
      [Q.toText a, Q.toList (Q.toPair Q.toText Q.toText) b,
       Q.toList Q.toEntity c, Q.toList Q.toDataDecl d,
       Q.toList Q.toSClassDecl e, Q.toList (Q.toPair Q.toText Q.toSInstanceDecl) f,
       Q.toList (Q.toPair Q.toText Q.toXType) g, Q.toText h]
  };
  interfaceValue :: Artifact.CrateInterface -> W.Value;
  interfaceValue value = case value of {
    Artifact.CrateInterface a b c d e f g h i j k l m -> W.VNode 242
      [Q.toText a, Q.toList (Q.toTriple Q.toText Q.toText Q.toText) b,
       Q.toList Q.toText c, Q.toList (Q.toPair Q.toText (Q.toList Q.toEntity)) d,
       Q.toList (Q.toPair Q.toText (Q.toList Q.toText)) e,
       Q.toList Q.toDataDecl f, Q.toList Q.toSClassDecl g,
       Q.toList (Q.toPair Q.toText Q.toSInstanceDecl) h,
       Q.toList Q.toDataDecl i, Q.toList (Q.toPair Q.toText Q.toXType) j,
       Q.toText k, Q.toText l, Q.toList (Q.toPair Q.toText Q.toBool) m]
  };
  fragmentValue :: Separate.UnitObject -> W.Value;
  fragmentValue value = W.VNode 241
    [unitValue (Separate.objectInterface value), Q.toXTerm (Separate.objectTerm value)];
  objectValue :: Artifact.CrateObject -> W.Value;
  objectValue value = case value of {
    Artifact.OpenCrateObject iface package -> W.VNode 244 [interfaceValue iface,
      Q.toList (\((,) owner fragment) -> W.VNode 245 [Q.toText owner,
        Q.toList Q.toDataDecl (Open.declarations (Open.context fragment)),
        Q.toList (Q.toPair Q.toXName Q.toXType) (Open.parameters fragment), Open.bodyValue fragment])
        (Open.packageFragments package)];
    _ -> W.VNode 243 [Q.toBool (Artifact.envelopeLegacyObject value),
      interfaceValue (Artifact.objectInterface value), Q.toList fragmentValue (Artifact.objectFragments value)]
  };

  data Scan = One Int W.Value | Many Int ([] W.Value);
  -- Explicit frames count occurrences, not physical sharing. All arithmetic
  -- is checked before addition. No literal/pretty output is materialized here.
  scan :: Artifact.CrateEnvelopeLimits -> [] Scan -> Int -> Int -> Either String ();
  scan limits tasks nodes bytes = case tasks of {
    [] -> Right ();
    (:) task rest -> case task of {
      Many depth values -> case values of {
        [] -> scan limits rest nodes bytes;
        (:) value more -> scan limits ((:) (One depth value) ((:) (Many depth more) rest)) nodes bytes
      };
      One depth value -> do {
        ensure (depth <= W.maxDepth W.defaultLimits) "prepared literal input depth limit exceeded";
        next <- Artifact.envelopeAdd "literal expanded nodes" (Artifact.envelopeMaxNodes limits) nodes 1;
        _ <- Artifact.envelopeAdd "literal expanded work" (Artifact.envelopeMaxWork limits) next bytes;
        case value of {
          W.VText text -> do {
            size <- W.utf8Size (Artifact.envelopeMaxText limits - bytes) text;
            total <- Artifact.envelopeAdd "literal expanded text" (Artifact.envelopeMaxText limits) bytes size;
            _ <- Artifact.envelopeAdd "literal expanded work" (Artifact.envelopeMaxWork limits) next total;
            scan limits rest next total
          };
          W.VNode _ fields -> scan limits ((:) (Many (depth + 1) fields) rest) next bytes;
          _ -> scan limits rest next bytes
        }
      }
    }
  };
  checkObjectWith :: Artifact.CrateEnvelopeLimits -> Artifact.CrateObject -> Either String ();
  checkObjectWith limits value = do {
    ensure (Artifact.envelopeValidLimits limits) "invalid prepared literal input limits";
    scan limits [One 1 (objectValue value)] 0 0
  };
  checkObject :: Artifact.CrateObject -> Either String ();
  checkObject value = do {
    checkObjectWith Artifact.crateEnvelopeLimits value;
    case value of {
      Artifact.OpenCrateObject _ package -> mapM_ (compose Open.audit snd) (Open.packageFragments package);
      _ -> mapEither (\_ -> ()) (Artifact.envelopePrepareMarkedLink Artifact.crateEnvelopeLimits value)
    }
  }
}
