-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Primitive where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  -- IDs are the native runtime ABI, append-only in declaration order.
  primitiveCode :: Primitive -> Int;
  primitiveCode p =
    case p of {
      PIOReturn -> 0;
      PIOBind -> 1;
      PPutStr -> 2;
      PPutStrLn -> 3;
      PGetLine -> 4;
      PPrintInt -> 5;
      PConcatString -> 6;
      PShowInt -> 7;
      PAddInt -> 8;
      PSubInt -> 9;
      PEqInt -> 10;
      PLtInt -> 11;
      PEqString -> 12;
      PIfThenElse -> 13;
      PMulInt -> 14;
      PQuotInt -> 15;
      PRemInt -> 16;
      PReadInt -> 17;
      PAddDouble -> 18;
      PSubDouble -> 19;
      PMulDouble -> 20;
      PDivDouble -> 21;
      PSqrtDouble -> 22;
      PEqDouble -> 23;
      PLtDouble -> 24;
      PIntToDouble -> 25;
      PFormatDouble -> 26;
      PNewIntArray -> 27;
      PReadIntArray -> 28;
      PWriteIntArray -> 29;
      PLengthIntArray -> 30;
      PNewDoubleArray -> 31;
      PReadDoubleArray -> 32;
      PWriteDoubleArray -> 33;
      PLengthDoubleArray -> 34;
      PNewByteArray -> 35;
      PReadByteArray -> 36;
      PWriteByteArray -> 37;
      PLengthByteArray -> 38;
      PByteArrayFromString -> 39;
      PPutBytes -> 40;
      PGetByteLine -> 41;
      PNewIntTable -> 42;
      PReadIntTable -> 43;
      PWriteIntTable -> 44;
      PAndInt -> 45;
      PStringLength -> 46;
      PStringCodeAt -> 47;
      PStringSlice -> 48;
      PStringFromCode -> 49;
      PCompareString -> 50;
      PReadDouble -> 51;
      PDoubleToBits -> 52;
      PDoubleFromBits -> 53;
      PSeq -> 54;
      PPanic -> 55;
      PReadFile -> 56;
      PWriteFile -> 57;
      PFileExists -> 58;
      PCanonicalPath -> 59;
      PGetArgCount -> 60;
      PGetArg -> 61;
      PPutErr -> 62;
      PExitWith -> 63;
      PGetExecutablePath -> 64;
      PGetContents -> 65;
      PSTReturn -> 66;
      PSTBind -> 67;
      PRunST -> 68;
      PNewSTArray -> 69;
      PReadSTArray -> 70;
      PWriteSTArray -> 71;
      PLengthSTArray -> 72;
      PGetEnv -> 73;
      PSetEnv -> 74;
      PUnsetEnv -> 75;
      PRunProcess -> 76;
      PListDirectory -> 77;
      PDirectoryExists -> 78;
      PFileDigest -> 79;
      PAcquireFileLock -> 80;
      PReleaseFileLock -> 81;
      PProcessSupervisor -> 82;
      PAsyncScopeNew -> 83;
      PAsyncScopeClose -> 84;
      PAsyncNewCompletion -> 85;
      PAsyncResolveCompletion -> 86;
      PAsyncReadCompletion -> 87;
      PAsyncSubscribeCompletion -> 88;
      PAsyncSubscriptionStatus -> 89;
      PAsyncCancelSubscription -> 90;
      PAsyncStep -> 91;
      PAsyncEnqueue -> 92;
      PAsyncDelay -> 93;
      PAsyncWait -> 94;
      PTextToChars -> 95;
      PTextFromChars -> 96;
      PCharCode -> 97;
      PCharFromCode -> 98;
      PUserError -> 99;
      PIOError -> 100;
      PCatchIOError -> 101;
      PIOErrorString -> 102;
      PEmptyCallStack -> 103;
      PPushCallStack -> 104;
      PPrettyCallStack -> 105;
      PIOErrorWithStack -> 106
    };
  primitiveName :: Primitive -> String;
  primitiveName p =
    case p of {
      PIOReturn -> "ioReturn";
      PIOBind -> "ioBind";
      PPutStr -> "putStr";
      PPutStrLn -> "putStrLn";
      PGetLine -> "getLine";
      PPrintInt -> "printInt";
      PConcatString -> "concatString";
      PShowInt -> "showInt";
      PAddInt -> "addInt";
      PSubInt -> "subInt";
      PEqInt -> "eqInt";
      PLtInt -> "ltInt";
      PEqString -> "eqString";
      PIfThenElse -> "ifThenElse";
      PMulInt -> "mulInt";
      PQuotInt -> "quotInt";
      PRemInt -> "remInt";
      PReadInt -> "readInt";
      PAddDouble -> "addDouble";
      PSubDouble -> "subDouble";
      PMulDouble -> "mulDouble";
      PDivDouble -> "divDouble";
      PSqrtDouble -> "sqrtDouble";
      PEqDouble -> "eqDouble";
      PLtDouble -> "ltDouble";
      PIntToDouble -> "intToDouble";
      PFormatDouble -> "formatDouble";
      PNewIntArray -> "newIntArray";
      PReadIntArray -> "readIntArray";
      PWriteIntArray -> "writeIntArray";
      PLengthIntArray -> "lengthIntArray";
      PNewDoubleArray -> "newDoubleArray";
      PReadDoubleArray -> "readDoubleArray";
      PWriteDoubleArray -> "writeDoubleArray";
      PLengthDoubleArray -> "lengthDoubleArray";
      PNewByteArray -> "newByteArray";
      PReadByteArray -> "readByteArray";
      PWriteByteArray -> "writeByteArray";
      PLengthByteArray -> "lengthByteArray";
      PByteArrayFromString -> "byteArrayFromString";
      PPutBytes -> "putBytes";
      PGetByteLine -> "getByteLine";
      PNewIntTable -> "newIntTable";
      PReadIntTable -> "readIntTable";
      PWriteIntTable -> "writeIntTable";
      PAndInt -> "andInt";
      PStringLength -> "stringLength";
      PStringCodeAt -> "stringCodeAt";
      PStringSlice -> "stringSlice";
      PStringFromCode -> "stringFromCode";
      PCompareString -> "compareString";
      PReadDouble -> "readDouble";
      PDoubleToBits -> "doubleToBits";
      PDoubleFromBits -> "doubleFromBits";
      PSeq -> "seq";
      PPanic -> "panic";
      PReadFile -> "readFile";
      PWriteFile -> "writeFile";
      PFileExists -> "fileExists";
      PCanonicalPath -> "canonicalPath";
      PGetArgCount -> "getArgCount";
      PGetArg -> "getArg";
      PPutErr -> "putErr";
      PExitWith -> "exitWith";
      PGetExecutablePath -> "getExecutablePath";
      PGetContents -> "getContents";
      PSTReturn -> "stReturn";
      PSTBind -> "stBind";
      PRunST -> "runST";
      PNewSTArray -> "newSTArray";
      PReadSTArray -> "readSTArray";
      PWriteSTArray -> "writeSTArray";
      PLengthSTArray -> "lengthSTArray";
      PGetEnv -> "getEnv";
      PSetEnv -> "setEnv";
      PUnsetEnv -> "unsetEnv";
      PRunProcess -> "runProcess";
      PListDirectory -> "listDirectory";
      PDirectoryExists -> "directoryExists";
      PFileDigest -> "fileDigest";
      PAcquireFileLock -> "acquireFileLock";
      PReleaseFileLock -> "releaseFileLock";
      PProcessSupervisor -> "processSupervisor";
      PAsyncScopeNew -> "asyncScopeNew";
      PAsyncScopeClose -> "asyncScopeClose";
      PAsyncNewCompletion -> "asyncNewCompletion";
      PAsyncResolveCompletion -> "asyncResolveCompletion";
      PAsyncReadCompletion -> "asyncReadCompletion";
      PAsyncSubscribeCompletion -> "asyncSubscribeCompletion";
      PAsyncSubscriptionStatus -> "asyncSubscriptionStatus";
      PAsyncCancelSubscription -> "asyncCancelSubscription";
      PAsyncStep -> "asyncStep";
      PAsyncEnqueue -> "asyncEnqueue";
      PAsyncDelay -> "asyncDelay";
      PAsyncWait -> "asyncWait";
      PTextToChars -> "textToChars";
      PTextFromChars -> "textFromChars";
      PCharCode -> "charCode";
      PCharFromCode -> "charFromCode";
      PUserError -> "userError";
      PIOError -> "ioError";
      PCatchIOError -> "catchIOError";
      PIOErrorString -> "ioeGetErrorString";
      PEmptyCallStack -> "mlfEmptyCallStack";
      PPushCallStack -> "mlfPushCallStack";
      PPrettyCallStack -> "mlfPrettyCallStack";
      PIOErrorWithStack -> "mlfIOErrorWithStack"
    };
  legacyPrimitives :: [] Primitive;
  legacyPrimitives =
    (:) PIOReturn
      ((:) PIOBind
         ((:) PPutStr
            ((:) PPutStrLn
               ((:) PGetLine
                  ((:) PPrintInt
                     ((:) PConcatString
                        ((:) PShowInt
                           ((:) PAddInt
                              ((:) PSubInt
                                 ((:) PEqInt
                                    ((:) PLtInt
                                       ((:) PEqString
                                          ((:) PIfThenElse
                                             ((:) PMulInt
                                                ((:) PQuotInt
                                                   ((:) PRemInt
                                                      ((:) PReadInt
                                                         ((:) PAddDouble
                                                            ((:) PSubDouble
                                                               ((:) PMulDouble
                                                                  ((:) PDivDouble
                                                                     ((:) PSqrtDouble
                                                                        ((:) PEqDouble
                                                                           ((:) PLtDouble
                                                                              ((:) PIntToDouble
                                                                                 ((:) PFormatDouble
                                                                                    ((:)
                                                                                       PNewIntArray
                                                                                       ((:)
                                                                                          PReadIntArray
                                                                                          ((:)
                                                                                             PWriteIntArray
                                                                                             ((:)
                                                                                                PLengthIntArray
                                                                                                ((:)
                                                                                                   PNewDoubleArray
                                                                                                   ((:)
                                                                                                      PReadDoubleArray
                                                                                                      ((:)
                                                                                                         PWriteDoubleArray
                                                                                                         ((:)
                                                                                                            PLengthDoubleArray
                                                                                                            ((:)
                                                                                                               PNewByteArray
                                                                                                               ((:)
                                                                                                                  PReadByteArray
                                                                                                                  ((:)
                                                                                                                     PWriteByteArray
                                                                                                                     ((:)
                                                                                                                        PLengthByteArray
                                                                                                                        ((:)
                                                                                                                           PByteArrayFromString
                                                                                                                           ((:)
                                                                                                                              PPutBytes
                                                                                                                              ((:)
                                                                                                                                 PGetByteLine
                                                                                                                                 ((:)
                                                                                                                                    PNewIntTable
                                                                                                                                    ((:)
                                                                                                                                       PReadIntTable
                                                                                                                                       ((:)
                                                                                                                                          PWriteIntTable
                                                                                                                                          ((:)
                                                                                                                                             PAndInt
                                                                                                                                             ((:)
                                                                                                                                                PStringLength
                                                                                                                                                ((:)
                                                                                                                                                   PStringCodeAt
                                                                                                                                                   ((:)
                                                                                                                                                      PStringSlice
                                                                                                                                                      ((:)
                                                                                                                                                         PStringFromCode
                                                                                                                                                         ((:)
                                                                                                                                                            PCompareString
                                                                                                                                                            ((:)
                                                                                                                                                               PReadDouble
                                                                                                                                                               ((:)
                                                                                                                                                                  PDoubleToBits
                                                                                                                                                                  ((:)
                                                                                                                                                                     PDoubleFromBits
                                                                                                                                                                     ((:)
                                                                                                                                                                        PSeq
                                                                                                                                                                        ((:)
                                                                                                                                                                           PPanic
                                                                                                                                                                           ((:)
                                                                                                                                                                              PReadFile
                                                                                                                                                                              ((:)
                                                                                                                                                                                 PWriteFile
                                                                                                                                                                                 ((:)
                                                                                                                                                                                    PFileExists
                                                                                                                                                                                    ((:)
                                                                                                                                                                                       PCanonicalPath
                                                                                                                                                                                       ((:)
                                                                                                                                                                                          PGetArgCount
                                                                                                                                                                                          ((:)
                                                                                                                                                                                             PGetArg
                                                                                                                                                                                             ((:)
                                                                                                                                                                                                PPutErr
                                                                                                                                                                                                ((:)
                                                                                                                                                                                                   PExitWith
                                                                                                                                                                                                   ((:)
                                                                                                                                                                                                      PGetExecutablePath
                                                                                                                                                                                                      ((:)
                                                                                                                                                                                                         PGetContents
                                                                                                                                                                                                         ((:)
                                                                                                                                                                                                            PSTReturn
                                                                                                                                                                                                            ((:)
                                                                                                                                                                                                               PSTBind
                                                                                                                                                                                                               ((:)
                                                                                                                                                                                                                  PRunST
                                                                                                                                                                                                                  ((:)
                                                                                                                                                                                                                     PNewSTArray
                                                                                                                                                                                                                     ((:)
                                                                                                                                                                                                                        PReadSTArray
                                                                                                                                                                                                                        ((:)
                                                                                                                                                                                                                           PWriteSTArray
                                                                                                                                                                                                                           ((:)
                                                                                                                                                                                                                              PLengthSTArray
                                                                                                                                                                                                                              ((:)
                                                                                                                                                                                                                                 PGetEnv
                                                                                                                                                                                                                                 ((:)
                                                                                                                                                                                                                                    PSetEnv
                                                                                                                                                                                                                                    ((:)
                                                                                                                                                                                                                                       PUnsetEnv
                                                                                                                                                                                                                                       ((:)
                                                                                                                                                                                                                                          PRunProcess
                                                                                                                                                                                                                                          ((:)
                                                                                                                                                                                                                                             PListDirectory
                                                                                                                                                                                                                                             ((:)
                                                                                                                                                                                                                                                PDirectoryExists
                                                                                                                                                                                                                                                ((:)
                                                                                                                                                                                                                                                   PFileDigest
                                                                                                                                                                                                                                                   ((:)
                                                                                                                                                                                                                                                      PAcquireFileLock
                                                                                                                                                                                                                                                      ((:)
                                                                                                                                                                                                                                                         PReleaseFileLock
                                                                                                                                                                                                                                                         ((:)
                                                                                                                                                                                                                                                            PProcessSupervisor
                                                                                                                                                                                                                                                            ((:)
                                                                                                                                                                                                                                                               PAsyncScopeNew
                                                                                                                                                                                                                                                               ((:)
                                                                                                                                                                                                                                                                  PAsyncScopeClose
                                                                                                                                                                                                                                                                  ((:)
                                                                                                                                                                                                                                                                     PAsyncNewCompletion
                                                                                                                                                                                                                                                                     ((:)
                                                                                                                                                                                                                                                                        PAsyncResolveCompletion
                                                                                                                                                                                                                                                                        ((:)
                                                                                                                                                                                                                                                                           PAsyncReadCompletion
                                                                                                                                                                                                                                                                           ((:)
                                                                                                                                                                                                                                                                              PAsyncSubscribeCompletion
                                                                                                                                                                                                                                                                              ((:)
                                                                                                                                                                                                                                                                                 PAsyncSubscriptionStatus
                                                                                                                                                                                                                                                                                 ((:)
                                                                                                                                                                                                                                                                                    PAsyncCancelSubscription
                                                                                                                                                                                                                                                                                    ((:)
                                                                                                                                                                                                                                                                                       PAsyncStep
                                                                                                                                                                                                                                                                                       ((:)
                                                                                                                                                                                                                                                                                          PAsyncEnqueue
                                                                                                                                                                                                                                                                                          ((:)
                                                                                                                                                                                                                                                                                             PAsyncDelay
                                                                                                                                                                                                                                                                                             ((:)
                                                                                                                                                                                                                                                                                                PAsyncWait
                                                                                                                                                                                                                                                                                                []))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))));
  allPrimitives :: [] Primitive;
  allPrimitives = S.append legacyPrimitives
    ((:) PTextToChars ((:) PTextFromChars ((:) PCharCode ((:) PCharFromCode ((:) PUserError ((:) PIOError ((:) PCatchIOError ((:) PIOErrorString ((:) PEmptyCallStack ((:) PPushCallStack ((:) PPrettyCallStack ((:) PIOErrorWithStack []))))))))))));
  lookupTargetPrimitive :: String -> Maybe Primitive;
  lookupTargetPrimitive name = S.find (\p -> eqString (primitiveName p) name) allPrimitives;
  lookupPrimitive :: String -> Maybe Primitive;
  lookupPrimitive name =
    if (eqString name "return" || eqString name "pure")
    then Just PIOReturn
    else if eqString name "bind" then Just PIOBind else lookupTargetPrimitive name;
  charListField :: Field;
  charListField = Applied "[]" ((:) (Applied "Char" []) []);
  primitiveSignature :: Primitive -> (,) ([] ((,) String Kind)) Field;
  primitiveSignature p =
    case p of {
      PIOReturn ->
        (,) ((:) ((,) "a" Star) [])
          (Function (Parameter "a") (Applied "IO" ((:) (Parameter "a") [])));
      PIOBind ->
        (,) ((:) ((,) "a" Star) ((:) ((,) "b" Star) []))
          (Function (Applied "IO" ((:) (Parameter "a") []))
             (Function (Function (Parameter "a") (Applied "IO" ((:) (Parameter "b") [])))
                (Applied "IO" ((:) (Parameter "b") []))));
      PPutStr ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PPutStrLn ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PGetLine -> (,) [] (Applied "IO" ((:) (Applied "String" []) []));
      PPrintInt ->
        (,) [] (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PConcatString ->
        (,) []
          (Function (Applied "String" [])
             (Function (Applied "String" []) (Applied "String" [])));
      PShowInt -> (,) [] (Function (Applied "Int" []) (Applied "String" []));
      PAddInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PSubInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PEqInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Bool" [])));
      PLtInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Bool" [])));
      PEqString ->
        (,) []
          (Function (Applied "String" []) (Function (Applied "String" []) (Applied "Bool" [])));
      PIfThenElse ->
        (,) ((:) ((,) "a" Star) [])
          (Function (Applied "Bool" [])
             (Function (Parameter "a") (Function (Parameter "a") (Parameter "a"))));
      PMulInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PQuotInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PRemInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PReadInt -> (,) [] (Function (Applied "String" []) (Applied "Int" []));
      PAddDouble ->
        (,) []
          (Function (Applied "Double" [])
             (Function (Applied "Double" []) (Applied "Double" [])));
      PSubDouble ->
        (,) []
          (Function (Applied "Double" [])
             (Function (Applied "Double" []) (Applied "Double" [])));
      PMulDouble ->
        (,) []
          (Function (Applied "Double" [])
             (Function (Applied "Double" []) (Applied "Double" [])));
      PDivDouble ->
        (,) []
          (Function (Applied "Double" [])
             (Function (Applied "Double" []) (Applied "Double" [])));
      PSqrtDouble -> (,) [] (Function (Applied "Double" []) (Applied "Double" []));
      PEqDouble ->
        (,) []
          (Function (Applied "Double" []) (Function (Applied "Double" []) (Applied "Bool" [])));
      PLtDouble ->
        (,) []
          (Function (Applied "Double" []) (Function (Applied "Double" []) (Applied "Bool" [])));
      PIntToDouble -> (,) [] (Function (Applied "Int" []) (Applied "Double" []));
      PFormatDouble ->
        (,) []
          (Function (Applied "Int" []) (Function (Applied "Double" []) (Applied "String" [])));
      PNewIntArray ->
        (,) []
          (Function (Applied "Int" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "IntArray" []) []))));
      PReadIntArray ->
        (,) []
          (Function (Applied "IntArray" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "Int" []) []))));
      PWriteIntArray ->
        (,) []
          (Function (Applied "IntArray" [])
             (Function (Applied "Int" [])
                (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])))));
      PLengthIntArray ->
        (,) [] (Function (Applied "IntArray" []) (Applied "IO" ((:) (Applied "Int" []) [])));
      PNewDoubleArray ->
        (,) []
          (Function (Applied "Int" [])
             (Function (Applied "Double" [])
                (Applied "IO" ((:) (Applied "DoubleArray" []) []))));
      PReadDoubleArray ->
        (,) []
          (Function (Applied "DoubleArray" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "Double" []) []))));
      PWriteDoubleArray ->
        (,) []
          (Function (Applied "DoubleArray" [])
             (Function (Applied "Int" [])
                (Function (Applied "Double" []) (Applied "IO" ((:) (Applied "()" []) [])))));
      PLengthDoubleArray ->
        (,) []
          (Function (Applied "DoubleArray" []) (Applied "IO" ((:) (Applied "Int" []) [])));
      PNewByteArray ->
        (,) []
          (Function (Applied "Int" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "ByteArray" []) []))));
      PReadByteArray ->
        (,) []
          (Function (Applied "ByteArray" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "Int" []) []))));
      PWriteByteArray ->
        (,) []
          (Function (Applied "ByteArray" [])
             (Function (Applied "Int" [])
                (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])))));
      PLengthByteArray ->
        (,) [] (Function (Applied "ByteArray" []) (Applied "IO" ((:) (Applied "Int" []) [])));
      PByteArrayFromString ->
        (,) []
          (Function (Applied "String" []) (Applied "IO" ((:) (Applied "ByteArray" []) [])));
      PPutBytes ->
        (,) []
          (Function (Applied "ByteArray" [])
             (Function (Applied "Int" [])
                (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])))));
      PGetByteLine -> (,) [] (Applied "IO" ((:) (Applied "ByteArray" []) []));
      PNewIntTable -> (,) [] (Applied "IO" ((:) (Applied "IntTable" []) []));
      PReadIntTable ->
        (,) []
          (Function (Applied "IntTable" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "Int" []) []))));
      PWriteIntTable ->
        (,) []
          (Function (Applied "IntTable" [])
             (Function (Applied "Int" [])
                (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])))));
      PAndInt ->
        (,) [] (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PStringLength -> (,) [] (Function (Applied "String" []) (Applied "Int" []));
      PStringCodeAt ->
        (,) []
          (Function (Applied "String" []) (Function (Applied "Int" []) (Applied "Int" [])));
      PStringSlice ->
        (,) []
          (Function (Applied "String" [])
             (Function (Applied "Int" []) (Function (Applied "Int" []) (Applied "String" []))));
      PStringFromCode -> (,) [] (Function (Applied "Int" []) (Applied "String" []));
      PCompareString ->
        (,) []
          (Function (Applied "String" []) (Function (Applied "String" []) (Applied "Int" [])));
      PReadDouble -> (,) [] (Function (Applied "String" []) (Applied "Double" []));
      PDoubleToBits -> (,) [] (Function (Applied "Double" []) (Applied "Int" []));
      PDoubleFromBits -> (,) [] (Function (Applied "Int" []) (Applied "Double" []));
      PSeq ->
        (,) ((:) ((,) "a" Star) ((:) ((,) "b" Star) []))
          (Function (Parameter "a") (Function (Parameter "b") (Parameter "b")));
      PPanic -> (,) ((:) ((,) "a" Star) []) (Function (Applied "String" []) (Parameter "a"));
      PReadFile ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PWriteFile ->
        (,) []
          (Function (Applied "String" [])
             (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) []))));
      PFileExists ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "Bool" []) [])));
      PCanonicalPath ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PGetArgCount -> (,) [] (Applied "IO" ((:) (Applied "Int" []) []));
      PGetArg ->
        (,) [] (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PPutErr ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PExitWith ->
        (,) ((:) ((,) "a" Star) [])
          (Function (Applied "Int" []) (Applied "IO" ((:) (Parameter "a") [])));
      PGetExecutablePath -> (,) [] (Applied "IO" ((:) (Applied "String" []) []));
      PGetContents -> (,) [] (Applied "IO" ((:) (Applied "String" []) []));
      PSTReturn ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) []))
          (Function (Parameter "a")
             (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "a") []))));
      PSTBind ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) ((:) ((,) "b" Star) [])))
          (Function (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "a") [])))
             (Function
                (Function (Parameter "a")
                   (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "b") []))))
                (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "b") [])))));
      PRunST ->
        (,) ((:) ((,) "a" Star) [])
          (Function
             (Quantified "s" Star (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "a") []))))
             (Parameter "a"));
      PNewSTArray ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) []))
          (Function (Applied "Int" [])
             (Function (Parameter "a")
                (Applied "ST"
                   ((:) (Parameter "s")
                      ((:) (Applied "STArray" ((:) (Parameter "s") ((:) (Parameter "a") [])))
                         [])))));
      PReadSTArray ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) []))
          (Function (Applied "STArray" ((:) (Parameter "s") ((:) (Parameter "a") [])))
             (Function (Applied "Int" [])
                (Applied "ST" ((:) (Parameter "s") ((:) (Parameter "a") [])))));
      PWriteSTArray ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) []))
          (Function (Applied "STArray" ((:) (Parameter "s") ((:) (Parameter "a") [])))
             (Function (Applied "Int" [])
                (Function (Parameter "a")
                   (Applied "ST" ((:) (Parameter "s") ((:) (Applied "()" []) []))))));
      PLengthSTArray ->
        (,) ((:) ((,) "s" Star) ((:) ((,) "a" Star) []))
          (Function (Applied "STArray" ((:) (Parameter "s") ((:) (Parameter "a") [])))
             (Applied "ST" ((:) (Parameter "s") ((:) (Applied "Int" []) []))));
      PGetEnv ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PSetEnv ->
        (,) []
          (Function (Applied "String" [])
             (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) []))));
      PUnsetEnv ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PRunProcess ->
        (,) []
          (Function (Applied "String" [])
             (Function (Applied "String" []) (Applied "IO" ((:) (Applied "Int" []) []))));
      PListDirectory ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PDirectoryExists ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "Bool" []) [])));
      PFileDigest ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PAcquireFileLock ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "Int" []) [])));
      PReleaseFileLock ->
        (,) [] (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PProcessSupervisor ->
        (,) [] (Function (Applied "String" []) (Applied "IO" ((:) (Applied "String" []) [])));
      PAsyncScopeNew ->
        (,) []
          (Function (Applied "Int" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "AsyncScope" []) []))));
      PAsyncScopeClose ->
        (,) []
          (Function (Applied "AsyncScope" []) (Applied "IO" ((:) (Applied "()" []) [])));
      PAsyncNewCompletion ->
        (,) ((:) ((,) "a" Star) ((:) ((,) "b" Star) []))
          (Function (Applied "AsyncScope" [])
             (Function
                (Function (Applied "Completion" ((:) (Parameter "a") []))
                   (Applied "IO" ((:) (Parameter "b") [])))
                (Function (Applied "IO" ((:) (Parameter "b") []))
                   (Applied "IO" ((:) (Parameter "b") [])))));
      PAsyncResolveCompletion ->
        (,) ((:) ((,) "a" Star) [])
          (Function (Applied "Completion" ((:) (Parameter "a") []))
             (Function (Parameter "a") (Applied "IO" ((:) (Applied "Int" []) []))));
      PAsyncReadCompletion ->
        (,) ((:) ((,) "a" Star) ((:) ((,) "b" Star) []))
          (Function (Applied "Completion" ((:) (Parameter "a") []))
             (Function (Function (Parameter "a") (Applied "IO" ((:) (Parameter "b") [])))
                (Function (Applied "IO" ((:) (Parameter "b") []))
                   (Applied "IO" ((:) (Parameter "b") [])))));
      PAsyncSubscribeCompletion ->
        (,) ((:) ((,) "a" Star) [])
          (Function (Applied "Completion" ((:) (Parameter "a") []))
             (Function (Function (Parameter "a") (Applied "IO" ((:) (Applied "()" []) [])))
                (Applied "IO" ((:) (Applied "AsyncSubscription" []) []))));
      PAsyncSubscriptionStatus ->
        (,) []
          (Function (Applied "AsyncSubscription" [])
             (Applied "IO" ((:) (Applied "Int" []) [])));
      PAsyncCancelSubscription ->
        (,) []
          (Function (Applied "AsyncSubscription" [])
             (Applied "IO" ((:) (Applied "Int" []) [])));
      PAsyncStep ->
        (,) []
          (Function (Applied "AsyncScope" []) (Applied "IO" ((:) (Applied "Int" []) [])));
      PAsyncEnqueue ->
        (,) []
          (Function (Applied "AsyncScope" [])
             (Function (Applied "IO" ((:) (Applied "()" []) []))
                (Applied "IO" ((:) (Applied "AsyncSubscription" []) []))));
      PAsyncDelay ->
        (,) []
          (Function (Applied "AsyncScope" [])
             (Function (Applied "Int" [])
                (Function (Applied "IO" ((:) (Applied "()" []) []))
                   (Applied "IO" ((:) (Applied "AsyncSubscription" []) [])))));
      PAsyncWait ->
        (,) []
          (Function (Applied "AsyncScope" [])
             (Function (Applied "Int" []) (Applied "IO" ((:) (Applied "Int" []) []))));
      PTextToChars -> (,) [] (Function (Applied "String" []) charListField);
      PTextFromChars -> (,) [] (Function charListField (Applied "String" []));
      PCharCode -> (,) [] (Function (Applied "Char" []) (Applied "Int" []));
      PCharFromCode -> (,) [] (Function (Applied "Int" []) (Applied "Char" []));
      PUserError -> (,) [] (Function charListField (Applied "IOError" []));
      PIOError -> (,) ((:) ((,) "a" Star) [])
        (Function (Applied "IOError" []) (Applied "IO" ((:) (Parameter "a") [])));
      PCatchIOError -> (,) ((:) ((,) "a" Star) [])
        (Function (Applied "IO" ((:) (Parameter "a") []))
          (Function (Function (Applied "IOError" []) (Applied "IO" ((:) (Parameter "a") [])))
            (Applied "IO" ((:) (Parameter "a") []))));
      PIOErrorString -> (,) [] (Function (Applied "IOError" []) charListField);
      PEmptyCallStack -> (,) [] (Applied "MLFCallStack" []);
      PPushCallStack -> (,) [] (Function (Applied "MLFStackFrame" [])
        (Function (Applied "MLFCallStack" []) (Applied "MLFCallStack" [])));
      PPrettyCallStack -> (,) [] (Function (Applied "MLFCallStack" []) charListField);
      PIOErrorWithStack -> (,) ((:) ((,) "a" Star) [])
        (Function (Applied "IOError" [])
          (Function (Applied "MLFCallStack" []) (Applied "IO" ((:) (Parameter "a") []))))
    };
  primitiveArity :: Primitive -> Int;
  -- Runtime application asks for arity on every partial and saturated call.
  -- Avoid allocating a type signature here. PrimitiveMetadata checks every
  -- result independently against fieldArity (snd (primitiveSignature p)).
  primitiveArity p =
    case p of {
      PIOReturn -> 1;
      PIOBind -> 2;
      PPutStr -> 1;
      PPutStrLn -> 1;
      PGetLine -> 0;
      PPrintInt -> 1;
      PConcatString -> 2;
      PShowInt -> 1;
      PAddInt -> 2;
      PSubInt -> 2;
      PEqInt -> 2;
      PLtInt -> 2;
      PEqString -> 2;
      PIfThenElse -> 3;
      PMulInt -> 2;
      PQuotInt -> 2;
      PRemInt -> 2;
      PReadInt -> 1;
      PAddDouble -> 2;
      PSubDouble -> 2;
      PMulDouble -> 2;
      PDivDouble -> 2;
      PSqrtDouble -> 1;
      PEqDouble -> 2;
      PLtDouble -> 2;
      PIntToDouble -> 1;
      PFormatDouble -> 2;
      PNewIntArray -> 2;
      PReadIntArray -> 2;
      PWriteIntArray -> 3;
      PLengthIntArray -> 1;
      PNewDoubleArray -> 2;
      PReadDoubleArray -> 2;
      PWriteDoubleArray -> 3;
      PLengthDoubleArray -> 1;
      PNewByteArray -> 2;
      PReadByteArray -> 2;
      PWriteByteArray -> 3;
      PLengthByteArray -> 1;
      PByteArrayFromString -> 1;
      PPutBytes -> 3;
      PGetByteLine -> 0;
      PNewIntTable -> 0;
      PReadIntTable -> 2;
      PWriteIntTable -> 3;
      PAndInt -> 2;
      PStringLength -> 1;
      PStringCodeAt -> 2;
      PStringSlice -> 3;
      PStringFromCode -> 1;
      PCompareString -> 2;
      PReadDouble -> 1;
      PDoubleToBits -> 1;
      PDoubleFromBits -> 1;
      PSeq -> 2;
      PPanic -> 1;
      PReadFile -> 1;
      PWriteFile -> 2;
      PFileExists -> 1;
      PCanonicalPath -> 1;
      PGetArgCount -> 0;
      PGetArg -> 1;
      PPutErr -> 1;
      PExitWith -> 1;
      PGetExecutablePath -> 0;
      PGetContents -> 0;
      PSTReturn -> 1;
      PSTBind -> 2;
      PRunST -> 1;
      PNewSTArray -> 2;
      PReadSTArray -> 2;
      PWriteSTArray -> 3;
      PLengthSTArray -> 1;
      PGetEnv -> 1;
      PSetEnv -> 2;
      PUnsetEnv -> 1;
      PRunProcess -> 2;
      PListDirectory -> 1;
      PDirectoryExists -> 1;
      PFileDigest -> 1;
      PAcquireFileLock -> 1;
      PReleaseFileLock -> 1;
      PProcessSupervisor -> 1;
      PAsyncScopeNew -> 2;
      PAsyncScopeClose -> 1;
      PAsyncNewCompletion -> 3;
      PAsyncResolveCompletion -> 2;
      PAsyncReadCompletion -> 3;
      PAsyncSubscribeCompletion -> 2;
      PAsyncSubscriptionStatus -> 1;
      PAsyncCancelSubscription -> 1;
      PAsyncStep -> 1;
      PAsyncEnqueue -> 2;
      PAsyncDelay -> 3;
      PAsyncWait -> 2;
      PTextToChars -> 1;
      PTextFromChars -> 1;
      PCharCode -> 1;
      PCharFromCode -> 1;
      PUserError -> 1;
      PIOError -> 1;
      PCatchIOError -> 2;
      PIOErrorString -> 1;
      PEmptyCallStack -> 0;
      PPushCallStack -> 2;
      PPrettyCallStack -> 1;
      PIOErrorWithStack -> 2
    };
  fieldArity :: Field -> Int;
  fieldArity field =
    case field of {
      Function a b -> (1 + fieldArity b);
      _ -> 0
    };
  primitiveStrict :: Primitive -> Bool;
  primitiveStrict p =
    (((primitiveCode p >= 95) && (primitiveCode p <= 98)) ||
     (primitiveCode p == 68) ||
     S.elem eqInt (primitiveCode p)
       ((:) 6
          ((:) 7
             ((:) 8
                ((:) 9
                   ((:) 10
                      ((:) 11
                         ((:) 12
                            ((:) 14
                               ((:) 15
                                  ((:) 16
                                     ((:) 45
                                        ((:) 17
                                           ((:) 18
                                              ((:) 19
                                                 ((:) 20
                                                    ((:) 21
                                                       ((:) 22
                                                          ((:) 23
                                                             ((:) 24
                                                                ((:) 25
                                                                   ((:) 26
                                                                      ((:) 46
                                                                         ((:) 47
                                                                            ((:) 48
                                                                               ((:) 49
                                                                                  ((:) 50
                                                                                     ((:) 51
                                                                                        ((:) 52
                                                                                           ((:) 53
                                                                                              ((:)
                                                                                                 55
                                                                                                 [])))))))))))))))))))))))))))))));
  eqPrimitive :: Primitive -> Primitive -> Bool;
  eqPrimitive a b = (primitiveCode a == primitiveCode b);
  comparePrimitive :: Primitive -> Primitive -> Int;
  comparePrimitive a b = S.compareInt (primitiveCode a) (primitiveCode b)
}
