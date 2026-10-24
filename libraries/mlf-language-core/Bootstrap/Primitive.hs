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
      PAsyncWait -> 94
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
      PAsyncWait -> "asyncWait"
    };
  allPrimitives :: List Primitive;
  allPrimitives =
    Cons PIOReturn
      (Cons PIOBind
         (Cons PPutStr
            (Cons PPutStrLn
               (Cons PGetLine
                  (Cons PPrintInt
                     (Cons PConcatString
                        (Cons PShowInt
                           (Cons PAddInt
                              (Cons PSubInt
                                 (Cons PEqInt
                                    (Cons PLtInt
                                       (Cons PEqString
                                          (Cons PIfThenElse
                                             (Cons PMulInt
                                                (Cons PQuotInt
                                                   (Cons PRemInt
                                                      (Cons PReadInt
                                                         (Cons PAddDouble
                                                            (Cons PSubDouble
                                                               (Cons PMulDouble
                                                                  (Cons PDivDouble
                                                                     (Cons PSqrtDouble
                                                                        (Cons PEqDouble
                                                                           (Cons PLtDouble
                                                                              (Cons PIntToDouble
                                                                                 (Cons PFormatDouble
                                                                                    (Cons
                                                                                       PNewIntArray
                                                                                       (Cons
                                                                                          PReadIntArray
                                                                                          (Cons
                                                                                             PWriteIntArray
                                                                                             (Cons
                                                                                                PLengthIntArray
                                                                                                (Cons
                                                                                                   PNewDoubleArray
                                                                                                   (Cons
                                                                                                      PReadDoubleArray
                                                                                                      (Cons
                                                                                                         PWriteDoubleArray
                                                                                                         (Cons
                                                                                                            PLengthDoubleArray
                                                                                                            (Cons
                                                                                                               PNewByteArray
                                                                                                               (Cons
                                                                                                                  PReadByteArray
                                                                                                                  (Cons
                                                                                                                     PWriteByteArray
                                                                                                                     (Cons
                                                                                                                        PLengthByteArray
                                                                                                                        (Cons
                                                                                                                           PByteArrayFromString
                                                                                                                           (Cons
                                                                                                                              PPutBytes
                                                                                                                              (Cons
                                                                                                                                 PGetByteLine
                                                                                                                                 (Cons
                                                                                                                                    PNewIntTable
                                                                                                                                    (Cons
                                                                                                                                       PReadIntTable
                                                                                                                                       (Cons
                                                                                                                                          PWriteIntTable
                                                                                                                                          (Cons
                                                                                                                                             PAndInt
                                                                                                                                             (Cons
                                                                                                                                                PStringLength
                                                                                                                                                (Cons
                                                                                                                                                   PStringCodeAt
                                                                                                                                                   (Cons
                                                                                                                                                      PStringSlice
                                                                                                                                                      (Cons
                                                                                                                                                         PStringFromCode
                                                                                                                                                         (Cons
                                                                                                                                                            PCompareString
                                                                                                                                                            (Cons
                                                                                                                                                               PReadDouble
                                                                                                                                                               (Cons
                                                                                                                                                                  PDoubleToBits
                                                                                                                                                                  (Cons
                                                                                                                                                                     PDoubleFromBits
                                                                                                                                                                     (Cons
                                                                                                                                                                        PSeq
                                                                                                                                                                        (Cons
                                                                                                                                                                           PPanic
                                                                                                                                                                           (Cons
                                                                                                                                                                              PReadFile
                                                                                                                                                                              (Cons
                                                                                                                                                                                 PWriteFile
                                                                                                                                                                                 (Cons
                                                                                                                                                                                    PFileExists
                                                                                                                                                                                    (Cons
                                                                                                                                                                                       PCanonicalPath
                                                                                                                                                                                       (Cons
                                                                                                                                                                                          PGetArgCount
                                                                                                                                                                                          (Cons
                                                                                                                                                                                             PGetArg
                                                                                                                                                                                             (Cons
                                                                                                                                                                                                PPutErr
                                                                                                                                                                                                (Cons
                                                                                                                                                                                                   PExitWith
                                                                                                                                                                                                   (Cons
                                                                                                                                                                                                      PGetExecutablePath
                                                                                                                                                                                                      (Cons
                                                                                                                                                                                                         PGetContents
                                                                                                                                                                                                         (Cons
                                                                                                                                                                                                            PSTReturn
                                                                                                                                                                                                            (Cons
                                                                                                                                                                                                               PSTBind
                                                                                                                                                                                                               (Cons
                                                                                                                                                                                                                  PRunST
                                                                                                                                                                                                                  (Cons
                                                                                                                                                                                                                     PNewSTArray
                                                                                                                                                                                                                     (Cons
                                                                                                                                                                                                                        PReadSTArray
                                                                                                                                                                                                                        (Cons
                                                                                                                                                                                                                           PWriteSTArray
                                                                                                                                                                                                                           (Cons
                                                                                                                                                                                                                              PLengthSTArray
                                                                                                                                                                                                                              (Cons
                                                                                                                                                                                                                                 PGetEnv
                                                                                                                                                                                                                                 (Cons
                                                                                                                                                                                                                                    PSetEnv
                                                                                                                                                                                                                                    (Cons
                                                                                                                                                                                                                                       PUnsetEnv
                                                                                                                                                                                                                                       (Cons
                                                                                                                                                                                                                                          PRunProcess
                                                                                                                                                                                                                                          (Cons
                                                                                                                                                                                                                                             PListDirectory
                                                                                                                                                                                                                                             (Cons
                                                                                                                                                                                                                                                PDirectoryExists
                                                                                                                                                                                                                                                (Cons
                                                                                                                                                                                                                                                   PFileDigest
                                                                                                                                                                                                                                                   (Cons
                                                                                                                                                                                                                                                      PAcquireFileLock
                                                                                                                                                                                                                                                      (Cons
                                                                                                                                                                                                                                                         PReleaseFileLock
                                                                                                                                                                                                                                                         (Cons
                                                                                                                                                                                                                                                            PProcessSupervisor
                                                                                                                                                                                                                                                            (Cons
                                                                                                                                                                                                                                                               PAsyncScopeNew
                                                                                                                                                                                                                                                               (Cons
                                                                                                                                                                                                                                                                  PAsyncScopeClose
                                                                                                                                                                                                                                                                  (Cons
                                                                                                                                                                                                                                                                     PAsyncNewCompletion
                                                                                                                                                                                                                                                                     (Cons
                                                                                                                                                                                                                                                                        PAsyncResolveCompletion
                                                                                                                                                                                                                                                                        (Cons
                                                                                                                                                                                                                                                                           PAsyncReadCompletion
                                                                                                                                                                                                                                                                           (Cons
                                                                                                                                                                                                                                                                              PAsyncSubscribeCompletion
                                                                                                                                                                                                                                                                              (Cons
                                                                                                                                                                                                                                                                                 PAsyncSubscriptionStatus
                                                                                                                                                                                                                                                                                 (Cons
                                                                                                                                                                                                                                                                                    PAsyncCancelSubscription
                                                                                                                                                                                                                                                                                    (Cons
                                                                                                                                                                                                                                                                                       PAsyncStep
                                                                                                                                                                                                                                                                                       (Cons
                                                                                                                                                                                                                                                                                          PAsyncEnqueue
                                                                                                                                                                                                                                                                                          (Cons
                                                                                                                                                                                                                                                                                             PAsyncDelay
                                                                                                                                                                                                                                                                                             (Cons
                                                                                                                                                                                                                                                                                                PAsyncWait
                                                                                                                                                                                                                                                                                                Nil))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))));
  lookupTargetPrimitive :: String -> Maybe Primitive;
  lookupTargetPrimitive name = S.find (\p -> eqString (primitiveName p) name) allPrimitives;
  lookupPrimitive :: String -> Maybe Primitive;
  lookupPrimitive name =
    if (eqString name "return" || eqString name "pure")
    then Just PIOReturn
    else if eqString name "bind" then Just PIOBind else lookupTargetPrimitive name;
  primitiveSignature :: Primitive -> Pair (List (Pair String Kind)) Field;
  primitiveSignature p =
    case p of {
      PIOReturn ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function (Parameter "a") (Applied "IO" (Cons (Parameter "a") Nil)));
      PIOBind ->
        Pair (Cons (Pair "a" Star) (Cons (Pair "b" Star) Nil))
          (Function (Applied "IO" (Cons (Parameter "a") Nil))
             (Function (Function (Parameter "a") (Applied "IO" (Cons (Parameter "b") Nil)))
                (Applied "IO" (Cons (Parameter "b") Nil))));
      PPutStr ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PPutStrLn ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PGetLine -> Pair Nil (Applied "IO" (Cons (Applied "String" Nil) Nil));
      PPrintInt ->
        Pair Nil (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PConcatString ->
        Pair Nil
          (Function (Applied "String" Nil)
             (Function (Applied "String" Nil) (Applied "String" Nil)));
      PShowInt -> Pair Nil (Function (Applied "Int" Nil) (Applied "String" Nil));
      PAddInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PSubInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PEqInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Bool" Nil)));
      PLtInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Bool" Nil)));
      PEqString ->
        Pair Nil
          (Function (Applied "String" Nil) (Function (Applied "String" Nil) (Applied "Bool" Nil)));
      PIfThenElse ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function (Applied "Bool" Nil)
             (Function (Parameter "a") (Function (Parameter "a") (Parameter "a"))));
      PMulInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PQuotInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PRemInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PReadInt -> Pair Nil (Function (Applied "String" Nil) (Applied "Int" Nil));
      PAddDouble ->
        Pair Nil
          (Function (Applied "Double" Nil)
             (Function (Applied "Double" Nil) (Applied "Double" Nil)));
      PSubDouble ->
        Pair Nil
          (Function (Applied "Double" Nil)
             (Function (Applied "Double" Nil) (Applied "Double" Nil)));
      PMulDouble ->
        Pair Nil
          (Function (Applied "Double" Nil)
             (Function (Applied "Double" Nil) (Applied "Double" Nil)));
      PDivDouble ->
        Pair Nil
          (Function (Applied "Double" Nil)
             (Function (Applied "Double" Nil) (Applied "Double" Nil)));
      PSqrtDouble -> Pair Nil (Function (Applied "Double" Nil) (Applied "Double" Nil));
      PEqDouble ->
        Pair Nil
          (Function (Applied "Double" Nil) (Function (Applied "Double" Nil) (Applied "Bool" Nil)));
      PLtDouble ->
        Pair Nil
          (Function (Applied "Double" Nil) (Function (Applied "Double" Nil) (Applied "Bool" Nil)));
      PIntToDouble -> Pair Nil (Function (Applied "Int" Nil) (Applied "Double" Nil));
      PFormatDouble ->
        Pair Nil
          (Function (Applied "Int" Nil) (Function (Applied "Double" Nil) (Applied "String" Nil)));
      PNewIntArray ->
        Pair Nil
          (Function (Applied "Int" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "IntArray" Nil) Nil))));
      PReadIntArray ->
        Pair Nil
          (Function (Applied "IntArray" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil))));
      PWriteIntArray ->
        Pair Nil
          (Function (Applied "IntArray" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))));
      PLengthIntArray ->
        Pair Nil (Function (Applied "IntArray" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PNewDoubleArray ->
        Pair Nil
          (Function (Applied "Int" Nil)
             (Function (Applied "Double" Nil)
                (Applied "IO" (Cons (Applied "DoubleArray" Nil) Nil))));
      PReadDoubleArray ->
        Pair Nil
          (Function (Applied "DoubleArray" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Double" Nil) Nil))));
      PWriteDoubleArray ->
        Pair Nil
          (Function (Applied "DoubleArray" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "Double" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))));
      PLengthDoubleArray ->
        Pair Nil
          (Function (Applied "DoubleArray" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PNewByteArray ->
        Pair Nil
          (Function (Applied "Int" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "ByteArray" Nil) Nil))));
      PReadByteArray ->
        Pair Nil
          (Function (Applied "ByteArray" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil))));
      PWriteByteArray ->
        Pair Nil
          (Function (Applied "ByteArray" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))));
      PLengthByteArray ->
        Pair Nil (Function (Applied "ByteArray" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PByteArrayFromString ->
        Pair Nil
          (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "ByteArray" Nil) Nil)));
      PPutBytes ->
        Pair Nil
          (Function (Applied "ByteArray" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))));
      PGetByteLine -> Pair Nil (Applied "IO" (Cons (Applied "ByteArray" Nil) Nil));
      PNewIntTable -> Pair Nil (Applied "IO" (Cons (Applied "IntTable" Nil) Nil));
      PReadIntTable ->
        Pair Nil
          (Function (Applied "IntTable" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil))));
      PWriteIntTable ->
        Pair Nil
          (Function (Applied "IntTable" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))));
      PAndInt ->
        Pair Nil (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PStringLength -> Pair Nil (Function (Applied "String" Nil) (Applied "Int" Nil));
      PStringCodeAt ->
        Pair Nil
          (Function (Applied "String" Nil) (Function (Applied "Int" Nil) (Applied "Int" Nil)));
      PStringSlice ->
        Pair Nil
          (Function (Applied "String" Nil)
             (Function (Applied "Int" Nil) (Function (Applied "Int" Nil) (Applied "String" Nil))));
      PStringFromCode -> Pair Nil (Function (Applied "Int" Nil) (Applied "String" Nil));
      PCompareString ->
        Pair Nil
          (Function (Applied "String" Nil) (Function (Applied "String" Nil) (Applied "Int" Nil)));
      PReadDouble -> Pair Nil (Function (Applied "String" Nil) (Applied "Double" Nil));
      PDoubleToBits -> Pair Nil (Function (Applied "Double" Nil) (Applied "Int" Nil));
      PDoubleFromBits -> Pair Nil (Function (Applied "Int" Nil) (Applied "Double" Nil));
      PSeq ->
        Pair (Cons (Pair "a" Star) (Cons (Pair "b" Star) Nil))
          (Function (Parameter "a") (Function (Parameter "b") (Parameter "b")));
      PPanic -> Pair (Cons (Pair "a" Star) Nil) (Function (Applied "String" Nil) (Parameter "a"));
      PReadFile ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PWriteFile ->
        Pair Nil
          (Function (Applied "String" Nil)
             (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil))));
      PFileExists ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Bool" Nil) Nil)));
      PCanonicalPath ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PGetArgCount -> Pair Nil (Applied "IO" (Cons (Applied "Int" Nil) Nil));
      PGetArg ->
        Pair Nil (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PPutErr ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PExitWith ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function (Applied "Int" Nil) (Applied "IO" (Cons (Parameter "a") Nil)));
      PGetExecutablePath -> Pair Nil (Applied "IO" (Cons (Applied "String" Nil) Nil));
      PGetContents -> Pair Nil (Applied "IO" (Cons (Applied "String" Nil) Nil));
      PSTReturn ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) Nil))
          (Function (Parameter "a")
             (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "a") Nil))));
      PSTBind ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) (Cons (Pair "b" Star) Nil)))
          (Function (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))
             (Function
                (Function (Parameter "a")
                   (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "b") Nil))))
                (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "b") Nil)))));
      PRunST ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function
             (Quantified "s" Star (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "a") Nil))))
             (Parameter "a"));
      PNewSTArray ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) Nil))
          (Function (Applied "Int" Nil)
             (Function (Parameter "a")
                (Applied "ST"
                   (Cons (Parameter "s")
                      (Cons (Applied "STArray" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))
                         Nil)))));
      PReadSTArray ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) Nil))
          (Function (Applied "STArray" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))
             (Function (Applied "Int" Nil)
                (Applied "ST" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))));
      PWriteSTArray ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) Nil))
          (Function (Applied "STArray" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))
             (Function (Applied "Int" Nil)
                (Function (Parameter "a")
                   (Applied "ST" (Cons (Parameter "s") (Cons (Applied "Unit" Nil) Nil))))));
      PLengthSTArray ->
        Pair (Cons (Pair "s" Star) (Cons (Pair "a" Star) Nil))
          (Function (Applied "STArray" (Cons (Parameter "s") (Cons (Parameter "a") Nil)))
             (Applied "ST" (Cons (Parameter "s") (Cons (Applied "Int" Nil) Nil))));
      PGetEnv ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PSetEnv ->
        Pair Nil
          (Function (Applied "String" Nil)
             (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil))));
      PUnsetEnv ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PRunProcess ->
        Pair Nil
          (Function (Applied "String" Nil)
             (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil))));
      PListDirectory ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PDirectoryExists ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Bool" Nil) Nil)));
      PFileDigest ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PAcquireFileLock ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PReleaseFileLock ->
        Pair Nil (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PProcessSupervisor ->
        Pair Nil (Function (Applied "String" Nil) (Applied "IO" (Cons (Applied "String" Nil) Nil)));
      PAsyncScopeNew ->
        Pair Nil
          (Function (Applied "Int" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "AsyncScope" Nil) Nil))));
      PAsyncScopeClose ->
        Pair Nil
          (Function (Applied "AsyncScope" Nil) (Applied "IO" (Cons (Applied "Unit" Nil) Nil)));
      PAsyncNewCompletion ->
        Pair (Cons (Pair "a" Star) (Cons (Pair "b" Star) Nil))
          (Function (Applied "AsyncScope" Nil)
             (Function
                (Function (Applied "Completion" (Cons (Parameter "a") Nil))
                   (Applied "IO" (Cons (Parameter "b") Nil)))
                (Function (Applied "IO" (Cons (Parameter "b") Nil))
                   (Applied "IO" (Cons (Parameter "b") Nil)))));
      PAsyncResolveCompletion ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function (Applied "Completion" (Cons (Parameter "a") Nil))
             (Function (Parameter "a") (Applied "IO" (Cons (Applied "Int" Nil) Nil))));
      PAsyncReadCompletion ->
        Pair (Cons (Pair "a" Star) (Cons (Pair "b" Star) Nil))
          (Function (Applied "Completion" (Cons (Parameter "a") Nil))
             (Function (Function (Parameter "a") (Applied "IO" (Cons (Parameter "b") Nil)))
                (Function (Applied "IO" (Cons (Parameter "b") Nil))
                   (Applied "IO" (Cons (Parameter "b") Nil)))));
      PAsyncSubscribeCompletion ->
        Pair (Cons (Pair "a" Star) Nil)
          (Function (Applied "Completion" (Cons (Parameter "a") Nil))
             (Function (Function (Parameter "a") (Applied "IO" (Cons (Applied "Unit" Nil) Nil)))
                (Applied "IO" (Cons (Applied "AsyncSubscription" Nil) Nil))));
      PAsyncSubscriptionStatus ->
        Pair Nil
          (Function (Applied "AsyncSubscription" Nil)
             (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PAsyncCancelSubscription ->
        Pair Nil
          (Function (Applied "AsyncSubscription" Nil)
             (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PAsyncStep ->
        Pair Nil
          (Function (Applied "AsyncScope" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil)));
      PAsyncEnqueue ->
        Pair Nil
          (Function (Applied "AsyncScope" Nil)
             (Function (Applied "IO" (Cons (Applied "Unit" Nil) Nil))
                (Applied "IO" (Cons (Applied "AsyncSubscription" Nil) Nil))));
      PAsyncDelay ->
        Pair Nil
          (Function (Applied "AsyncScope" Nil)
             (Function (Applied "Int" Nil)
                (Function (Applied "IO" (Cons (Applied "Unit" Nil) Nil))
                   (Applied "IO" (Cons (Applied "AsyncSubscription" Nil) Nil)))));
      PAsyncWait ->
        Pair Nil
          (Function (Applied "AsyncScope" Nil)
             (Function (Applied "Int" Nil) (Applied "IO" (Cons (Applied "Int" Nil) Nil))))
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
      PAsyncWait -> 2
    };
  fieldArity :: Field -> Int;
  fieldArity field =
    case field of {
      Function a b -> (1 + fieldArity b);
      _ -> 0
    };
  primitiveStrict :: Primitive -> Bool;
  primitiveStrict p =
    ((primitiveCode p == 68) ||
     S.elem eqInt (primitiveCode p)
       (Cons 6
          (Cons 7
             (Cons 8
                (Cons 9
                   (Cons 10
                      (Cons 11
                         (Cons 12
                            (Cons 14
                               (Cons 15
                                  (Cons 16
                                     (Cons 45
                                        (Cons 17
                                           (Cons 18
                                              (Cons 19
                                                 (Cons 20
                                                    (Cons 21
                                                       (Cons 22
                                                          (Cons 23
                                                             (Cons 24
                                                                (Cons 25
                                                                   (Cons 26
                                                                      (Cons 46
                                                                         (Cons 47
                                                                            (Cons 48
                                                                               (Cons 49
                                                                                  (Cons 50
                                                                                     (Cons 51
                                                                                        (Cons 52
                                                                                           (Cons 53
                                                                                              (Cons
                                                                                                 55
                                                                                                 Nil)))))))))))))))))))))))))))))));
  eqPrimitive :: Primitive -> Primitive -> Bool;
  eqPrimitive a b = (primitiveCode a == primitiveCode b);
  comparePrimitive :: Primitive -> Primitive -> Int;
  comparePrimitive a b = S.compareInt (primitiveCode a) (primitiveCode b)
}
