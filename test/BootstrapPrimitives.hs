module BootstrapPrimitives (bootstrapPrimitiveTests) where

import Control.Exception (bracket)
import Control.Monad (forM_, unless)
import qualified Data.ByteString as BS
import qualified Data.Text as Text
import qualified Data.Text.Encoding as Text
import System.Directory (canonicalizePath, createDirectory, getTemporaryDirectory, removeDirectoryRecursive, removeFile)
import System.FilePath ((</>))
import System.IO (hClose, openTempFile)
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import qualified MLF.X.Parser as XP
import MLF.X.Pretty (prettyTerm)
import qualified MLF.X.Syntax as X

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

checked :: String -> IO X.Term
checked source = do
  term <- compiledTerm <$> right (compile "<bootstrap primitive>" source)
  parsed <- right (XP.parseTerm "<bootstrap primitive target>" (prettyTerm term))
  unless (X.erase term == X.erase parsed) (fail "bootstrap primitive target round trip changed erasure")
  pure parsed

bootstrapPrimitiveTests :: Backends -> [(String,IO ())]
bootstrapPrimitiveTests backends =
  [("bootstrap primitives: " ++ label, do
      term <- checked source
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == expected) (fail (show observed))) | (label,source,expected) <- programs] ++
  [("bootstrap primitive failure: " ++ label, do
      term <- checked ("do { putStrLn \"before\"; " ++ source ++ " }")
      observed <- B.execute backends IOEntry (Input "" False) term
      case B.outcome observed of
        Left err | show err == expected && B.output observed == "before\n" -> pure ()
        _ -> fail (show observed)) | (label,source,expected) <- failures] ++
  [ ("bootstrap primitives: Unicode scalar boundaries", do
      let codes = [0,127,128,2047,2048,55295,57344,65535,65536,1114111]
      term <- checked ("do { " ++ concat ["printInt (stringCodeAt (stringFromCode " ++ show (c::Int) ++ ") 0); " | c <- codes] ++ "return () }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == unlines (map show codes)) (fail (show observed)))
  , ("bootstrap primitives: strict decimal input", forM_
      [""," "," 1","1 ",".1","1.","1e","1e+","1e-","+","--1","0x1p2","NaN","Infinity","1\0"] $ \input -> do
      term <- checked ("putStrLn (formatDouble 1 (readDouble " ++ show input ++ "))")
      observed <- B.execute backends IOEntry (Input "" False) term
      case B.outcome observed of
        Left err | show err == "invalid Double input" -> pure ()
        _ -> fail (show observed))
  , ("bootstrap primitives: arguments exclude executable and preserve Unicode", do
      term <- checked "do { n <- getArgCount; printInt n; a <- getArg 0; b <- getArg 1; c <- getArg 2; putStrLn a; putStrLn b; putStrLn c }"
      observed <- B.executeWithArguments backends ["--type","λ😀",""] IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "3\n--type\nλ😀\n\n") (fail (show observed)))
  , ("bootstrap primitives: diagnostics are ordered and separate from stdout", do
      term <- checked "do { putStr \"out\"; putErr \"diagnostic λ\\0\\n\"; putStrLn \"put\" }"
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "output\n" && B.stderrOutput observed == "diagnostic λ\0\n" &&
        B.events observed == [B.Write "out",B.WriteError "diagnostic λ\0\n",B.Write "put\n"])
        (fail (show observed)))
  , ("bootstrap primitives: diagnostic write failures stop continuation", do
      term <- checked "do { putErr \"error\"; getLine; return () }"
      observed <- B.execute backends IOEntry (Input "unused\n" True) term
      case B.outcome observed of
        Left err | show err == "IO error: write failed" && B.stderrOutput observed == "error" && B.remaining observed == "unused\n" -> pure ()
        _ -> fail (show observed))
  , ("bootstrap primitives: executable path is canonical and names this process", do
      term <- checked "do { path <- getExecutablePath; present <- fileExists path; canonical <- canonicalPath path; printInt (if present then 1 else 0); printInt (if eqString canonical path then 1 else 0); printInt (stringCodeAt path 0) }"
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "1\n1\n47\n") (fail (show observed)))
  , ("bootstrap primitives: complete input preserves UTF-8, lines and NUL", forM_
      ["","\n","first\nλ😀\0\nlast","unterminated"] $ \input -> do
      term <- checked "do { text <- getContents; putStr text; empty <- getContents; printInt (stringLength empty) }"
      observed <- B.execute backends IOEntry (Input input False) term
      right (B.outcome observed)
      unless (B.output observed == input ++ "0\n" && null (B.remaining observed)) (fail (show observed)))
  , ("bootstrap primitives: complete input rejects invalid UTF-8", do
      term <- checked "do { text <- getContents; putStr text }"
      observed <- B.execute backends IOEntry (RawInput (BS.pack [65,10,255,10]) False) term
      case B.outcome observed of
        Left err | show err == "IO error: invalid UTF-8 input" && null (B.output observed) && null (B.remaining observed) -> pure ()
        _ -> fail (show observed))
  , ("bootstrap primitives: exit status stops pending effects", forM_ [0,1,23,255] $ \status -> do
      term <- checked ("do { putStrLn \"before\"; putErr \"diagnostic\"; exitWith " ++ show (status::Int) ++ "; putStrLn \"after\"; getLine }")
      observed <- B.execute backends IOEntry (Input "unused\n" False) term
      let statusOK = if status == 0 then B.outcome observed == Right () else
            either ((== "exit status " ++ show status) . show) (const False) (B.outcome observed)
      unless (statusOK && B.output observed == "before\n" && B.stderrOutput observed == "diagnostic" && B.remaining observed == "unused\n")
        (fail (show observed)))
  , ("bootstrap primitives: UTF-8 files and canonical paths", withScratch $ \directory -> do
      let file = directory </> "λ-source.emlf"
          absent = directory </> "missing.emlf"
          contents = "module λ where\ntext = \"😀\"\0\n"
      writeFile file "original"
      canonical <- canonicalizePath file
      term <- checked ("do { present <- fileExists " ++ show file ++ "; missing <- fileExists " ++ show absent ++
        "; directory <- fileExists " ++ show directory ++ "; printInt (if present then 1 else 0); " ++
        "printInt (if missing then 1 else 0); printInt (if directory then 1 else 0); " ++
        "writeFile " ++ show file ++ " " ++ show contents ++ "; text <- readFile " ++ show file ++
        "; putStr text; name <- canonicalPath " ++ show (directory </> "." </> "λ-source.emlf") ++ "; putStrLn name }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "1\n0\n0\n" ++ contents ++ canonical ++ "\n") (fail (show observed))
      bytes <- BS.readFile file
      unless (bytes == Text.encodeUtf8 (Text.pack contents)) (fail "writeFile changed UTF-8 bytes"))
  , ("host IO: environment mutation and inheritance", do
      term <- checked "do { setEnv \"MLF_PACKAGE_TEST_ENV\" \"literal $() λ\"; value <- getEnv \"MLF_PACKAGE_TEST_ENV\"; putStrLn value; unsetEnv \"MLF_PACKAGE_TEST_ENV\"; absent <- getEnv \"MLF_PACKAGE_TEST_ENV\"; printInt (stringLength absent) }"
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "literal $() λ\n0\n") (fail (show observed)))
  , ("host IO: binary SHA-256 vectors", withScratch $ \directory -> do
      let file = directory </> "digest input"
      forM_ [(BS.empty,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
             (BS.pack [97,98,99],"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
             (BS.replicate 1000000 97,"cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")]
        $ \(bytes,expected) -> do
          BS.writeFile file bytes
          term <- checked ("do { hash <- fileDigest " ++ show file ++ "; putStrLn hash }")
          observed <- B.execute backends IOEntry (Input "" False) term
          right (B.outcome observed)
          unless (B.output observed == expected ++ "\n") (fail (show observed)))
  , ("host IO: directory listing and lock lifecycle", withScratch $ \directory -> do
      let file = directory </> "only file"
          lock = directory </> "lock"
      writeFile file "x"
      writeFile lock ""
      term <- checked ("do { yes <- directoryExists " ++ show directory ++ "; no <- directoryExists " ++ show file ++
        "; printInt (if yes then 1 else 0); printInt (if no then 1 else 0); names <- listDirectory " ++ show directory ++
        "; printInt (stringLength names); handle <- acquireFileLock " ++ show lock ++ "; releaseFileLock handle; putStrLn \"released\" }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "1\n0\n15\nreleased\n") (fail (show observed)))
  , ("host IO: literal argv, cwd, redirects and exit status", withScratch $ \directory -> do
      let out = directory </> "stdout"
          err = directory </> "stderr"
          spec = concatMap (++ "\0") ["10","",out,err,"/usr/bin/printf","%s|%s|%s","a b","$(false)","λ\nline"]
      term <- checked ("do { status <- runProcess " ++ show directory ++ " " ++ show spec ++
        "; printInt status; text <- readFile " ++ show out ++ "; putStrLn text; errors <- readFile " ++ show err ++ "; printInt (stringLength errors) }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "0\na b|$(false)|λ\nline\n0\n") (fail (show observed)))
  , ("host IO: process launch failures return status", withScratch $ \directory -> do
      let nonExecutable = directory </> "not executable"
      writeFile nonExecutable "not a program"
      forM_ [(directory </> "missing",127),(nonExecutable,126)] $ \(command,status) -> do
        let spec = concatMap (++ "\0") ["5","",directory </> "out",directory </> "err",command]
        term <- checked ("do { status <- runProcess " ++ show directory ++ " " ++ show spec ++ "; printInt status }")
        observed <- B.execute backends IOEntry (Input "" False) term
        right (B.outcome observed)
        unless (B.output observed == show (status :: Int) ++ "\n") (fail (show observed)))
  , ("host IO: repeated launches retain process-group isolation", withScratch $ \directory -> do
      let spec = concatMap (++ "\0") ["5","",directory </> "out",directory </> "err","/usr/bin/true"]
      term <- checked ("go : Int -> IO Int\ngo n = if n == 0 then return 0 else do { status <- runProcess " ++
        show directory ++ " " ++ show spec ++ "; if status == 0 then go (n - 1) else return status }\nmain = do { status <- go 80; printInt status }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "0\n") (fail (show observed)))
  , ("host IO: process timeout returns 124", withScratch $ \directory -> do
      let spec = concatMap (++ "\0") ["1","",directory </> "out",directory </> "err","/bin/sleep","10"]
      term <- checked ("do { status <- runProcess " ++ show directory ++ " " ++ show spec ++ "; printInt status }")
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "124\n") (fail (show observed)))
  , ("bootstrap primitives: file errors retain effect order", withScratch $ \directory -> do
      let bad = directory </> "bad.emlf"
      BS.writeFile bad (BS.pack [255])
      forM_
        [("readFile " ++ show bad,"IO error: invalid UTF-8 input"),
         ("readFile " ++ show (directory </> "missing"),"IO error: file read failed"),
         ("writeFile " ++ show directory ++ " \"text\"","IO error: file write failed"),
         ("canonicalPath " ++ show (directory </> "missing"),"IO error: canonical path failed")] $ \(action,message) -> do
        term <- checked ("do { putStrLn \"before\"; " ++ action ++ " }")
        observed <- B.execute backends IOEntry (Input "" False) term
        case B.outcome observed of
          Left err | show err == message && B.output observed == "before\n" -> pure ()
          _ -> fail (show observed))
  , ("bootstrap primitives: cached Unicode offsets survive collection", do
      term <- checked (unlines
        ["churn : Int -> IO Unit", "churn n = if n == 0 then return () else do { a <- newIntArray 1 n; churn (n - 1) }",
         "main = do { let text = concatString \"λ\" \"😀end\"; printInt (stringLength text); churn 300; printInt (stringCodeAt text 1); putStrLn (stringSlice text 2 3) }"])
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "5\n128512\nend\n") (fail (show observed)))
  , ("bootstrap primitives: collection preserves suspended pure work and cyclic data", do
      term <- checked (unlines
        [ "data Cycle = Cycle Int Cycle"
        , "repeatApply : (Int -> Int) -> Int -> Int -> Int"
        , "repeatApply f n value = if n == 0 then value else f (repeatApply f (n - 1) value)"
        , "churn : Int -> Int -> Int"
        , "churn n value = if n == 0 then value else churn (n - 1) (remInt (value * 999999999999999999999999999999 + n) 100000000000000000000000000000000000000000000000000000000000000000007)"
        , "main = do"
        , "  let rec circle : Cycle = Cycle 17 circle"
        , "  let large = 99999999999999999999999999999999999999999999999999"
        , "  array <- newIntArray 1 large"
        , "  table <- newIntTable"
        , "  writeIntTable table large (large + 5)"
        , "  add <- return (\\x -> x + large)"
        , "  printInt (quotInt (repeatApply add 4000 0) large)"
        , "  printInt (seq (churn 12000 3) 23)"
        , "  a <- readIntArray array 0"
        , "  b <- readIntTable table large"
        , "  printInt (b - a)"
        , "  case circle of Cycle first tail -> case tail of Cycle second ignored -> printInt (first + second)"
        ])
      observed <- B.execute backends IOEntry (Input "" False) term
      right (B.outcome observed)
      unless (B.output observed == "4000\n23\n5\n34\n") (fail (show observed)))
  , ("bootstrap primitives: signatures reject mismatched types", forM_
      ["stringLength 1", "stringCodeAt \"x\" true", "stringFromCode 1.0", "doubleToBits 1", "doubleFromBits 1.0",
       "readFile 2", "writeFile \"x\" 1", "fileExists true", "getArg \"1\"", "putErr 1", "exitWith true"] $ \source ->
        case compile "<invalid bootstrap primitive>" source of
          Left _ -> pure (); Right _ -> fail ("accepted " ++ source))
  ]

programs :: [(String,String,String)]
programs =
  [ ("scalar indexing counts characters and preserves NUL",
      "do { printInt (stringLength \"Aλ😀\\0\"); printInt (stringCodeAt \"Aλ😀\\0\" 1); printInt (stringCodeAt \"Aλ😀\\0\" 2); " ++
      "printInt (stringCodeAt \"Aλ😀\\0\" 3); putStrLn (stringSlice \"Aλ😀\\0\" 1 2); putStrLn (stringSlice \"λ\" 1 0) }",
      "4\n955\n128512\n0\nλ😀\n\n")
  , ("string comparison follows Unicode scalar order",
      "do { printInt (compareString \"λ\" \"😀\"); printInt (compareString \"a\\0\" \"a\"); printInt (compareString \"😀\" \"😀\") }",
      "-1\n1\n0\n")
  , ("floating bit representation includes signed zero and nonfinite values",
      "do { printInt (doubleToBits 1.0); printInt (doubleToBits (readDouble \"-0.0\")); " ++
      "printInt (doubleToBits (doubleFromBits 18446744073709551615)); putStrLn (formatDouble 1 (readDouble \"+1.25e2\")); " ++
      "putStrLn (formatDouble 1 (readDouble \"1e999\")); putStrLn (formatDouble 1 (readDouble \"-1e-999\")) }",
      "4607182418800017408\n9223372036854775808\n18446744073709551615\n125.0\nInfinity\n-0.0\n")
  , ("seq forces only weak head and unused panic stays lazy",
      "data Box a = Box a; let unused = panic \"unused\" in do { printInt (seq (Box (panic \"field\")) 7); " ++
      "return (panic \"unused result\"); printInt (if true then 8 else panic \"unused branch\") }", "7\n8\n")
  , ("escaping primitives follow the same runtime ABI",
      "do { slice <- return stringSlice; at <- return stringCodeAt; cmp <- return compareString; len <- return stringLength; " ++
      "from <- return stringFromCode; read <- return readDouble; bits <- return doubleToBits; fromBits <- return doubleFromBits; " ++
      "force <- return seq; putStrLn (slice \"Aλ😀\" 1 2); printInt (at (from 955) 0); printInt (len (from 128512)); " ++
      "printInt (cmp \"a\" \"b\"); printInt (bits (fromBits (bits (read \"1.5\")))); printInt (force (\\x -> x) 9) }",
      "λ😀\n955\n1\n-1\n4609434218613702656\n9\n")
  , ("empty arguments and lazy file operations",
      "do { let unused = readFile \"does-not-exist\"; return unused; let another = writeFile \"unused\" (panic \"unused\"); " ++
      "return another; n <- getArgCount; printInt n }", "0\n")
  ]

failures :: [(String,String,String)]
failures =
  [ ("empty index", "printInt (stringCodeAt \"\" 0)", "string index out of bounds")
  , ("negative index", "printInt (stringCodeAt \"λ\" (-1))", "string index out of bounds")
  , ("huge index", "printInt (stringCodeAt \"λ\" 999999999999999999999)", "string index out of bounds")
  , ("negative slice", "putStr (stringSlice \"λ\" (-1) 1)", "string slice out of bounds")
  , ("oversize slice", "putStr (stringSlice \"λ\" 1 1)", "string slice out of bounds")
  , ("negative slice count", "putStr (stringSlice \"λ\" 0 (-1))", "string slice out of bounds")
  , ("surrogate", "putStr (stringFromCode 55296)", "invalid Unicode scalar")
  , ("past maximum scalar", "putStr (stringFromCode 1114112)", "invalid Unicode scalar")
  , ("negative scalar", "putStr (stringFromCode (-1))", "invalid Unicode scalar")
  , ("negative double bits", "putStr (formatDouble 1 (doubleFromBits (-1)))", "Double bit pattern out of bounds")
  , ("oversize double bits", "putStr (formatDouble 1 (doubleFromBits 18446744073709551616))", "Double bit pattern out of bounds")
  , ("seq demands first", "printInt (seq (panic \"forced\") 1)", "forced")
  , ("panic preserves embedded NUL and newline", "panic \"bad\\0message\\n\"", "bad\0message\n")
  , ("missing argument", "getArg 0", "argument index out of bounds")
  , ("invalid negative exit", "exitWith (-1)", "exit status must be between 0 and 255")
  , ("invalid large exit", "exitWith 256", "exit status must be between 0 and 255")
  , ("NUL path", "fileExists \"a\\0b\"", "file path contains NUL")
  ]

withScratch :: (FilePath -> IO a) -> IO a
withScratch = bracket create removeDirectoryRecursive
  where
    create = do
      parent <- getTemporaryDirectory
      (path,handle) <- openTempFile parent "mlf-bootstrap-primitives"
      hClose handle
      removeFile path
      createDirectory path
      pure path
