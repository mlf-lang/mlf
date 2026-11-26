-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.ReportJournal (begin, append, recover, contents, publish, flush) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  import qualified Package.Json as J;

  -- Each report has a single writer. Keep small worker reports inline. After
  -- eight appends, the inline prefix is frozen. Each sixteen-row block has
  -- two alternating snapshots so an interrupted write preserves its predecessor.
  -- Fresh directories keep stale blocks out of a retry.
  begin name path first = do {
    let { current = path ++ ".journal/current.json" };
    previous <- fileExists current;
    if previous then writeFile current "null\n" else return ();
    backup <- fileExists (path ++ ".previous.jsonl");
    if backup then writeFile (path ++ ".previous.jsonl") "" else return ();
    writeFile path first;
    setEnv (name ++ "_NEXT") "0";
    unsetEnv (name ++ "_PARTS")
  };
  spill name path = do {
    let { directory = path ++ ".journal" };
    O.mkdir directory;
    root <- canonicalPath directory;
    work <- O.temporaryDirectory root (root ++ "/run-");
    prefix <- readFile path;
    writeFile (work ++ "/prefix.jsonl") prefix;
    writeFile (root ++ "/current.json") (J.render (J.str (O.base work)) ++ "\n");
    setEnv (name ++ "_PARTS") work;
    return work
  };
  blockSize :: Int;
  blockSize = 16;
  part work block slot =
    work ++ ("/block-" ++ (showInt block ++ ("-" ++ (showInt slot ++ ".jsonl"))));
  append name path line = do {
    index <- O.envDefault (name ++ "_NEXT") "0";
    let { next = readInt index };
    if next < 8 then do {
      previous <- readFile path;
      writeFile (path ++ ".previous.jsonl") previous;
      writeFile path (previous ++ line)
    } else do {
      work <- if next == 8 then spill name path else getEnv (name ++ "_PARTS");
      O.require (stringLength work > 0) "missing active report journal";
      let { index = next - 8; block = quotInt index blockSize; slot = remInt index 2 };
      previous <- if remInt index blockSize == 0 then return ""
                  else readFile (part work block (1 - slot));
      writeFile (part work block slot) (previous ++ line)
    };
    setEnv (name ++ "_NEXT") (showInt (next + 1))
  };
  -- Recovery is read-only, also in another process. A truncated last part
  -- cannot contribute an observation. The stable locator contains a basename,
  -- so a copied artifact directory works independently of the writer's cwd.
  recover path = do {
    current <- completePart path;
    backup <- completePart (path ++ ".previous.jsonl");
    let { canonical = if stringLength current >= stringLength backup then current else backup };
    let { directory = path ++ ".journal" };
    let { locator = directory ++ "/current.json" };
    exists <- fileExists locator;
    selected <- if exists then do {
      raw <- readFile locator;
      case J.parse raw of {
        Right (J.String value) -> return value;
        _ -> return ""
      }
    } else return "";
    if eqString selected "" then return canonical else do {
      O.require (O.starts "run-" selected && eqString (O.base selected) selected)
        "invalid report journal directory";
      let { work = directory ++ ("/" ++ selected) };
      prefix <- readFile (work ++ "/prefix.jsonl");
      if eqString prefix canonical then do {
        parts <- readParts work 0;
        return (S.concatStrings ((:) prefix parts))
      } else return canonical
    }
  };
  completePart path = do {
    present <- fileExists path;
    if S.not present then return "" else do {
      -- The unfinished snapshot can end in a partial UTF-8 scalar. Inspect
      -- its final byte before decoding the file as text.
      (,) error bytes <- readByteFileOrError path 2147483647;
      O.require (eqString error "") error;
      length <- lengthByteArray bytes;
      if length == 0 then return "" else do {
        last <- readByteArray bytes (length - 1);
        if last == 10 then readFile path else return ""
      }
    }
  };
  readParts work block = do {
    left <- completePart (part work block 0);
    right <- completePart (part work block 1);
    let { best = if stringLength left >= stringLength right then left else right };
    if S.length (O.nonempty (O.lines best)) < blockSize then return ((:) best [])
    else do {
      rest <- readParts work (block + 1);
      return ((:) best rest)
    }
  };
  -- The live writer knows how many appends returned successfully. Require
  -- every such part before publishing a complete or gracefully failed run.
  contents name path = do {
    work <- getEnv (name ++ "_PARTS");
    if eqString work "" then readFile path else do {
      next <- getEnv (name ++ "_NEXT");
      prefix <- readFile (work ++ "/prefix.jsonl");
      let { count = readInt next - 8 };
      parts <- S.mapM (\block -> do {
        let { rows = S.min blockSize (count - block * blockSize) };
        text <- readFile (part work block (remInt (rows - 1) 2));
        O.require (O.ends "\n" text) "truncated report journal block";
        return text
      }) (S.range 0 (quotInt (count + blockSize - 1) blockSize - 1));
      return (S.concatStrings ((:) prefix parts))
    }
  };
  publish name path text = do {
    work <- getEnv (name ++ "_PARTS");
    if eqString work "" then do {
      current <- readFile path;
      writeFile (path ++ ".previous.jsonl") current;
      writeFile path text
    } else do {
      root <- canonicalPath (path ++ ".journal");
      current <- J.read (root ++ "/current.json");
      O.require (eqString (O.parent work) root && O.starts "run-" (O.base work) &&
                 J.equal current (J.str (O.base work))) "report journal generation changed";
      writeFile (work ++ "/publish.jsonl") text;
      O.move (work ++ "/publish.jsonl") path;
      writeFile (path ++ ".journal/current.json") "null\n";
      O.remove work;
      unsetEnv (name ++ "_PARTS")
    }
  };
  flush name = do {
    path <- getEnv name;
    if eqString path "" then return () else do {
      work <- getEnv (name ++ "_PARTS");
      if eqString work "" then return () else do {
        text <- contents name path;
        publish name path text
      }
    }
  }
}
