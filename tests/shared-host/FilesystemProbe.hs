{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import Control.Exception
import System.Environment
main = do
  args <- getArgs
  case args of
    ["file-exists",path] -> F.fileExists (B.literal path) >>= print
    ["canonical-discard",path] -> do
      result <- try (F.canonicalPath (B.literal path) >> pure ())
      print (result :: Either SomeException ())
    ["canonical-force",path] -> do
      result <- try (F.canonicalPath (B.literal path) >>= evaluate . F.stringLength)
      print (result :: Either SomeException Integer)
    ["executable-discard"] -> do
      result <- try (F.getExecutablePath >> pure ())
      print (result :: Either SomeException ())
    ["unicode-roundtrip",directory] -> do
      let path=B.literal (directory++"/emoji-😀.txt")
          contents=B.literal "a😀\0z"
      F.writeFile path contents
      text <- F.readFile path
      print (F.stringLength text,F.eqString contents text)
    ["contents-byte-line"] -> do
      _ <- F.getContents
      result <- try (F.getByteLine >>= F.lengthByteArray)
      print (result :: Either SomeException Integer)
    _ -> error "unknown test mode"
