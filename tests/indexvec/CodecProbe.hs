-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.Std as S;
  load :: String -> IO ByteArray;
  load path = do {
    (message, bytes) <- readByteFileOrError path 268435456;
    if message == "" then ioReturn bytes else panic message
  };
  printInts :: [] Int -> IO ();
  printInts values = case values of {
    [] -> ioReturn ();
    (:) value rest -> do { printInt value; printInts rest }
  };
  nodes :: W.Graph -> Int -> IO ();
  nodes graph index = if index == W.graphNodeCount graph then ioReturn () else do {
    depth <- case W.graphNodeDepth graph index of { Left e -> panic e; Right x -> ioReturn x };
    printInt depth;
    case W.lookupGraphNode graph index of {
      Left e -> panic e;
      Right value -> case value of {
        W.GInt x -> do { printInt 0; printInt x };
        W.GBits x -> do { printInt 1; printInt x };
        W.GText x -> do { printInt 2; putStrLn x };
        W.GNode tag children -> do { printInt 3; printInt tag; printInt (S.length children); printInts children }
      }
    };
    nodes graph (index + 1)
  };
  inspect :: ByteArray -> IO ();
  inspect bytes = do {
    result <- W.decodeGraph W.defaultLimits 7 bytes;
    case result of {
      Left message -> putStrLn ("E " ++ message);
      Right graph -> do {
        putStrLn "OK";
        printInt (W.graphNodeCount graph);
        printInt (S.length (W.graphRoots graph));
        printInts (W.graphRoots graph);
        nodes graph 0;
        case W.graphResourceStats graph of {
          Left message -> panic message;
          Right stats -> printInts [W.resourceBytes stats, W.resourceNodes stats, W.resourceEdges stats,
            W.resourceSymbols stats, W.resourceSymbolBytes stats, W.resourceDepth stats,
            W.resourceMaxSymbolBytes stats, W.resourceExpandedNodes stats,
            W.resourceExpandedTextBytes stats, W.resourceExpandedWork stats]
        };
        decoded <- W.decode W.defaultLimits 7 bytes;
        case decoded of {
          Left message -> panic message;
          Right values -> do {
            encoded <- W.encode W.defaultLimits 7 values;
            case encoded of { Left message -> panic message; Right blob -> byteArrayDigest blob >>= putStrLn }
          }
        }
      }
    }
  };
  files :: Int -> Int -> IO ();
  files index count = if index == count then ioReturn () else do {
    path <- getArg index;
    bytes <- load path;
    inspect bytes;
    files (index + 1) count
  };
  clock :: IO Int;
  clock = do {
    reply <- processSupervisor "MLF-PROCESS-1\0clock\0";
    ioReturn (readInt (stringSlice reply 2 (stringLength reply - 3)))
  };
  measure :: ByteArray -> Int -> Int -> Int -> IO Int;
  measure bytes schema remaining total = if remaining == 0 then ioReturn total else do {
    result <- W.decodeGraph W.defaultLimits schema bytes;
    case result of {
      Left message -> panic message;
      Right graph -> let { next = total + W.graphNodeCount graph + S.length (W.graphRoots graph) } in
        seq next (measure bytes schema (remaining - 1) next)
    }
  };
  checkLimits :: String -> Int -> Int -> IO ();
  checkLimits path depth work = do {
    bytes <- load path;
    let { limits = W.Limits 268435456 1048576 16777216 134217728 4194304 16777216 depth work };
    decoded <- W.decodeGraph limits 7 bytes;
    case decoded of {
      Left message -> putStrLn ("E " ++ message);
      Right graph -> do {
        putStrLn "OK";
        printInt (W.graphNodeCount graph);
        case W.graphRoots graph of {
          (:) root [] -> do {
            printInt root;
            case W.graphNodeDepth graph root of { Left message -> panic message; Right value -> printInt value }
          };
          _ -> panic "expected one root"
        }
      }
    }
  };
  main :: IO ();
  main = do {
    mode <- getArg 0;
    if mode == "bench" || mode == "timed" then do {
      path <- getArg 1; schema <- getArg 2; count <- getArg 3;
      bytes <- load path;
      start <- if mode == "timed" then clock else ioReturn 0;
      total <- measure bytes (readInt schema) (readInt count) 0;
      end <- if mode == "timed" then clock else ioReturn 0;
      printInt total;
      if mode == "timed" then printInt (end - start) else ioReturn ()
    } else if mode == "limits" then do {
      path <- getArg 1; depth <- getArg 2; work <- getArg 3;
      checkLimits path (readInt depth) (readInt work)
    } else do {
      count <- getArgCount;
      files 1 count
    }
  }
}
