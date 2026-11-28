-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TestDrivers where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Package.Json as J;
  import qualified Package.Build as B;
  import qualified Tests.TestCompilation as Compilation;
  -- Driver preparation is a client of the same compilation service as the
  -- runtime matrix. Preserve these names for its existing callers.
  nativeInputs :: B.Builder -> J.Json -> J.Json;
  nativeInputs b native = Compilation.nativeInputs (Compilation.fromBuilder b) native;
  nativeIdentity :: B.Builder -> [] String -> IO J.Json;
  nativeIdentity b flags = Compilation.nativeIdentity (Compilation.fromBuilder b) flags;
  dependencyWords :: String -> [] String;
  dependencyWords = Compilation.dependencyWords;
  dependencyWordsAt :: String -> Int -> String -> [] String -> [] String;
  dependencyWordsAt = Compilation.dependencyWordsAt;
  cObject :: B.Builder -> J.Json -> String -> J.Json -> [] String -> IO String;
  cObject b native source dependencies options =
    Compilation.cObject (Compilation.fromBuilder b) native source dependencies options;
  linkObject :: B.Builder -> J.Json -> String -> [] String -> [] String -> IO String;
  linkObject b native llvm objects flags =
    Compilation.linkObject (Compilation.fromBuilder b) native llvm objects flags;
  receipt :: B.Builder -> String -> IO J.Json;
  receipt b artifact = Compilation.receipt (Compilation.fromBuilder b) artifact
}
