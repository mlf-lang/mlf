-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedLibraryLiteral (rawLibrary, rawLibraryPieces) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std (map, append, ensure);
  import qualified Bootstrap.BuiltinPreludeLiteral as L;
  import qualified Bootstrap.PreparedLibraries as P;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.ArtifactStructure as Q;
  import qualified Bootstrap.Bitstream as W;

  -- Lossless constructor serialization; no checked witness is serialized.
  -- Both host compilers consume the same canonical generated source module.
  unitInterface value = case value of {
    Separate.UnitInterface identity dependencies exports declarations classes instances bindings fingerprint ->
      L.application "UnitInterface" [L.string identity, L.list (L.pair L.string L.string) dependencies,
        L.list L.entity exports, L.list L.declaration declarations, L.list L.sourceClass classes,
        L.list (L.pair L.string L.sourceInstance) instances,
        L.list (L.pair L.string L.typeLiteral) bindings, L.string fingerprint]
  };
  fragment value = L.application "UnitObject"
    [unitInterface (Separate.objectInterface value), L.term (Separate.objectTerm value)];
  object :: Artifact.CrateObject -> String;
  object value = if Artifact.envelopeMarked value then case checkObject value of {
    Left message -> panic message;
    Right () -> objectV1 value
  } else objectV1 value;
  objectV1 :: Artifact.CrateObject -> String;
  objectV1 value = case value of {
    Artifact.CrateObject iface fragments -> L.application "CrateObject"
      [L.interface iface, L.list fragment fragments];
    Artifact.LegacyCrateObject iface fragments -> L.application "LegacyCrateObject"
      [L.interface iface, L.list fragment fragments];
    Artifact.EnvelopeCrateObject legacy iface fragments -> L.application "EnvelopeCrateObject"
      [L.boolean legacy, L.interface iface, L.list fragment fragments]
  };
  source value = case value of {
    P.LibrarySource identity path text digest syntax -> L.application "LibrarySource"
      [L.string identity, L.string path, L.string text, L.string digest, L.sourceSyntax syntax]
  };
  recordedObject value = case value of {
    P.LibraryObject metadata digest body -> L.application "LibraryObject"
      [L.string metadata, L.string digest, object body]
  };
  mode :: PreludeMode -> String;
  mode value = case value of {
    ImplicitPrelude -> "ImplicitPrelude";
    NoImplicitPrelude -> "NoImplicitPrelude"
  };
  -- Admission is at each actual object rendering point, not at RawLibrary
  -- entry. Earlier fields retain their original demand/error order.
  rawLibrary :: P.RawLibrary -> String;
  rawLibrary = rawLibraryV1;
  rawLibraryPieces :: P.RawLibrary -> (,) String String;
  rawLibraryPieces = rawLibraryPiecesV1;
  rawLibraryV1 :: P.RawLibrary -> String;
  rawLibraryV1 value = case value of {
    P.RawLibrary identity schema prelude sources objects witnesses -> L.application "RawLibrary"
      [L.string identity, L.string schema, mode prelude, L.list source sources, L.list recordedObject objects,
       L.list L.sourceModule witnesses]
  };
  fragmentPiece value serial = let {
    pieces = L.termPieces (Separate.objectTerm value) serial;
    label = "mlfLiteralUnit" ++ showInt (L.pieceNext pieces);
    definition = label ++ " :: () -> UnitObject;\n" ++ label ++ " _ = " ++
      L.application "UnitObject" [unitInterface (Separate.objectInterface value), L.pieceText pieces] ++ ";\n"
  } in L.TermPieces (L.pieceNext pieces + 1)
    (append (L.pieceDefinitions pieces) [definition]) ("(" ++ label ++ " ())");

  objectPiece :: Artifact.CrateObject -> Int -> L.TermPieces;
  objectPiece value serial = if Artifact.envelopeMarked value then case checkObject value of {
    Left message -> panic message;
    Right () -> objectPieceV1 value serial
  } else objectPieceV1 value serial;
  objectPieceV1 :: Artifact.CrateObject -> Int -> L.TermPieces;
  objectPieceV1 value serial = let {
    units = L.listPieces (map fragmentPiece (Artifact.objectFragments value)) serial;
    label = "mlfLiteralObject" ++ showInt (L.pieceNext units);
    rendered = case value of {
      Artifact.CrateObject iface _ -> L.application "CrateObject" [L.interface iface, L.pieceText units];
      Artifact.LegacyCrateObject iface _ -> L.application "LegacyCrateObject" [L.interface iface, L.pieceText units];
      Artifact.EnvelopeCrateObject legacy iface _ -> L.application "EnvelopeCrateObject"
        [L.boolean legacy, L.interface iface, L.pieceText units]
    };
    definition = label ++ " :: () -> CrateObject;\n" ++ label ++ " _ = " ++ rendered ++ ";\n"
  } in L.TermPieces (L.pieceNext units + 1) (append (L.pieceDefinitions units) [definition]) ("(" ++ label ++ " ())");
  recordedPiece value serial = case value of {
    P.LibraryObject metadata digest body -> let { pieces = objectPiece body serial } in
      L.TermPieces (L.pieceNext pieces) (L.pieceDefinitions pieces)
        (L.application "LibraryObject" [L.string metadata, L.string digest, L.pieceText pieces])
  };
  rawLibraryPiecesV1 :: P.RawLibrary -> (,) String String;
  rawLibraryPiecesV1 value = case value of {
    P.RawLibrary identity schema prelude sources objects witnesses -> let {
      pieces = L.listPieces (map recordedPiece objects) 0
    } in (,) (concatStringList (L.pieceDefinitions pieces))
      (L.application "RawLibrary"
        [L.string identity, L.string schema, mode prelude, L.list source sources, L.pieceText pieces,
         L.list L.sourceModule witnesses])
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
  objectValue value = W.VNode 243 [Q.toBool (Artifact.envelopeLegacyObject value),
    interfaceValue (Artifact.objectInterface value), Q.toList fragmentValue (Artifact.objectFragments value)];

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
    _ <- Artifact.envelopePrepareMarkedLink Artifact.crateEnvelopeLimits value;
    Right ()
  }
}
