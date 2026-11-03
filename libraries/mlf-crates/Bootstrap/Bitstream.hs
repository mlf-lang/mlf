-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Bitstream (
  Value(..), Limits(..), Entry(..), Symbol(..), SymbolState(..), NodeState(..),
  PlanState(..), Tables(..), EncodeTask(..), Layout(..), Cursor(..), Read(..),
  Header(..), Parsed(..), CanonicalTask(..),
  defaultLimits, maxBytes, maxSymbols, maxSymbolBytes, maxTotalSymbolBytes,
  maxNodes, maxEdges, maxDepth, maxExpandedWork, validLimits, magic,
  hasMagicPrefix, hasMagic, matchMagic, entryKind, compareIds, compareEntry,
  charge, boundedLength, boundedLengthAt, scalar, scalarBytes, utf8Size,
  utf8SizeAt, internSymbol, entryEdges, internEntry, takeIds, plan, planTasks,
  zigzag, unzigzag, varBytes, referenceWidth, bytesForBits, symbolSize,
  nodeBits, layout, putBits, putVar, putScalar, putText, putSymbols,
  putReferences, putEntry, putEntries, putWords, putHeader, crcNibble,
  crcByte, checksum, checksumAt, encode, encodeChecked, encodeTables,
  returnRead, bindRead, failRead, checkRead, liftEither, getBits, getBitsAt,
  remainingBits, getVar, getVarAt, getNat, finishSection, runSection,
  getHeader, getContinuation, getUtf8, getUtf8At, strictUtf8,
  strictUtf8Checked, getSymbols, getSymbolsAt, parsedEntry, parsedValue,
  parsedDepth, parsedWork, getChildIds, getEntry, buildChildren, buildParsed,
  getNodes, getNodesAt, getRoots, getRootsAt, canonicalGraph, canonicalTasks,
  collectRoots, decode, decodeChecked, decodeTables,
  Graph, GraphNode(..), decodeGraph, decodeGraphWithText, graphRoots, lookupGraphNode,
  ResourceStats, planMeasured, planGraph, GraphPlan, prepareGraphPlan, realizeGraphPlan, graphNodeDepth, graphResourceStats,
  resourceBytes, resourceNodes, resourceEdges, resourceSymbols,
  resourceSymbolBytes, resourceDepth, resourceMaxSymbolBytes,
  resourceExpandedNodes, resourceExpandedTextBytes, resourceExpandedWork) where {
  import MLF.Primitive;
  import Bootstrap.Types hiding (Graph(..));
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;

  -- The schema above this layer owns constructor tags and field types. VBits
  -- is an arbitrary Int64 bit pattern, not a nonnegative numeric quantity.
  data Value = VInt Int | VBits Int | VText String | VNode Int ([] Value);
  data Limits = Limits Int Int Int Int Int Int Int Int;
  defaultLimits :: Limits;
  defaultLimits = Limits 268435456 1048576 16777216 134217728
    4194304 16777216 16384 67108864;
  maxBytes :: Limits -> Int;
  maxBytes (Limits x _ _ _ _ _ _ _) = x;
  maxSymbols :: Limits -> Int;
  maxSymbols (Limits _ x _ _ _ _ _ _) = x;
  maxSymbolBytes :: Limits -> Int;
  maxSymbolBytes (Limits _ _ x _ _ _ _ _) = x;
  maxTotalSymbolBytes :: Limits -> Int;
  maxTotalSymbolBytes (Limits _ _ _ x _ _ _ _) = x;
  maxNodes :: Limits -> Int;
  maxNodes (Limits _ _ _ _ x _ _ _) = x;
  maxEdges :: Limits -> Int;
  maxEdges (Limits _ _ _ _ _ x _ _) = x;
  maxDepth :: Limits -> Int;
  maxDepth (Limits _ _ _ _ _ _ x _) = x;
  maxExpandedWork :: Limits -> Int;
  maxExpandedWork (Limits _ _ _ _ _ _ _ x) = x;
  validLimits :: Limits -> Bool;
  validLimits (Limits bytes symbols single total nodes edges depth work) =
    bytes >= 80 && bytes <= 2147483647 &&
    symbols >= 0 && symbols <= 2147483647 &&
    single >= 0 && single <= total && total <= bytes &&
    nodes >= 0 && nodes <= 2147483647 &&
    edges >= 0 && edges <= 2147483647 &&
    depth >= 1 && depth <= 65536 && work >= 0 && work <= 2147483647;
  magic :: String;
  magic = "MLFBIN\r\n";
  hasMagicPrefix :: String -> Bool;
  hasMagicPrefix text = stringLength text >= 8 && eqString (stringSlice text 0 8) magic;
  hasMagic :: ByteArray -> IO Bool;
  hasMagic bytes = do {
    size <- lengthByteArray bytes;
    if size < 8 then ioReturn False else matchMagic bytes 0
  };
  matchMagic :: ByteArray -> Int -> IO Bool;
  matchMagic bytes position =
    if position == 8 then ioReturn True else do {
      byte <- readByteArray bytes position;
      if byte == stringCodeAt magic position
      then matchMagic bytes (position + 1) else ioReturn False
    };

  -- Full shallow keys, never hash-only admission. IDs in an ENode are
  -- already interned child IDs, so key equality is structural equality.
  data Entry = EInt Int | EBits Int | EText Int | ENode Int ([] Int);
  data Symbol = Symbol String Int;
  entryKind :: Entry -> Int;
  entryKind entry = case entry of {
    EInt _ -> 0; EBits _ -> 1; EText _ -> 2; ENode _ _ -> 3
  };
  compareIds :: [] Int -> [] Int -> Int;
  compareIds left right = case left of {
    [] -> case right of { [] -> 0; _ -> (-1) };
    (:) a more -> case right of {
      [] -> 1;
      (:) b rest -> let { c = compareInt a b } in
        if c == 0 then compareIds more rest else c
    }
  };
  compareEntry :: Entry -> Entry -> Int;
  compareEntry left right =
    let { kind = compareInt (entryKind left) (entryKind right) } in
    if kind /= 0 then kind else case left of {
      EInt a -> case right of { EInt b -> compareInt a b; _ -> 0 };
      EBits a -> case right of { EBits b -> compareInt a b; _ -> 0 };
      EText a -> case right of { EText b -> compareInt a b; _ -> 0 };
      ENode tag ids -> case right of {
        ENode other rest -> let { c = compareInt tag other } in
          if c == 0 then compareIds ids rest else c;
        _ -> 0
      }
    };
  data SymbolState = Symbols (Map String ((,) Int Int)) ([] Symbol) Int Int;
  data NodeState = Nodes (Map Entry Int) ([] Entry) Int Int;
  data PlanState = PlanState SymbolState NodeState Int;
  data Tables = Tables ([] Symbol) ([] Entry) ([] Int) Int Int Int Int;
  data EncodeTask = EncodeValues Int ([] Value) | EncodeOne Int Value | EncodeClose Int Int;
  charge :: Limits -> Int -> PlanState -> Either String PlanState;
  charge limits amount (PlanState symbols nodes work) =
    if amount < 0 || amount > maxExpandedWork limits - work
    then Left "binary expanded-work limit exceeded"
    else let { next = work + amount } in seq next (Right (PlanState symbols nodes next));
  boundedLength :: forall a. Int -> [] a -> Either String Int;
  boundedLength limit values = boundedLengthAt limit 0 values;
  boundedLengthAt :: forall a. Int -> Int -> [] a -> Either String Int;
  boundedLengthAt limit count values = case values of {
    [] -> Right count;
    (:) _ rest -> if count >= limit then Left "binary list count limit exceeded"
      else let { next = count + 1 } in seq next (boundedLengthAt limit next rest)
  };
  scalar :: Int -> Bool;
  scalar code = code >= 0 && code <= 1114111 && (code < 55296 || code > 57343);
  scalarBytes :: Int -> Int;
  scalarBytes code = if code < 128 then 1 else if code < 2048 then 2
    else if code < 65536 then 3 else 4;
  utf8Size :: Int -> String -> Either String Int;
  utf8Size limit text =
    if stringLength text > limit then Left "binary symbol byte limit exceeded"
    else utf8SizeAt limit text 0 0;
  utf8SizeAt :: Int -> String -> Int -> Int -> Either String Int;
  utf8SizeAt limit text position size =
    if position == stringLength text then Right size else
    let { code = stringCodeAt text position } in
    if not (scalar code) then Left "binary symbol contains a non-scalar code point"
    else let { count = scalarBytes code } in
      if count > limit - size then Left "binary symbol byte limit exceeded"
      else let { next = size + count } in
        seq next (utf8SizeAt limit text (position + 1) next);
  internSymbol :: Limits -> String -> PlanState -> Either String ((,) Int PlanState);
  internSymbol limits text (PlanState (Symbols names symbols count total) nodes work) =
    if stringLength text > maxSymbolBytes limits then Left "binary symbol byte limit exceeded"
    else case M.lookup compareString text names of {
      Just ((,) index bytes) -> do {
        next <- charge limits bytes (PlanState (Symbols names symbols count total) nodes work);
        Right ((,) index next)
      };
      Nothing -> do {
        ensure (count < maxSymbols limits) "binary symbol count limit exceeded";
        size <- utf8Size (maxSymbolBytes limits) text;
        ensure (size <= maxTotalSymbolBytes limits - total) "binary total symbol byte limit exceeded";
        let {
          nextCount = count + 1;
          nextTotal = total + size;
          nextSymbols = Symbols (M.insert compareString text ((,) count size) names)
            ((:) (Symbol text size) symbols) nextCount nextTotal
        };
        next <- seq nextCount (seq nextTotal (charge limits size (PlanState nextSymbols nodes work)));
        Right ((,) count next)
      }
    };
  entryEdges :: Entry -> Int;
  entryEdges entry = case entry of { ENode _ children -> length children; _ -> 0 };
  internEntry :: Limits -> Entry -> PlanState -> Either String ((,) Int PlanState);
  internEntry limits entry (PlanState symbols (Nodes keys entries count edges) work) =
    case M.lookup compareEntry entry keys of {
      Just index -> Right ((,) index (PlanState symbols (Nodes keys entries count edges) work));
      Nothing -> do {
        ensure (count < maxNodes limits) "binary node count limit exceeded";
        let { arity = entryEdges entry };
        ensure (arity <= maxEdges limits - edges) "binary edge count limit exceeded";
        let {
          nextCount = count + 1;
          nextEdges = edges + arity;
          nextNodes = Nodes (M.insert compareEntry entry count keys) ((:) entry entries) nextCount nextEdges
        };
        seq nextCount (seq nextEdges (Right ((,) count (PlanState symbols nextNodes work))))
      }
    };
  takeIds :: Int -> [] Int -> [] Int -> Either String ((,) ([] Int) ([] Int));
  takeIds count stack acc = if count == 0 then Right ((,) acc stack) else case stack of {
    [] -> Left "binary encoder internal reference stack underflow";
    (:) index rest -> takeIds (count - 1) rest ((:) index acc)
  };
  plan :: Limits -> [] Value -> Either String Tables;
  plan limits roots = do {
    ensure (validLimits limits) "invalid binary codec limits";
    rootCount <- boundedLength (min (maxEdges limits) (maxExpandedWork limits)) roots;
    planned <- planTasks limits ((:) (EncodeValues 1 roots) []) []
      (PlanState (Symbols M.empty [] 0 0) (Nodes M.empty [] 0 0) 0);
    case planned of {
      (,) stack (PlanState (Symbols _ symbols symbolCount _) (Nodes _ entries nodeCount edges) _) ->
        Right (Tables (reverse symbols) (reverse entries) (reverse stack)
          symbolCount nodeCount rootCount edges)
    }
  };
  -- Explicit tasks keep valid deep ASTs off the language call stack. Work
  -- is charged on every input occurrence, including repeated subgraphs.
  planTasks :: Limits -> [] EncodeTask -> [] Int -> PlanState -> Either String ((,) ([] Int) PlanState);
  planTasks limits tasks stack state = case tasks of {
    [] -> Right ((,) stack state);
    (:) task rest -> case task of {
      EncodeValues depth values -> case values of {
        [] -> planTasks limits rest stack state;
        (:) value more -> planTasks limits
          ((:) (EncodeOne depth value) ((:) (EncodeValues depth more) rest)) stack state
      };
      EncodeClose tag arity -> do {
        parts <- takeIds arity stack [];
        case parts of {
          (,) children remaining -> do {
            inserted <- internEntry limits (ENode tag children) state;
            case inserted of {
              (,) index next -> planTasks limits rest ((:) index remaining) next
            }
          }
        }
      };
      EncodeOne depth value -> do {
        ensure (depth <= maxDepth limits) "binary graph depth limit exceeded";
        charged <- charge limits 1 state;
        case value of {
          VNode tag children -> do {
            ensure (tag >= 0 && tag <= 2147483647) "binary constructor tag out of range";
            arity <- boundedLength (min (maxEdges limits) (maxExpandedWork limits - 1)) children;
            planTasks limits ((:) (EncodeValues (depth + 1) children)
              ((:) (EncodeClose tag arity) rest)) stack charged
          };
          VText text -> do {
            symbol <- internSymbol limits text charged;
            case symbol of {
              (,) symbolId withSymbol -> do {
                inserted <- internEntry limits (EText symbolId) withSymbol;
                case inserted of { (,) index next -> planTasks limits rest ((:) index stack) next }
              }
            }
          };
          VInt valueInt -> do {
            inserted <- internEntry limits (EInt valueInt) charged;
            case inserted of { (,) index next -> planTasks limits rest ((:) index stack) next }
          };
          VBits bits -> do {
            inserted <- internEntry limits (EBits bits) charged;
            case inserted of { (,) index next -> planTasks limits rest ((:) index stack) next }
          }
        }
      }
    }
  };

  zigzag :: Int -> Int;
  zigzag value = xorInt (shiftLInt value 1) (shiftRInt value 63);
  unzigzag :: Int -> Int;
  unzigzag bits = xorInt (unsignedShiftRInt bits 1) (0 - andInt bits 1);
  varBytes :: Int -> Int;
  varBytes bits = if unsignedLtInt bits 128 then 1 else 1 + varBytes (unsignedShiftRInt bits 7);
  referenceWidth :: Int -> Int;
  referenceWidth count = if count <= 1 then 1 else 64 - countLeadingZerosInt (count - 1);
  bytesForBits :: Int -> Int;
  bytesForBits bits = (bits + 7) / 8;
  symbolSize :: Symbol -> Int;
  symbolSize (Symbol _ size) = varBytes size + size;
  nodeBits :: Int -> Int -> Entry -> Int;
  nodeBits nodeWidth symbolWidth entry = 2 + case entry of {
    EInt value -> 8 * varBytes (zigzag value);
    EBits _ -> 64;
    EText _ -> symbolWidth;
    ENode tag children -> let { count = length children } in
      8 * (varBytes tag + varBytes count) + count * nodeWidth
  };
  -- All measurement intermediates are <= 2^40 under validLimits. The final
  -- allocation is checked against maxBytes before newByteArray is called.
  data Layout = Layout Int Int Int Int Int Int Int Int Int Int Int Int;
  layout :: Limits -> Tables -> Either String Layout;
  layout limits (Tables symbols nodes roots symbolCount nodeCount rootCount edges) =
    let {
      nodeWidth = referenceWidth nodeCount;
      symbolWidth = referenceWidth symbolCount;
      symbolLength = foldlStrict (\total symbol -> total + symbolSize symbol) 0 symbols;
      nodeLength = bytesForBits (foldlStrict (\total entry -> total + nodeBits nodeWidth symbolWidth entry) 0 nodes);
      rootLength = bytesForBits (rootCount * nodeWidth);
      nodeOffset = 80 + symbolLength;
      rootOffset = nodeOffset + nodeLength;
      total = rootOffset + rootLength
    } in
    if total > maxBytes limits then Left "binary file byte limit exceeded"
    else Right (Layout total symbolCount symbolLength nodeCount nodeOffset nodeLength
      edges rootCount rootOffset rootLength nodeWidth symbolWidth);

  -- The writer owns its zero-filled buffer exclusively. Bits are little-endian
  -- within bytes; no intermediate list of output bytes or textual envelope.
  putBits :: ByteArray -> Int -> Int -> Int -> IO Int;
  putBits bytes position width bits =
    if width == 0 then ioReturn position else do {
      let {
        offset = position % 8;
        take = min width (8 - offset);
        mask = shiftLInt 1 take - 1;
        piece = shiftLInt (andInt bits mask) offset;
        byteIndex = position / 8
      };
      if take == 8 then writeByteArray bytes byteIndex piece else do {
        previous <- readByteArray bytes byteIndex;
        writeByteArray bytes byteIndex (orInt previous piece)
      };
      putBits bytes (position + take) (width - take) (unsignedShiftRInt bits take)
    };
  putVar :: ByteArray -> Int -> Int -> IO Int;
  putVar bytes position bits = do {
    let { final = unsignedLtInt bits 128; byte = orInt (andInt bits 127) (if final then 0 else 128) };
    next <- putBits bytes position 8 byte;
    if final then ioReturn next else putVar bytes next (unsignedShiftRInt bits 7)
  };
  putScalar :: ByteArray -> Int -> Int -> IO Int;
  putScalar bytes position code =
    if code < 128 then putBits bytes position 8 code
    else if code < 2048 then do {
      next <- putBits bytes position 8 (orInt 192 (unsignedShiftRInt code 6));
      putBits bytes next 8 (orInt 128 (andInt code 63))
    } else if code < 65536 then do {
      next <- putBits bytes position 8 (orInt 224 (unsignedShiftRInt code 12));
      more <- putBits bytes next 8 (orInt 128 (andInt (unsignedShiftRInt code 6) 63));
      putBits bytes more 8 (orInt 128 (andInt code 63))
    } else do {
      next <- putBits bytes position 8 (orInt 240 (unsignedShiftRInt code 18));
      more <- putBits bytes next 8 (orInt 128 (andInt (unsignedShiftRInt code 12) 63));
      last <- putBits bytes more 8 (orInt 128 (andInt (unsignedShiftRInt code 6) 63));
      putBits bytes last 8 (orInt 128 (andInt code 63))
    };
  putText :: ByteArray -> Int -> String -> Int -> IO Int;
  putText bytes position text index =
    if position >= 0 && position % 8 == 0 then putAlignedText bytes (position / 8) text index
    else if index == stringLength text then ioReturn position else do {
      next <- putScalar bytes position (stringCodeAt text index);
      putText bytes next text (index + 1)
    };
  putAlignedText bytes byteIndex text index =
    if index == stringLength text then ioReturn (byteIndex * 8) else let {
      code = stringCodeAt text index
    } in if code < 128 then do {
      writeByteArray bytes byteIndex code;
      putAlignedText bytes (byteIndex + 1) text (index + 1)
    } else do {
      next <- putScalar bytes (byteIndex * 8) code;
      putAlignedText bytes (next / 8) text (index + 1)
    };
  putSymbols :: ByteArray -> Int -> [] Symbol -> IO Int;
  putSymbols bytes position symbols = case symbols of {
    [] -> ioReturn position;
    (:) (Symbol text size) rest -> do {
      next <- putVar bytes position size;
      more <- putText bytes next text 0;
      putSymbols bytes more rest
    }
  };
  putReferences :: ByteArray -> Int -> Int -> [] Int -> IO Int;
  putReferences bytes position width references = case references of {
    [] -> ioReturn position;
    (:) index rest -> do {
      next <- putBits bytes position width index;
      putReferences bytes next width rest
    }
  };
  putEntry :: ByteArray -> Int -> Int -> Int -> Entry -> IO Int;
  putEntry bytes position nodeWidth symbolWidth entry = do {
    next <- putBits bytes position 2 (entryKind entry);
    case entry of {
      EInt value -> putVar bytes next (zigzag value);
      EBits bits -> putBits bytes next 64 bits;
      EText index -> putBits bytes next symbolWidth index;
      ENode tag children -> do {
        more <- putVar bytes next tag;
        last <- putVar bytes more (length children);
        putReferences bytes last nodeWidth children
      }
    }
  };
  putEntries :: ByteArray -> Int -> Int -> Int -> [] Entry -> IO Int;
  putEntries bytes position nodeWidth symbolWidth entries = case entries of {
    [] -> ioReturn position;
    (:) entry rest -> do {
      next <- putEntry bytes position nodeWidth symbolWidth entry;
      putEntries bytes next nodeWidth symbolWidth rest
    }
  };
  putWords :: ByteArray -> Int -> [] Int -> IO Int;
  putWords bytes position words = case words of {
    [] -> ioReturn position;
    (:) word rest -> do {
      next <- putBits bytes position 32 word;
      putWords bytes next rest
    }
  };
  putHeader :: ByteArray -> Int -> Layout -> IO Int;
  putHeader bytes schema (Layout total symbols symbolLength nodes nodeOffset nodeLength
      edges roots rootOffset rootLength nodeWidth symbolWidth) = do {
    next <- putText bytes 0 magic 0;
    putWords bytes next ((:) 1 ((:) 0 ((:) schema ((:) 80 ((:) total
      ((:) symbols ((:) 80 ((:) symbolLength ((:) nodes ((:) nodeOffset ((:) nodeLength
      ((:) edges ((:) roots ((:) rootOffset ((:) rootLength ((:) nodeWidth
      ((:) symbolWidth ((:) 0 []))))))))))))))))))
  };

  -- CRC32/ISO-HDLC. This detects corruption only; it is not a signature,
  -- MAC or content-addressing substitute. Header checksum bytes 76..79 are
  -- treated as zero, binding every other header byte and every payload byte.
  crcNibble :: Int -> Int;
  crcNibble value = case andInt value 15 of {
    0 -> 0; 1 -> 498536548; 2 -> 997073096; 3 -> 651767980;
    4 -> 1994146192; 5 -> 1802195444; 6 -> 1303535960; 7 -> 1342533948;
    8 -> 3988292384; 9 -> 4027552580; 10 -> 3604390888; 11 -> 3412177804;
    12 -> 2607071920; 13 -> 2262029012; 14 -> 2685067896; _ -> 3183342108
  };
  crcByte :: Int -> Int -> Int;
  crcByte previous byte =
    let { start = xorInt previous byte;
          first = xorInt (unsignedShiftRInt start 4) (crcNibble start) } in
    xorInt (unsignedShiftRInt first 4) (crcNibble first);
  checksum :: ByteArray -> Int -> IO Int;
  checksum bytes size = if size < 1024 then checksumAt bytes size 0 4294967295 else do {
    table <- newIntArray 256 0;
    buildCRCTable table 0;
    checksumBytes table bytes size 0 4294967295
  };
  -- CRC is linear over XOR. The one-byte remainder is crcByte 0 index,
  -- while every higher input bit shifts down by eight positions.
  buildCRCTable table index = if index == 256 then ioReturn () else do {
    writeIntArray table index (crcByte 0 index);
    buildCRCTable table (index + 1)
  };
  checksumBytes table bytes size position crc =
    if position == size then ioReturn (xorInt crc 4294967295) else do {
      byte <- if position >= 76 && position < 80 then ioReturn 0 else readByteArray bytes position;
      remainder <- readIntArray table (andInt (xorInt crc byte) 255);
      let { next = xorInt (unsignedShiftRInt crc 8) remainder };
      seq next (checksumBytes table bytes size (position + 1) next)
    };
  checksumAt :: ByteArray -> Int -> Int -> Int -> IO Int;
  checksumAt bytes size position crc =
    if position == size then ioReturn (xorInt crc 4294967295) else do {
      byte <- if position >= 76 && position < 80 then ioReturn 0 else readByteArray bytes position;
      let { next = crcByte crc byte };
      seq next (checksumAt bytes size (position + 1) next)
    };
  encode :: Limits -> Int -> [] Value -> IO (Either String ByteArray);
  encode limits schema roots = catchIOError (encodeChecked limits schema roots)
    (\error -> ioReturn (Left ("binary encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  encodeChecked :: Limits -> Int -> [] Value -> IO (Either String ByteArray);
  encodeChecked limits schema roots =
    if schema < 0 || schema > 2147483647 then ioReturn (Left "binary schema ID out of range")
    else case plan limits roots of {
      Left message -> ioReturn (Left message);
      Right tables -> case layout limits tables of {
        Left message -> ioReturn (Left message);
        Right geometry -> encodeTables schema geometry tables
      }
    };
  encodeTables :: Int -> Layout -> Tables -> IO (Either String ByteArray);
  encodeTables schema geometry tables = case geometry of {
    Layout total _ _ _ nodeOffset _ _ _ rootOffset _ nodeWidth symbolWidth ->
      case tables of {
        Tables symbols entries roots _ _ _ _ -> do {
          bytes <- newByteArray total 0;
          headerEnd <- putHeader bytes schema geometry;
          symbolEnd <- putSymbols bytes 640 symbols;
          nodeEnd <- putEntries bytes (nodeOffset * 8) nodeWidth symbolWidth entries;
          rootEnd <- putReferences bytes (rootOffset * 8) nodeWidth roots;
          if headerEnd /= 640 || symbolEnd /= nodeOffset * 8 ||
             bytesForBits nodeEnd /= rootOffset || bytesForBits rootEnd /= total
          then ioReturn (Left "binary encoder internal measured-size mismatch") else do {
            crc <- checksum bytes total;
            end <- putBits bytes 608 32 crc;
            ioReturn (Right bytes)
          }
        }
      }
  };

  data Cursor = Cursor ByteArray Int Int;
  data Read a = Read (Cursor -> IO (Either String ((,) a Cursor)));
  returnRead :: forall a. a -> Read a;
  returnRead value = Read (\cursor -> ioReturn (Right ((,) value cursor)));
  bindRead :: forall a b. Read a -> (a -> Read b) -> Read b;
  bindRead (Read action) next = Read (\cursor -> do {
    result <- action cursor;
    case result of {
      Left message -> ioReturn (Left message);
      Right ((,) value more) -> case next value of { Read following -> following more }
    }
  });
  instance Functor Read where {
    fmap function action = bindRead action (\value -> returnRead (function value))
  };
  instance Applicative Read where {
    pure = returnRead;
    (<*>) action argument = bindRead action (\function ->
      bindRead argument (\value -> returnRead (function value)))
  };
  instance Monad Read where { (>>=) = bindRead };
  failRead :: forall a. String -> Read a;
  failRead message = Read (\_ -> ioReturn (Left message));
  checkRead :: Bool -> String -> Read ();
  checkRead condition message = if condition then returnRead () else failRead message;
  liftEither :: forall a. Either String a -> Read a;
  liftEither result = case result of { Left message -> failRead message; Right value -> returnRead value };
  getBits :: Int -> Read Int;
  getBits width = Read (\cursor -> case cursor of {
    Cursor bytes position end ->
      if width < 0 || width > 64 || width > end - position
      then ioReturn (Left "truncated binary bitstream")
      else getBitsAt bytes position end width 0 0
  });
  getBitsAt :: ByteArray -> Int -> Int -> Int -> Int -> Int -> IO (Either String ((,) Int Cursor));
  getBitsAt bytes position end remaining consumed result =
    if remaining == 0 then ioReturn (Right ((,) result (Cursor bytes position end))) else do {
      let { offset = position % 8; take = min remaining (8 - offset); mask = shiftLInt 1 take - 1 };
      byte <- readByteArray bytes (position / 8);
      let { piece = andInt (unsignedShiftRInt byte offset) mask;
            next = orInt result (shiftLInt piece consumed) };
      seq next (getBitsAt bytes (position + take) end (remaining - take) (consumed + take) next)
    };
  remainingBits :: Read Int;
  remainingBits = Read (\cursor -> case cursor of {
    Cursor _ position end -> ioReturn (Right ((,) (end - position) cursor))
  });
  getVar :: Read Int;
  getVar = getVarAt 0 0;
  getVarAt :: Int -> Int -> Read Int;
  getVarAt index result = do {
    byte <- getBits 8;
    let { payload = andInt byte 127; continuing = andInt byte 128 /= 0 };
    checkRead (index < 9 || (not continuing && payload <= 1)) "binary varint overflows 64 bits";
    checkRead (continuing || index == 0 || payload /= 0) "noncanonical binary varint";
    let { next = orInt result (shiftLInt payload (index * 7)) };
    if continuing then seq next (getVarAt (index + 1) next) else returnRead next
  };
  getNat :: Int -> Read Int;
  getNat bound = do {
    value <- getVar;
    checkRead (value >= 0 && value <= bound) "binary unsigned quantity exceeds its limit";
    returnRead value
  };
  finishSection :: Read ();
  finishSection = do {
    remaining <- remainingBits;
    checkRead (remaining < 8) "binary section length/count mismatch";
    padding <- getBits remaining;
    checkRead (padding == 0) "nonzero binary section padding"
  };
  runSection :: forall a. ByteArray -> Int -> Int -> Read a -> IO (Either String a);
  runSection bytes offset size action = case bindRead action (\value -> do {
    finishSection; returnRead value
  }) of {
    Read parse -> do {
      result <- parse (Cursor bytes (offset * 8) ((offset + size) * 8));
      ioReturn (mapEither fst result)
    }
  };
  data Header = Header Layout Int;
  getHeader :: Limits -> Int -> Int -> Read Header;
  getHeader limits schema actualSize = do {
    version <- getBits 32;
    flags <- getBits 32;
    storedSchema <- getBits 32;
    headerSize <- getBits 32;
    total <- getBits 32;
    symbols <- getBits 32;
    symbolOffset <- getBits 32;
    symbolLength <- getBits 32;
    nodes <- getBits 32;
    nodeOffset <- getBits 32;
    nodeLength <- getBits 32;
    edges <- getBits 32;
    roots <- getBits 32;
    rootOffset <- getBits 32;
    rootLength <- getBits 32;
    nodeWidth <- getBits 32;
    symbolWidth <- getBits 32;
    crc <- getBits 32;
    checkRead (version == 1) "unsupported binary format version";
    checkRead (flags == 0) "unknown binary mandatory flags";
    checkRead (storedSchema == schema) "binary artifact schema mismatch";
    checkRead (headerSize == 80 && total == actualSize) "binary file/header length mismatch";
    checkRead (symbols <= maxSymbols limits && nodes <= maxNodes limits &&
      edges <= maxEdges limits && roots <= maxEdges limits) "binary table count limit exceeded";
    checkRead (symbolOffset == 80 && nodeOffset == 80 + symbolLength &&
      rootOffset == nodeOffset + nodeLength && total == rootOffset + rootLength)
      "binary sections overlap, have gaps, or contain trailing bytes";
    checkRead (symbols <= symbolLength && bytesForBits (nodes * 2) <= nodeLength)
      "binary section count exceeds its byte length";
    checkRead (nodeWidth == referenceWidth nodes && symbolWidth == referenceWidth symbols)
      "noncanonical binary reference width";
    checkRead (rootLength == bytesForBits (roots * nodeWidth)) "binary root section length mismatch";
    returnRead (Header (Layout total symbols symbolLength nodes nodeOffset nodeLength
      edges roots rootOffset rootLength nodeWidth symbolWidth) crc)
  };

  -- UTF-8 is decoded without a permissive host replacement-character path.
  -- Reject overlong encodings, isolated continuations, surrogates and >U+10FFFF.
  getContinuation :: Int -> Int -> Read Int;
  getContinuation remaining code = if remaining == 0 then returnRead code else do {
    byte <- getBits 8;
    checkRead (byte >= 128 && byte <= 191) "invalid binary UTF-8 continuation";
    getContinuation (remaining - 1) (orInt (shiftLInt code 6) (andInt byte 63))
  };
  getUtf8 :: Int -> Read String;
  getUtf8 size = getUtf8At size [];
  getUtf8With hints size = Read (\cursor -> case cursor of { Cursor bytes position end ->
    let { ordinary = \ignored -> case getUtf8At size [] of { Read parse -> parse cursor } } in
    if position < 0 || position % 8 /= 0 || size < 0 || size > (end - position) / 8
    then ordinary () else do {
      let { start = position / 8 };
      text <- case find (\hint -> stringLength hint == size) hints of {
        Just hint -> do {
          matches <- sameAscii bytes start hint size 0;
          if matches then ioReturn (Just hint) else alignedAscii bytes start (start + size) []
        };
        Nothing -> alignedAscii bytes start (start + size) []
      };
      case text of {
        Nothing -> ordinary ();
        Just value -> ioReturn (Right ((,) value (Cursor bytes (position + size * 8) end)))
      }
    }
  });
  -- A hint only supplies storage. Every byte must equal a canonical ASCII
  -- scalar from that text; a mismatch takes the independent ordinary path.
  sameAscii bytes start hint size index = if index == size then ioReturn True else do {
    byte <- readByteArray bytes (start + index);
    if byte < 128 && byte == stringCodeAt hint index then sameAscii bytes start hint size (index + 1)
    else ioReturn False
  };
  -- Scan in wire order. A malformed prefix cannot allocate a list for an
  -- unread suffix. Non-ASCII falls back to the strict scalar decoder.
  alignedAscii bytes index end chars =
    if index == end then ioReturn (Just (textFromChars (reverse chars))) else do {
      code <- readByteArray bytes index;
      if code < 128 then alignedAscii bytes (index + 1) end ((:) (charFromCode code) chars)
      else ioReturn Nothing
    };
  getUtf8At :: Int -> [] Char -> Read String;
  getUtf8At remaining chars =
    if remaining == 0 then returnRead (textFromChars (reverse chars)) else do {
      first <- getBits 8;
      if first < 128 then getUtf8At (remaining - 1) ((:) (charFromCode first) chars)
      else if first >= 194 && first <= 223 then do {
        checkRead (remaining >= 2) "truncated binary UTF-8 scalar";
        code <- getContinuation 1 (andInt first 31);
        getUtf8At (remaining - 2) ((:) (charFromCode code) chars)
      } else if first >= 224 && first <= 239 then do {
        checkRead (remaining >= 3) "truncated binary UTF-8 scalar";
        code <- getContinuation 2 (andInt first 15);
        checkRead (code >= 2048 && scalar code) "noncanonical binary UTF-8 scalar";
        getUtf8At (remaining - 3) ((:) (charFromCode code) chars)
      } else if first >= 240 && first <= 244 then do {
        checkRead (remaining >= 4) "truncated binary UTF-8 scalar";
        code <- getContinuation 3 (andInt first 7);
        checkRead (code >= 65536 && scalar code) "noncanonical binary UTF-8 scalar";
        getUtf8At (remaining - 4) ((:) (charFromCode code) chars)
      } else failRead "invalid binary UTF-8 leading byte"
    };
  -- Legacy dispatch may need a strict UTF-8 bridge after raw bounded IO.
  -- The storage layer must check hasMagic FIRST: a recognized new-format
  -- file that fails decode must never be retried as legacy textual input.
  strictUtf8 :: Int -> ByteArray -> IO (Either String String);
  strictUtf8 limit bytes = catchIOError (strictUtf8Checked limit bytes)
    (\error -> ioReturn (Left ("binary UTF-8 IO failure: " ++ textFromChars (ioeGetErrorString error))));
  strictUtf8Checked :: Int -> ByteArray -> IO (Either String String);
  strictUtf8Checked limit bytes =
    if limit < 0 || limit > 2147483647 then ioReturn (Left "invalid UTF-8 byte limit") else do {
      size <- lengthByteArray bytes;
      if size > limit then ioReturn (Left "UTF-8 file byte limit exceeded")
      else runSection bytes 0 size (getUtf8 size)
    };
  getSymbols :: Limits -> Int -> Read (IntMap Symbol);
  getSymbols limits count = getSymbolsAt limits count 0 0 M.empty IM.empty;
  getSymbolsAt :: Limits -> Int -> Int -> Int -> Map String Int -> IntMap Symbol -> Read (IntMap Symbol);
  getSymbolsAt = getSymbolsWith [];
  getSymbolsWith hints limits count index total names symbols =
    if index == count then returnRead symbols else do {
      size <- getNat (maxSymbolBytes limits);
      remaining <- remainingBits;
      checkRead (size <= remaining / 8) "truncated binary symbol";
      checkRead (size <= maxTotalSymbolBytes limits - total) "binary total symbol byte limit exceeded";
      text <- getUtf8With hints size;
      checkRead (not (M.member compareString text names)) "duplicate binary symbol";
      let { nextTotal = total + size;
            nextNames = M.insert compareString text index names;
            nextSymbols = IM.insert index (Symbol text size) symbols };
      seq nextTotal (seq nextNames (seq nextSymbols
        (getSymbolsWith hints limits count (index + 1) nextTotal nextNames nextSymbols)))
    };

  -- Resource summaries are separate from codec limits. In particular these
  -- helpers do not change defaultLimits or the legacy expanded-work policy.
  -- N counts every expanded node occurrence; T counts UTF-8 text bytes at
  -- every occurrence. The validated legacy work measure is exactly N + T.
  data ResourceStats = ResourceStats Int Int Int Int Int Int Int Int Int Int;
  resourceBytes :: ResourceStats -> Int;
  resourceBytes (ResourceStats x _ _ _ _ _ _ _ _ _) = x;
  resourceNodes :: ResourceStats -> Int;
  resourceNodes (ResourceStats _ x _ _ _ _ _ _ _ _) = x;
  resourceEdges :: ResourceStats -> Int;
  resourceEdges (ResourceStats _ _ x _ _ _ _ _ _ _) = x;
  resourceSymbols :: ResourceStats -> Int;
  resourceSymbols (ResourceStats _ _ _ x _ _ _ _ _ _) = x;
  resourceSymbolBytes :: ResourceStats -> Int;
  resourceSymbolBytes (ResourceStats _ _ _ _ x _ _ _ _ _) = x;
  resourceDepth :: ResourceStats -> Int;
  resourceDepth (ResourceStats _ _ _ _ _ x _ _ _ _) = x;
  resourceMaxSymbolBytes :: ResourceStats -> Int;
  resourceMaxSymbolBytes (ResourceStats _ _ _ _ _ _ x _ _ _) = x;
  resourceExpandedNodes :: ResourceStats -> Int;
  resourceExpandedNodes (ResourceStats _ _ _ _ _ _ _ x _ _) = x;
  resourceExpandedTextBytes :: ResourceStats -> Int;
  resourceExpandedTextBytes (ResourceStats _ _ _ _ _ _ _ _ x _) = x;
  resourceExpandedWork :: ResourceStats -> Int;
  resourceExpandedWork (ResourceStats _ _ _ _ _ _ _ _ _ x) = x;

  -- Int is the same signed Int64 on both hosts. Check before arithmetic,
  -- including layout bit totals, rather than relying on host Integer or a
  -- particular default limit. A Graph accepted under ANY validLimits is
  -- supported: counts/work <= 2^31-1, depth <= 65536, layout bits < 2^40.
  measuredAdd :: Int -> Int -> Either String Int;
  measuredAdd left right =
    if left < 0 || right < 0 || right > 9223372036854775807 - left
    then Left "binary resource addition overflow"
    else let { result = left + right } in seq result (Right result);
  measuredMultiply :: Int -> Int -> Either String Int;
  measuredMultiply left right =
    if left < 0 || right < 0 then Left "binary resource multiplication overflow"
    else if left == 0 || right == 0 then Right 0
    else if left > 9223372036854775807 / right
      then Left "binary resource multiplication overflow"
      else let { result = left * right } in seq result (Right result);
  measuredBytesForBits :: Int -> Either String Int;
  measuredBytesForBits bits = do {
    padded <- measuredAdd bits 7;
    Right (padded / 8)
  };

  -- These two entry points own the original planner and layout. No public
  -- Tables value is admitted as a Graph: the only table-to-graph helper is
  -- private, and it rechecks the complete structural/canonical contract.
  planMeasured :: Limits -> [] Value -> Either String ((,) Tables ResourceStats);
  planMeasured limits roots = do {
    tables <- plan limits roots;
    geometry <- layout limits tables;
    graph <- graphFromPlan limits tables;
    stats <- graphResourceStats graph;
    case geometry of {
      Layout total _ _ _ _ _ _ _ _ _ _ _ -> do {
        ensure (resourceBytes stats == total) "binary resource layout mismatch";
        Right ((,) tables stats)
      }
    }
  };
  planGraph :: Limits -> [] Value -> Either String Graph;
  planGraph limits roots = bindEither (prepareGraphPlan limits roots) realizeGraphPlan;
  -- The constructor stays private. Only a successful plan and layout can
  -- supply the exact tables subsequently used for canonical graph admission.
  data GraphPlan = GraphPlan Limits Tables;
  prepareGraphPlan :: Limits -> [] Value -> Either String GraphPlan;
  prepareGraphPlan limits roots = do {
    tables <- plan limits roots;
    geometry <- layout limits tables;
    seq geometry (Right (GraphPlan limits tables))
  };
  realizeGraphPlan :: GraphPlan -> Either String Graph;
  realizeGraphPlan (GraphPlan limits tables) = graphFromPlan limits tables;
  graphNodeDepth :: Graph -> Int -> Either String Int;
  graphNodeDepth (Graph nodes _) index = case IM.lookup index nodes of {
    Nothing -> Left "binary graph node index out of range";
    Just parsed -> Right (parsedDepth parsed)
  };
  graphFromPlan :: Limits -> Tables -> Either String Graph;
  graphFromPlan limits (Tables symbolList entries roots symbolCount nodeCount rootCount edges) = do {
    ensure (validLimits limits) "invalid binary codec limits";
    ensure (symbolCount >= 0 && symbolCount <= maxSymbols limits &&
      nodeCount >= 0 && nodeCount <= maxNodes limits &&
      rootCount >= 0 && rootCount <= maxEdges limits &&
      edges >= 0 && edges <= maxEdges limits) "binary table count limit exceeded";
    symbols <- graphPlanSymbols limits symbolCount symbolList 0 0 M.empty IM.empty;
    nodes <- graphPlanNodes limits symbols symbolCount nodeCount entries 0 0 edges M.empty IM.empty;
    graphPlanRoots limits nodes rootCount roots 0 0;
    canonicalGraph nodes nodeCount roots;
    Right (Graph nodes roots)
  };
  graphPlanSymbols :: Limits -> Int -> [] Symbol -> Int -> Int -> Map String Int -> IntMap Symbol -> Either String (IntMap Symbol);
  graphPlanSymbols limits count remaining index total names symbols = case remaining of {
    [] -> do {
      ensure (index == count) "binary symbol count mismatch";
      Right symbols
    };
    (:) (Symbol text storedSize) rest -> do {
      ensure (index < count) "binary symbol count mismatch";
      size <- utf8Size (maxSymbolBytes limits) text;
      ensure (size == storedSize) "binary symbol byte count mismatch";
      ensure (size <= maxTotalSymbolBytes limits - total) "binary total symbol byte limit exceeded";
      ensure (not (M.member compareString text names)) "duplicate binary symbol";
      nextIndex <- measuredAdd index 1;
      nextTotal <- measuredAdd total size;
      let { nextNames = M.insert compareString text index names;
            nextSymbols = IM.insert index (Symbol text size) symbols };
      seq nextNames (seq nextSymbols
        (graphPlanSymbols limits count rest nextIndex nextTotal nextNames nextSymbols))
    }
  };
  graphPlanChildren :: Int -> [] Int -> Either String ();
  graphPlanChildren parent children = case children of {
    [] -> Right ();
    (:) index rest -> do {
      ensure (index >= 0 && index < parent)
        "binary node has a forward, cyclic, or out-of-range reference";
      graphPlanChildren parent rest
    }
  };
  graphPlanEntryEdges :: Int -> Int -> Entry -> Either String Int;
  graphPlanEntryEdges parent remainingEdges entry = case entry of {
    EInt _ -> Right 0;
    EBits _ -> Right 0;
    EText _ -> Right 0;
    ENode tag children -> do {
      ensure (tag >= 0 && tag <= 2147483647) "binary constructor tag out of range";
      arity <- boundedLength remainingEdges children;
      graphPlanChildren parent children;
      Right arity
    }
  };
  graphPlanNodes :: Limits -> IntMap Symbol -> Int -> Int -> [] Entry -> Int -> Int -> Int -> Map Entry Int -> IntMap Parsed -> Either String (IntMap Parsed);
  graphPlanNodes limits symbols symbolCount count entries index nextSymbol remainingEdges keys nodes = case entries of {
    [] -> do {
      ensure (index == count) "binary node count mismatch";
      ensure (remainingEdges == 0) "binary edge count mismatch";
      ensure (nextSymbol == symbolCount) "unused binary symbol table entries";
      Right nodes
    };
    (:) entry rest -> do {
      ensure (index < count) "binary node count mismatch";
      arity <- graphPlanEntryEdges index remainingEdges entry;
      ensure (not (M.member compareEntry entry keys)) "duplicate binary structural node";
      followingSymbol <- case entry of {
        EText symbol -> do {
          ensure (symbol == nextSymbol) "noncanonical binary symbol first-use order";
          measuredAdd nextSymbol 1
        };
        EInt _ -> Right nextSymbol;
        EBits _ -> Right nextSymbol;
        ENode _ _ -> Right nextSymbol
      };
      parsed <- buildParsed limits symbols nodes entry;
      nextIndex <- measuredAdd index 1;
      let { nextKeys = M.insert compareEntry entry index keys;
            nextNodes = IM.insert index parsed nodes;
            nextEdges = remainingEdges - arity };
      seq nextKeys (seq nextNodes (seq nextEdges
        (graphPlanNodes limits symbols symbolCount count rest nextIndex
          followingSymbol nextEdges nextKeys nextNodes)))
    }
  };
  graphPlanRoots :: Limits -> IntMap Parsed -> Int -> [] Int -> Int -> Int -> Either String ();
  graphPlanRoots limits nodes count roots index work = case roots of {
    [] -> ensure (index == count) "binary root count mismatch";
    (:) root rest -> do {
      ensure (index < count) "binary root count mismatch";
      case IM.lookup root nodes of {
        Nothing -> Left "binary root reference out of range";
        Just parsed -> do {
          ensure (parsedWork parsed <= maxExpandedWork limits - work)
            "binary expanded root-work limit exceeded";
          nextIndex <- measuredAdd index 1;
          nextWork <- measuredAdd work (parsedWork parsed);
          graphPlanRoots limits nodes count rest nextIndex nextWork
        }
      }
    }
  };

  -- One memo entry per physical node; each edge occurrence adds that child's
  -- memo once. The Value field is inspected only for a physical text leaf,
  -- never recursively. Repeated roots are counted just like repeated edges.
  data NodeResources = NodeResources Int Int;
  -- Expanded N/T; physical edges/symbols/text bytes/symbol-section bytes;
  -- node bits excluding text-reference payloads (whose width is known later).
  data NodeMeasurement = NodeMeasurement Int Int Int Int Int Int Int;
  -- Memo; physical edges/symbols/text bytes/largest text/symbol-section bytes;
  -- node bits excluding text-reference payloads; maximum validated depth.
  data ResourceState = ResourceState (IntMap NodeResources) Int Int Int Int Int Int Int;
  measureReferences :: IntMap NodeResources -> [] Int -> Int -> Int -> Int -> Either String ((,,) Int Int Int);
  measureReferences memo references nodes text count = case references of {
    [] -> Right ((,,) nodes text count);
    (:) index rest -> case IM.lookup index memo of {
      Nothing -> Left "binary resource reference has no preceding node";
      Just (NodeResources childNodes childText) -> do {
        nextNodes <- measuredAdd nodes childNodes;
        nextText <- measuredAdd text childText;
        nextCount <- measuredAdd count 1;
        measureReferences memo rest nextNodes nextText nextCount
      }
    }
  };
  measureParsed :: Int -> IntMap NodeResources -> Parsed -> Either String NodeMeasurement;
  measureParsed nodeWidth memo (Parsed entry value _ _) = case entry of {
    EInt integer -> do {
      payload <- measuredMultiply 8 (varBytes (zigzag integer));
      bits <- measuredAdd 2 payload;
      Right (NodeMeasurement 1 0 0 0 0 0 bits)
    };
    EBits _ -> Right (NodeMeasurement 1 0 0 0 0 0 66);
    EText _ -> case value of {
      VText text -> do {
        size <- utf8Size 2147483647 text;
        symbolLength <- measuredAdd (varBytes size) size;
        Right (NodeMeasurement 1 size 0 1 size symbolLength 2)
      };
      VInt _ -> Left "binary graph internal text-node invariant failure";
      VBits _ -> Left "binary graph internal text-node invariant failure";
      VNode _ _ -> Left "binary graph internal text-node invariant failure"
    };
    ENode tag children -> do {
      totals <- measureReferences memo children 1 0 0;
      case totals of {
        (,,) nodes text arity -> do {
          prefixBytes <- measuredAdd (varBytes tag) (varBytes arity);
          prefixBits <- measuredMultiply 8 prefixBytes;
          childBits <- measuredMultiply arity nodeWidth;
          payload <- measuredAdd prefixBits childBits;
          bits <- measuredAdd 2 payload;
          Right (NodeMeasurement nodes text arity 0 0 0 bits)
        }
      }
    }
  };
  measureGraphNodes :: IntMap Parsed -> Int -> Int -> Int -> ResourceState -> Either String ResourceState;
  measureGraphNodes nodes count nodeWidth index state =
    if index == count then Right state else case state of {
      ResourceState memo edges symbols symbolBytes largest symbolLength nodeBits depth ->
        case IM.lookup index nodes of {
          Nothing -> Left "binary resource graph node index gap";
          Just parsed -> do {
            measurement <- measureParsed nodeWidth memo parsed;
            case measurement of {
              NodeMeasurement expandedNodes expandedText arity texts bytes wireBytes bits -> do {
                work <- measuredAdd expandedNodes expandedText;
                ensure (work == parsedWork parsed) "binary resource expanded-work mismatch";
                nextEdges <- measuredAdd edges arity;
                nextSymbols <- measuredAdd symbols texts;
                nextSymbolBytes <- measuredAdd symbolBytes bytes;
                nextSymbolLength <- measuredAdd symbolLength wireBytes;
                nextNodeBits <- measuredAdd nodeBits bits;
                nextIndex <- measuredAdd index 1;
                let { nextLargest = max largest bytes;
                      nextDepth = max depth (parsedDepth parsed);
                      nextMemo = IM.insert index (NodeResources expandedNodes expandedText) memo };
                seq nextLargest (seq nextDepth (seq nextMemo
                  (measureGraphNodes nodes count nodeWidth nextIndex
                    (ResourceState nextMemo nextEdges nextSymbols nextSymbolBytes nextLargest
                      nextSymbolLength nextNodeBits nextDepth))))
              }
            }
          }
        }
    };
  graphResourceStats :: Graph -> Either String ResourceStats;
  graphResourceStats (Graph nodes roots) = do {
    let { count = IM.size nodes; nodeWidth = referenceWidth count };
    measured <- measureGraphNodes nodes count nodeWidth 0
      (ResourceState IM.empty 0 0 0 0 0 0 0);
    case measured of {
      ResourceState memo edges symbols symbolBytes largest symbolLength nodeBits depth -> do {
        rootTotals <- measureReferences memo roots 0 0 0;
        case rootTotals of {
          (,,) expandedNodes expandedText rootCount -> do {
            work <- measuredAdd expandedNodes expandedText;
            textBits <- measuredMultiply symbols (referenceWidth symbols);
            allNodeBits <- measuredAdd nodeBits textBits;
            nodeLength <- measuredBytesForBits allNodeBits;
            rootBits <- measuredMultiply rootCount nodeWidth;
            rootLength <- measuredBytesForBits rootBits;
            nodeOffset <- measuredAdd 80 symbolLength;
            rootOffset <- measuredAdd nodeOffset nodeLength;
            total <- measuredAdd rootOffset rootLength;
            Right (ResourceStats total count edges symbols symbolBytes depth largest
              expandedNodes expandedText work)
          }
        }
      }
    }
  };

  -- Parsed values share their children. Depth/work summaries are computed
  -- once per node and checked before exposing any root to an AST adapter.
  data Parsed = Parsed Entry Value Int Int;
  -- A Graph is validated raw syntax, never checked typing evidence. Its
  -- constructor is deliberately hidden. Typed adapters memoize by their
  -- expected shape and these canonical node IDs, preserving actual sharing
  -- instead of repeatedly reconstructing a shared subtree through Value.
  data Graph = Graph (IntMap Parsed) ([] Int);
  data GraphNode = GInt Int | GBits Int | GText String | GNode Int ([] Int);
  graphRoots :: Graph -> [] Int;
  graphRoots (Graph _ roots) = roots;
  lookupGraphNode :: Graph -> Int -> Either String GraphNode;
  lookupGraphNode (Graph nodes _) index = case IM.lookup index nodes of {
    Nothing -> Left "binary graph node index out of range";
    Just (Parsed entry value _ _) -> case entry of {
      EInt integer -> Right (GInt integer);
      EBits bits -> Right (GBits bits);
      ENode tag children -> Right (GNode tag children);
      EText _ -> case value of {
        VText text -> Right (GText text);
        _ -> Left "binary graph internal text-node invariant failure"
      }
    }
  };
  parsedEntry :: Parsed -> Entry;
  parsedEntry (Parsed entry _ _ _) = entry;
  parsedValue :: Parsed -> Value;
  parsedValue (Parsed _ value _ _) = value;
  parsedDepth :: Parsed -> Int;
  parsedDepth (Parsed _ _ depth _) = depth;
  parsedWork :: Parsed -> Int;
  parsedWork (Parsed _ _ _ work) = work;
  getChildIds :: Int -> Int -> Int -> [] Int -> Read ([] Int);
  getChildIds width parent remaining acc =
    if remaining == 0 then returnRead (reverse acc) else do {
      index <- getBits width;
      checkRead (index < parent) "binary node has a forward, cyclic, or out-of-range reference";
      getChildIds width parent (remaining - 1) ((:) index acc)
    };
  getEntry :: Limits -> Int -> Int -> Int -> Int -> Int -> Read Entry;
  getEntry limits nodeWidth symbolWidth parent symbols remainingEdges = do {
    kind <- getBits 2;
    if kind == 0 then do { bits <- getVar; returnRead (EInt (unzigzag bits)) }
    else if kind == 1 then do { bits <- getBits 64; returnRead (EBits bits) }
    else if kind == 2 then do {
      symbol <- getBits symbolWidth;
      checkRead (symbol < symbols) "binary symbol reference out of range";
      returnRead (EText symbol)
    } else do {
      tag <- getNat 2147483647;
      arity <- getNat remainingEdges;
      remaining <- remainingBits;
      checkRead (arity <= remaining / nodeWidth) "truncated binary child references";
      children <- getChildIds nodeWidth parent arity [];
      returnRead (ENode tag children)
    }
  };
  buildChildren :: Limits -> IntMap Parsed -> [] Int -> [] Value -> Int -> Int -> Either String ((,,) ([] Value) Int Int);
  buildChildren limits nodes children values depth work = case children of {
    [] -> Right ((,,) (reverse values) depth work);
    (:) index rest -> case IM.lookup index nodes of {
      Nothing -> Left "binary child reference has no preceding node";
      Just child -> do {
        ensure (parsedWork child <= maxExpandedWork limits - work) "binary expanded-work limit exceeded";
        let { nextDepth = max depth (parsedDepth child + 1); nextWork = work + parsedWork child };
        ensure (nextDepth <= maxDepth limits) "binary graph depth limit exceeded";
        seq nextDepth (seq nextWork (buildChildren limits nodes rest
          ((:) (parsedValue child) values) nextDepth nextWork))
      }
    }
  };
  buildParsed :: Limits -> IntMap Symbol -> IntMap Parsed -> Entry -> Either String Parsed;
  buildParsed limits symbols nodes entry = case entry of {
    EInt value -> if maxExpandedWork limits < 1 then Left "binary expanded-work limit exceeded"
      else Right (Parsed entry (VInt value) 1 1);
    EBits bits -> if maxExpandedWork limits < 1 then Left "binary expanded-work limit exceeded"
      else Right (Parsed entry (VBits bits) 1 1);
    EText index -> case IM.lookup index symbols of {
      Nothing -> Left "binary symbol reference has no symbol";
      Just (Symbol text size) -> if size >= maxExpandedWork limits
        then Left "binary expanded-work limit exceeded"
        else Right (Parsed entry (VText text) 1 (1 + size))
    };
    ENode tag children -> do {
      ensure (maxExpandedWork limits >= 1) "binary expanded-work limit exceeded";
      built <- buildChildren limits nodes children [] 1 1;
      case built of { (,,) values depth work -> Right (Parsed entry (VNode tag values) depth work) }
    }
  };
  getNodes :: Limits -> Layout -> IntMap Symbol -> Read (IntMap Parsed);
  getNodes limits (Layout _ symbolCount _ count _ _ edges _ _ _ nodeWidth symbolWidth) symbols =
    getNodesAt limits symbols symbolCount count nodeWidth symbolWidth 0 0 edges M.empty IM.empty;
  getNodesAt :: Limits -> IntMap Symbol -> Int -> Int -> Int -> Int -> Int -> Int -> Int -> Map Entry Int -> IntMap Parsed -> Read (IntMap Parsed);
  getNodesAt limits symbols symbolCount count nodeWidth symbolWidth index nextSymbol remainingEdges keys nodes =
    if index == count then do {
      checkRead (remainingEdges == 0) "binary edge count mismatch";
      checkRead (nextSymbol == symbolCount) "unused binary symbol table entries";
      returnRead nodes
    } else do {
      entry <- getEntry limits nodeWidth symbolWidth index symbolCount remainingEdges;
      checkRead (not (M.member compareEntry entry keys)) "duplicate binary structural node";
      followingSymbol <- case entry of {
        EText symbol -> do {
          checkRead (symbol == nextSymbol) "noncanonical binary symbol first-use order";
          returnRead (nextSymbol + 1)
        };
        _ -> returnRead nextSymbol
      };
      parsed <- liftEither (buildParsed limits symbols nodes entry);
      let { nextKeys = M.insert compareEntry entry index keys;
            nextNodes = IM.insert index parsed nodes;
            nextEdges = remainingEdges - entryEdges entry };
      seq nextKeys (seq nextNodes (seq nextEdges
        (getNodesAt limits symbols symbolCount count nodeWidth symbolWidth (index + 1)
          followingSymbol nextEdges nextKeys nextNodes)))
    };
  getRoots :: Limits -> IntMap Parsed -> Int -> Int -> Read ([] Int);
  getRoots limits nodes width count = getRootsAt limits nodes width count 0 [];
  getRootsAt :: Limits -> IntMap Parsed -> Int -> Int -> Int -> [] Int -> Read ([] Int);
  getRootsAt limits nodes width remaining work roots =
    if remaining == 0 then returnRead (reverse roots) else do {
      index <- getBits width;
      case IM.lookup index nodes of {
        Nothing -> failRead "binary root reference out of range";
        Just root -> do {
          checkRead (parsedWork root <= maxExpandedWork limits - work) "binary expanded root-work limit exceeded";
          let { nextWork = work + parsedWork root };
          seq nextWork (getRootsAt limits nodes width (remaining - 1) nextWork ((:) index roots))
        }
      }
    };
  data CanonicalTask = WalkIds ([] Int) | CloseId Int;
  canonicalGraph :: IntMap Parsed -> Int -> [] Int -> Either String ();
  canonicalGraph nodes count roots = canonicalTasks nodes count 0 ((:) (WalkIds roots) []);
  canonicalTasks :: IntMap Parsed -> Int -> Int -> [] CanonicalTask -> Either String ();
  canonicalTasks nodes count next tasks = case tasks of {
    [] -> ensure (next == count) "unused binary node table entries";
    (:) task rest -> case task of {
      CloseId index -> if index /= next then Left "noncanonical binary node postorder"
        else canonicalTasks nodes count (next + 1) rest;
      WalkIds references -> case references of {
        [] -> canonicalTasks nodes count next rest;
        (:) index more -> if index < next
          then canonicalTasks nodes count next ((:) (WalkIds more) rest)
          else case IM.lookup index nodes of {
            Nothing -> Left "binary graph contains an absent node";
            Just parsed -> case parsedEntry parsed of {
              ENode _ children -> canonicalTasks nodes count next
                ((:) (WalkIds children) ((:) (CloseId index) ((:) (WalkIds more) rest)));
              _ -> canonicalTasks nodes count next ((:) (CloseId index) ((:) (WalkIds more) rest))
            }
          }
      }
    }
  };
  collectRoots :: IntMap Parsed -> [] Int -> [] Value -> Either String ([] Value);
  collectRoots nodes roots values = case roots of {
    [] -> Right (reverse values);
    (:) index rest -> case IM.lookup index nodes of {
      Nothing -> Left "binary root has no decoded node";
      Just parsed -> collectRoots nodes rest ((:) (parsedValue parsed) values)
    }
  };
  decode :: Limits -> Int -> ByteArray -> IO (Either String ([] Value));
  decode limits schema bytes = catchIOError (decodeChecked limits schema bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  decodeChecked :: Limits -> Int -> ByteArray -> IO (Either String ([] Value));
  decodeChecked limits schema bytes = do {
    graph <- decodeGraphChecked [] limits schema bytes;
    ioReturn (bindEither graph (\value -> case value of {
      Graph nodes roots -> collectRoots nodes roots []
    }))
  };
  decodeGraph :: Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraph = decodeGraphWithText [];
  decodeGraphWithText :: [] String -> Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraphWithText hints limits schema bytes = catchIOError (decodeGraphChecked hints limits schema bytes)
    (\error -> ioReturn (Left ("binary decode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  decodeGraphChecked :: [] String -> Limits -> Int -> ByteArray -> IO (Either String Graph);
  decodeGraphChecked hints limits schema bytes =
    if not (validLimits limits) then ioReturn (Left "invalid binary codec limits")
    else if schema < 0 || schema > 2147483647 then ioReturn (Left "binary schema ID out of range")
    else do {
      size <- lengthByteArray bytes;
      if size < 80 || size > maxBytes limits then ioReturn (Left "binary file byte limit exceeded or truncated header")
      else do {
        recognized <- hasMagic bytes;
        if not recognized then ioReturn (Left "binary magic mismatch") else do {
          header <- runSection bytes 8 72 (getHeader limits schema size);
          case header of {
            Left message -> ioReturn (Left message);
            Right (Header geometry expectedCRC) -> do {
              actualCRC <- checksum bytes size;
              if actualCRC /= expectedCRC then ioReturn (Left "binary checksum mismatch")
              else decodeGraphTables hints limits bytes geometry
            }
          }
        }
      }
    };
  decodeTables :: Limits -> ByteArray -> Layout -> IO (Either String ([] Value));
  decodeTables limits bytes geometry = do {
    graph <- decodeGraphTables [] limits bytes geometry;
    ioReturn (bindEither graph (\value -> case value of {
      Graph nodes roots -> collectRoots nodes roots []
    }))
  };
  decodeGraphTables :: [] String -> Limits -> ByteArray -> Layout -> IO (Either String Graph);
  decodeGraphTables hints limits bytes geometry = case geometry of {
    Layout _ symbolCount symbolLength nodeCount nodeOffset nodeLength _ rootCount rootOffset rootLength nodeWidth _ -> do {
      symbolResult <- runSection bytes 80 symbolLength (getSymbolsWith (filter (\t -> stringLength t >= 256) (take 9 hints)) limits symbolCount 0 0 M.empty IM.empty);
      case symbolResult of {
        Left message -> ioReturn (Left message);
        Right symbols -> do {
          nodeResult <- runSection bytes nodeOffset nodeLength (getNodes limits geometry symbols);
          case nodeResult of {
            Left message -> ioReturn (Left message);
            Right nodes -> do {
              rootResult <- runSection bytes rootOffset rootLength (getRoots limits nodes nodeWidth rootCount);
              case rootResult of {
                Left message -> ioReturn (Left message);
                Right roots -> ioReturn (do {
                  canonicalGraph nodes nodeCount roots;
                  Right (Graph nodes roots)
                })
              }
            }
          }
        }
      }
    }
  }
}
