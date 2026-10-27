-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TestDrivers where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Build as B;
  -- These native products depend on the actual C/LLVM bytes and native toolchain,
  -- independently of the source frontend that produced a driver's LLVM.
  nativeInputs :: B.Builder -> J.Json -> J.Json;
  nativeInputs builder native =
    J.set "native" native
      (B.info
         (S.map (\key -> (,) key (J.get key (B.tools builder)))
            (O.words "clang system machine native_environment windows")));
  -- pkg-config may omit -L for a library in the compiler's default search path.
  -- Fingerprint those resolved files as well as explicit library/include paths.
  nativeIdentity :: B.Builder -> [] String -> IO J.Json;
  nativeIdentity builder flags =
    do {
      explicit <- B.flagIdentity flags;
      implicit <-
        S.mapM
          (\flag ->
             do {
               candidates <-
                 S.mapM
                   (\suffix ->
                      do {
                        let {
                          name = ("lib" ++ (O.drop 2 flag ++ suffix))
                        };
                        text <-
                          B.capture builder (B.root builder)
                            ((:) (B.clang builder) ((:) ("-print-file-name=" ++ name) []))
                            ""
                            "";
                        let {
                          path =
                            if O.ends "\r\n" text
                            then stringSlice text 0 (stringLength text - 2)
                            else if O.ends "\n" text
                                 then stringSlice text 0 (stringLength text - 1)
                                 else text
                        };
                        present <- fileExists path;
                        if present
                        then do {
                               actual <- canonicalPath path;
                               return (Just actual)
                             }
                        else return Nothing
                      })
                   (O.words ".dylib .so .dll.a .a");
               return (S.catMaybes candidates)
             })
          (S.filter (O.starts "-l") flags);
      libraries <-
        B.hashFiles
          (S.append (S.map S.fst (J.items (J.get "libraries" explicit))) (S.concat implicit));
      let {
        identity = J.set "libraries" libraries explicit
      };
      B.record builder "native_inputs" identity;
      return identity
    };
  -- Clang emits Make words, whose quotes are literal filename characters. Shell
  -- word parsing would drop apostrophes and double quotes from dependency paths.
  dependencyWords :: String -> [] String;
  dependencyWords source = dependencyWordsAt source 0 "" [];
  dependencyWordsAt :: String -> Int -> String -> [] String -> [] String;
  dependencyWordsAt source offset word done =
    if (offset >= stringLength source)
    then S.reverse (if eqString word "" then done else (:) word done)
    else let {
           c = stringCodeAt source offset
         } in
         if ((c == 92) && ((offset + 1) < stringLength source))
         then let {
                next = stringCodeAt source (offset + 1)
              } in
              if (next == 10)
              then dependencyWordsAt source (offset + 2) word done
              else if ((next == 13) &&
                       (((offset + 2) < stringLength source) &&
                        (stringCodeAt source (offset + 2) == 10)))
                   then dependencyWordsAt source (offset + 3) word done
                   else if (J.space next || ((next == 35) || ((next == 92) || (next == 58))))
                        then dependencyWordsAt source (offset + 2)
                               (word ++ O.char source (offset + 1))
                               done
                        else dependencyWordsAt source (offset + 1) (word ++ "\\") done
         else if ((c == 36) &&
                  (((offset + 1) < stringLength source) &&
                   (stringCodeAt source (offset + 1) == 36)))
              then dependencyWordsAt source (offset + 2) (word ++ "$") done
              else if J.space c
                   then dependencyWordsAt source (offset + 1) ""
                          (if eqString word "" then done else (:) word done)
                   else dependencyWordsAt source (offset + 1) (word ++ O.char source offset) done;
  cObject :: B.Builder -> J.Json -> String -> J.Json -> [] String -> IO String;
  -- Include the headers Clang actually resolves, including default include
  -- directories and SDK headers that need not appear as explicit -I flags.
  cObject builder native source dependencies options =
    do {
      text <-
        B.capture builder (B.root builder)
          (S.append ((:) (B.clang builder) options)
             ((:) "-M" ((:) "-MT" ((:) "test-driver" ((:) source [])))))
          ""
          "";
      let {
        paths = S.drop 1 (dependencyWords text)
      };
      O.require (S.not (S.null paths)) "test driver C dependency scan produced no files";
      headers <- B.hashFiles paths;
      B.record builder "native_inputs" (B.obj2 "headers" headers "libraries" J.empty);
      let {
        inputs =
          J.set "format" (J.num 1)
            (J.set "compiler_dependencies" headers
               (J.set "source" (J.str source)
                  (J.set "source_files" dependencies
                     (J.set "flags" (J.stringArray options) (nativeInputs builder native)))))
      };
      artifact <-
        B.cached builder "test driver C object" inputs
          (\work ->
             do {
               ignored <-
                 B.capture builder (B.root builder)
                   (S.append ((:) (B.clang builder) options)
                      ((:) "-c" ((:) source ((:) "-o" ((:) (work ++ "/object.o") [])))))
                   ""
                   "";
               present <- fileExists (work ++ "/object.o");
               O.require present "test driver C compiler did not produce an object"
             });
      B.verifyHashes dependencies;
      B.verifyHashes headers;
      return artifact
    };
  linkObject :: B.Builder -> J.Json -> String -> [] String -> [] String -> IO String;
  linkObject builder native llvm objects flags =
    do {
      let {
        paths = (:) (llvm ++ "/program.o") objects
      };
      hashes <- B.hashFiles paths;
      let {
        options = O.words "-O2 -Wno-override-module"
      };
      let {
        inputs =
          J.set "format" (J.num 1)
            (J.set "object_paths" (J.stringArray paths)
               (J.set "objects" hashes
                  (J.set "flags" (J.stringArray (S.append options flags))
                     (nativeInputs builder native))))
      };
      B.cached builder "test driver native link" inputs
        (\work ->
           do {
             ignored <-
               B.capture builder (B.root builder)
                 (S.append ((:) (B.clang builder) options)
                    (S.append paths
                       (S.append flags
                          ((:) "-o" ((:) (B.executable builder (work ++ "/program")) [])))))
                 ""
                 "";
             present <- fileExists (B.executable builder (work ++ "/program"));
             O.require present "test driver linker did not produce an executable";
             B.copyWindowsFiles builder work
           })
    };
  -- Read the checked cache decision made by this group's builder. Never infer
  -- reuse from the mere presence of a file or from a matching binary elsewhere.
  receipt :: B.Builder -> String -> IO J.Json;
  receipt builder artifact =
    do {
      saved <- J.read (artifact ++ "/artifact.json");
      let {
        key = J.getText "key" "" saved
      };
      valid <- B.cacheValid artifact key;
      O.require valid "test driver artifact changed before recording";
      report <- J.read (B.reportPath builder);
      let {
        rows =
          S.filter (\row -> eqString (J.getText "key" "" row) key)
            (J.values (J.get "builds" report))
      };
      O.require (S.not (S.null rows)) "test driver artifact has no group build receipt";
      hash <- fileDigest (artifact ++ "/artifact.json");
      return
        (J.set "directory" (J.str artifact)
           (J.set "artifact_sha256" (J.str hash)
              (J.set "files" (J.get "files" saved) (S.last rows))))
    }
}
