-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as A;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.CrateArtifact as Crate;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Std as Std;
  import qualified Bootstrap.X.Pretty as Pretty;
  require :: String -> Bool -> IO ();
  require label okay = if okay then return () else panic label;
  fill :: ByteArray -> Int -> IO ();
  fill bytes index = if index == 256 then return () else do {
    writeByteArray bytes index index; fill bytes (index + 1)
  };
  equalBytes :: ByteArray -> Int -> Int -> IO Bool;
  equalBytes bytes count index = if index == count then return True else do {
    value <- readByteArray bytes index;
    if value == index then equalBytes bytes count (index + 1) else return False
  };
  okayRead :: String -> Int -> Int -> IO ();
  okayRead path limit count = do {
    (message, bytes) <- readByteFileOrError path limit;
    size <- lengthByteArray bytes;
    exact <- if size == count then equalBytes bytes count 0 else return False;
    require "raw successful read preserves exact bytes" (message == "" && exact)
  };
  badRead :: String -> Int -> String -> IO ();
  badRead path limit expected = do {
    (message, bytes) <- readByteFileOrError path limit;
    size <- lengthByteArray bytes;
    require "raw failure returns diagnostic and no partial bytes" (message == expected && size == 0)
  };
  writeOkay :: String -> ByteArray -> IO ();
  writeOkay path bytes = do {
    message <- writeByteFileOrError path bytes;
    require "raw successful write" (message == "")
  };
  fillPattern :: ByteArray -> Int -> Int -> IO ();
  fillPattern bytes count index = if index == count then return () else do {
    writeByteArray bytes index (remInt index 256); fillPattern bytes count (index + 1)
  };
  digestBoundaries :: String -> [] Int -> IO ();
  digestBoundaries root sizes = case sizes of {
    [] -> return ();
    (:) size rest -> do {
      bytes <- newByteArray size 0;
      fillPattern bytes size 0;
      let { name = "sha-" ++ showInt size ++ ".bin" };
      writeOkay (root ++ "/" ++ name) bytes;
      fingerprint <- byteArrayDigest bytes;
      putStrLn ("DIGEST " ++ name ++ " " ++ fingerprint);
      digestBoundaries root rest
    }
  };
  rawMain :: IO ();
  rawMain = do {
    root <- getLine;
    sink <- getLine;
    let { allPath = root ++ "/allbytes.bin" };
    let { emptyPath = root ++ "/empty.bin" };
    empty <- newByteArray 0 0;
    bytes <- newByteArray 256 0;
    fill bytes 0;
    writeOkay emptyPath empty;
    writeOkay allPath bytes;
    okayRead emptyPath 0 0;
    okayRead allPath 256 256;
    okayRead allPath 257 256;
    badRead allPath 0 "byte file exceeds limit";
    badRead allPath 255 "byte file exceeds limit";
    badRead (root ++ "/missing") 256 "IO error: byte file read failed";
    badRead allPath (-1) "invalid byte file limit";
    badRead allPath 9223372036854775807 "invalid byte file limit";
    badRead (allPath ++ stringFromCode 0 ++ "suffix") (-1) "file path contains NUL";
    invalid <- writeByteFileOrError (root ++ "/nul-created" ++ stringFromCode 0 ++ "suffix") bytes;
    require "raw NUL write rejected" (invalid == "file path contains NUL");
    parent <- writeByteFileOrError (root ++ "/missing-parent/file") bytes;
    require "raw missing parent write rejected" (parent == "IO error: byte file write failed");
    failed <- writeByteFileOrError root bytes;
    require "raw directory write rejected" (failed == "IO error: byte file write failed");
    digest0 <- byteArrayDigest empty;
    digest1 <- byteArrayDigest bytes;
    writeByteArray bytes 0 255;
    digest2 <- byteArrayDigest bytes;
    writeOkay (root ++ "/changed.bin") bytes;
    require "raw snapshot digest distinguishes mutation" (digest1 /= digest2);
    writeOkay allPath empty;
    retained <- byteArrayDigest bytes;
    require "raw digest does not reopen pathname" (retained == digest2);
    writeByteArray bytes 0 0;
    writeOkay allPath bytes;
    putStrLn ("DIGEST empty.bin " ++ digest0);
    putStrLn ("DIGEST allbytes.bin " ++ digest1);
    putStrLn ("DIGEST changed.bin " ++ digest2);
    digestBoundaries root [1,55,56,63,64,65,127,128,129,4095,4096,4097];
    short <- newByteArray 8192 255;
    failure <- writeByteFileOrError sink short;
    require "raw partial/close failure is not success" (failure == "IO error: byte file write failed");
    let { roots = [W.VInt (-9223372036854775808), W.VInt 9223372036854775807,
                 W.VBits (-9223372036854775808), W.VBits 9221120237041090561,
                 W.VText ("α😀" ++ stringFromCode 0),
                 W.VNode 31 [W.VInt (-7), W.VText "hint"],
                 W.VNode 31 [W.VInt (-7), W.VText "hint"]] };
    encoded <- W.encode W.defaultLimits 7 roots;
    case encoded of {
      Left message -> panic message;
      Right blob -> do {
        writeOkay (root ++ "/shared-wire.bin") blob;
        decoded <- W.decode W.defaultLimits 7 blob;
        case decoded of {
          Left message -> panic message;
          Right values -> do {
            reencoded <- W.encode W.defaultLimits 7 values;
            case reencoded of {
              Left message -> panic message;
              Right blob2 -> do {
                first <- byteArrayDigest blob; second <- byteArrayDigest blob2;
                require "native wire deterministic bytes" (first == second)
              }
            }
          }
        }
      }
    };
    putStrLn "PASS shared-raw-binary"
  };

  right :: forall a. Either String a -> IO a;
  right value = case value of { Left message -> panic message; Right result -> return result };
  binaryGraph :: Int -> String -> IO W.Graph;
  binaryGraph schema path = do {
    input <- Storage.read schema path >>= right;
    case input of { Storage.LegacyText _ -> panic "new typed storage unexpectedly text";
      Storage.BinaryInput graph -> return graph }
  };
  oneRoot :: W.Graph -> Int;
  oneRoot graph = case W.graphRoots graph of {
    (:) root [] -> root; _ -> panic "exactly one typed root required"
  };
  rawUnit :: XTerm -> Separate.UnitObject;
  rawUnit term = Separate.UnitObject
    (Separate.UnitInterface "NativeAdmission" [] [] [] [] [] []
      (Separate.fingerprint (Pretty.prettyTerm term))) term;
  typedMain :: String -> IO ();
  typedMain root = do {
    let { raw = rawUnit (XIntTerm 41) };
    Storage.write 7 (root ++ "/typed-raw.bin")
      [A.toKind (KArrow Star Star), A.toRawUnitObject raw] >>= right;
    graph <- binaryGraph 7 (root ++ "/typed-raw.bin");
    case W.graphRoots graph of {
      (:) kindID ((:) rawID []) -> do {
        kind <- right (A.fromGraphKind graph kindID);
        require "native typed Kind graph" (case kind of { KArrow Star Star -> True; _ -> False });
        restored <- right (A.fromGraphRawUnitObject graph rawID);
        require "typed decoder exposes raw syntax only" (case restored of {
          Separate.UnitObject _ (XIntTerm 41) -> True; _ -> False });
        checked <- right (Storage.checkUnit restored);
        require "production admission establishes evidence" (case checked of {
          Separate.CheckedUnitObject _ _ -> True; _ -> False })
      };
      _ -> panic "native typed graph root inventory"
    };
    let { malformed = rawUnit (XVarTerm (XName (-1) "x")) };
    Storage.write 7 (root ++ "/typed-bad.bin") [A.toRawUnitObject malformed] >>= right;
    badGraph <- binaryGraph 7 (root ++ "/typed-bad.bin");
    badRaw <- right (A.fromGraphRawUnitObject badGraph (oneRoot badGraph));
    case Storage.checkUnit badRaw of {
      Left message -> require "native exact production syntax refusal"
        (message == "binary artifact syntax admission: invalid term identity or hint");
      Right _ -> panic "native accepted invalid identity"
    };
    let { declarations = [DataDecl "NativeToken" [] [ConstructorDecl "NativeToken" []]] };
    right (Storage.admit [Storage.AdmitData True declarations]);
    Storage.write 1 (root ++ "/typed-context.bin") [A.toDataContext declarations] >>= right;
    contextGraph <- binaryGraph 1 (root ++ "/typed-context.bin");
    context <- right (A.fromGraphDataContext contextGraph (oneRoot contextGraph));
    require "native schema1 declarations retained" (case context of {
      (:) (DataDecl name [] ((:) (ConstructorDecl constructor []) [])) [] ->
        name == "NativeToken" && constructor == "NativeToken";
      _ -> False
    });
    let {
      empty = W.VNode 1 [];
      names = W.VNode 1 [A.toXName (XName 9 "typed-batch")];
      emptyPair = W.VNode 2 [empty, empty];
      mixedPair = W.VNode 2 [names, names]
    };
    batchBytes <- W.encode W.defaultLimits 7
      [emptyPair, mixedPair, A.toXTerm (XIntTerm 41), A.toXTerm (XIntTerm 42)] >>= right;
    batchGraph <- W.decodeGraph W.defaultLimits 7 batchBytes >>= right;
    case W.graphRoots batchGraph of {
      [emptyID, mixedID, firstID, secondID] -> do {
        emptyBatch <- right (A.decodeGraphMany A.ShapeXTerm batchGraph []);
        require "typed batch accepts no roots" (Std.null emptyBatch);
        emptyResult <- right (A.decodeGraphMany
          (A.ShapePair (A.ShapeList A.ShapeText) (A.ShapeList A.ShapeXName))
          batchGraph [emptyID]);
        require "batch shared empty list retains recursive shape" (case emptyResult of {
          [A.DecodedPair (A.DecodedList []) (A.DecodedList [])] -> True; _ -> False
        });
        case A.decodeGraphMany
          (A.ShapePair (A.ShapeList A.ShapeXName) (A.ShapeList A.ShapeText))
          batchGraph [mixedID] of {
          Left _ -> return ();
          Right _ -> panic "batch reused one node under an incompatible recursive shape"
        };
        ordered <- right (A.decodeGraphMany A.ShapeXTerm batchGraph
          [firstID, secondID, firstID]);
        require "batch retains root order and repetitions" (case ordered of {
          [A.DecodedXTerm (XIntTerm 41), A.DecodedXTerm (XIntTerm 42),
           A.DecodedXTerm (XIntTerm 41)] -> True;
          _ -> False
        });
        otherBytes <- W.encode W.defaultLimits 7
          [emptyPair, mixedPair, A.toXTerm (XIntTerm 43), A.toXTerm (XIntTerm 44)] >>= right;
        otherGraph <- W.decodeGraph W.defaultLimits 7 otherBytes >>= right;
        case W.graphRoots otherGraph of {
          [_, _, otherID, _] -> do {
            require "cross-graph test reuses the same numeric node ID" (otherID == firstID);
            result <- right (A.decodeGraphMany A.ShapeXTerm otherGraph [otherID]);
            require "batch memo is graph-local" (case result of {
              [A.DecodedXTerm (XIntTerm 43)] -> True; _ -> False
            })
          };
          _ -> panic "cross-graph batch fixture roots"
        }
      };
      _ -> panic "typed batch fixture roots"
    };
    putStrLn "PASS shared-typed-graph-and-admission"
  };
  -- Compare every retained semantic field, not the storage-dependent object SHA.
  -- The task stack preserves deep syntax and IEEE bit patterns exactly.
  data SameSyntaxTask = SameSyntaxValue W.Value W.Value |
    SameSyntaxList ([] W.Value) ([] W.Value);
  sameSyntax :: [] SameSyntaxTask -> Bool;
  sameSyntax tasks = case tasks of {
    [] -> True;
    (:) task rest -> case task of {
      SameSyntaxList left right -> case left of {
        [] -> case right of { [] -> sameSyntax rest; _ -> False };
        (:) a more -> case right of {
          (:) b following -> sameSyntax
            ((:) (SameSyntaxValue a b) ((:) (SameSyntaxList more following) rest));
          _ -> False
        }
      };
      SameSyntaxValue left right -> case left of {
        W.VInt a -> case right of { W.VInt b -> a == b && sameSyntax rest; _ -> False };
        W.VBits a -> case right of { W.VBits b -> a == b && sameSyntax rest; _ -> False };
        W.VText a -> case right of { W.VText b -> a == b && sameSyntax rest; _ -> False };
        W.VNode tag fields -> case right of {
          W.VNode other more -> tag == other &&
            sameSyntax ((:) (SameSyntaxList fields more) rest);
          _ -> False
        }
      }
    }
  };
  fragmentSyntax ((,) name fragment) = W.VNode 433
    [A.toText name, A.toText (Open.fingerprint fragment),
     A.toList Open.declarationValue (Open.declarations (Open.context fragment)),
     A.toList (A.toPair A.toXName (Std.compose A.toXType Separate.normalType))
       (Open.parameters fragment),
     A.toXTerm (Open.body fragment),
     A.toList (A.toPair A.toXName (Std.compose A.toXType Separate.normalType))
       (Open.bindings fragment),
     A.toList A.toXName (Open.usedParameters fragment)];
  sameFragments left right = sameSyntax
    [SameSyntaxList (Std.map fragmentSyntax left) (Std.map fragmentSyntax right)];
  sameOpenMeaning original package restored reread =
    Crate.encodeInterface (Crate.withObjectFingerprint original "open-object") ==
      Crate.encodeInterface (Crate.withObjectFingerprint restored "open-object") &&
    Open.packageMetadata package == Open.packageMetadata reread &&
    sameFragments (Open.packageFragments package) (Open.packageFragments reread);
  formalMain :: String -> String -> IO ();
  formalMain input output = do {
    iface <- Crate.readInterface (input ++ ".mlfci") >>= right;
    object <- Crate.readObject (input ++ ".mlfco") iface >>= right;
    Crate.writeObjectEither output object >>= right;
    reread <- Crate.readInterface (output ++ ".mlfci") >>= right;
    rebuilt <- Crate.readObject (output ++ ".mlfco") reread >>= right;
    require "public interface semantic identity" (Crate.encodeInterface iface == Crate.encodeInterface reread);
    require "public object semantic identity" (Crate.encodeObject object == Crate.encodeObject rebuilt);
    case object of {
      Crate.OpenCrateObject original package -> do {
        imported <- Crate.loadInterfaces (Std.map Crate.dependencyPath (Crate.crateDependencies original)) >>= right;
        audited <- right (Std.traverseEither (\((,) name fragment) ->
          Std.mapEither ((,) name) (Open.audit fragment)) (Open.packageFragments package));
        require "retained checker preserves complete fragment semantics"
          (sameFragments (Open.packageFragments package) audited);
        case rebuilt of {
          Crate.OpenCrateObject _ transferred -> do {
            exact <- Storage.sameBytes (Open.packageBytes package) (Open.packageBytes transferred);
            require "open public transfer preserves original object bytes" exact
          };
          _ -> panic "open public transfer changed family"
        };
        checked <- Crate.makeOpenObject original (Std.map Std.snd imported) audited >>= right;
        Crate.writeObjectEither (output ++ "-audited") checked >>= right;
        checkedInterface <- Crate.readInterface (output ++ "-audited.mlfci") >>= right;
        checkedObject <- Crate.readObject (output ++ "-audited.mlfco") checkedInterface >>= right;
        case checkedObject of {
          Crate.OpenCrateObject restored rereadPackage -> do {
            oldSchema <- readByteArray (Open.packageBytes package) 16;
            newSchema <- readByteArray (Open.packageBytes rereadPackage) 16;
            require "retained audit rebuild uses schema 8"
              ((oldSchema == 7 || oldSchema == 8) && newSchema == 8);
            require "retained checked rebuild preserves complete open semantics"
              (sameOpenMeaning original package restored rereadPackage);
            if oldSchema == 8 then do {
              exactObject <- Storage.sameBytes
                (Open.packageBytes package) (Open.packageBytes rereadPackage);
              originalMetadata <- Storage.readRaw (input ++ ".mlfci") >>= right;
              auditedMetadata <- Storage.readRaw (output ++ "-audited.mlfci") >>= right;
              exactMetadata <- Storage.sameBytes originalMetadata auditedMetadata;
              require "schema 8 retained audit rebuild exact pair bytes"
                (exactObject && exactMetadata)
            } else return ()
          };
          _ -> panic "retained audit rebuild changed open family"
        }
      };
      _ -> return ()
    };
    putStrLn "PASS shared-public-binary-pair"
  };
  rejectMain :: String -> String -> Bool -> IO ();
  rejectMain input expected auditing = do {
    iface <- Crate.readInterface (input ++ ".mlfci") >>= right;
    result <- Crate.readObject (input ++ ".mlfco") iface;
    let { observed = case result of {
      Left message -> if auditing then panic "audit negative failed ordinary admission" else Left message;
      Right object -> if auditing then case object of {
        Crate.OpenCrateObject _ package ->
          Std.mapLeft (\message -> input ++ ".mlfco: " ++ message)
            (Std.mapEither (\_ -> ()) (Std.traverseEither
              (\entry -> Open.audit (Std.snd entry)) (Open.packageFragments package)));
        _ -> Left "audit negative requires an open object"
      } else Right ()
    } };
    case observed of {
      Left message -> require "exact open rejection, no fallback"
        (message == input ++ ".mlfco: " ++ expected);
      Right _ -> panic "invalid open object accepted"
    };
    putStrLn "PASS shared-public-reject"
  };
  main :: IO ();
  main = do {
    mode <- getLine;
    if mode == "raw" then rawMain else if mode == "typed" then do {
      root <- getLine; typedMain root
    } else if mode == "formal" then do {
      input <- getLine; output <- getLine; formalMain input output
    } else if mode == "reject" then do {
      input <- getLine; expected <- getLine; rejectMain input expected False
    } else if mode == "audit-reject" then do {
      input <- getLine; expected <- getLine; rejectMain input expected True
    } else panic "unknown shared binary fixture mode"
  }
}
