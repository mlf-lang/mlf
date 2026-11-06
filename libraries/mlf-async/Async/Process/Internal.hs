-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Async.Process.Internal where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  -- Trusted monomorphic transport, not a task-ID-to-typed-value conversion.
  -- All requests are interpreted by the in-process supervisor on this thread.
  pack :: [] String -> String;
  pack fields = L.concatMapString (\field -> (field ++ stringFromCode 0)) fields;
  unpackAt :: String -> Int -> Int -> [] String;
  unpackAt text start at =
    if (at >= stringLength text)
    then []
    else if (stringCodeAt text at == 0)
         then (:) (stringSlice text start (at - start)) (unpackAt text (at + 1) (at + 1))
         else unpackAt text start (at + 1);
  unpack :: String -> [] String;
  unpack text = unpackAt text 0 0;
  hasNulAt :: String -> Int -> Bool;
  hasNulAt text at =
    if (at >= stringLength text)
    then False
    else if (stringCodeAt text at == 0) then True else hasNulAt text (at + 1);
  validField :: String -> Bool;
  validField text = L.not (hasNulAt text 0);
  request :: [] String -> IO (Either ((,) Int String) ([] String));
  request fields =
    if L.not (L.all validField fields)
    then ioReturn (Left ((,) 1 "process fields cannot contain NUL"))
    else do {
           reply <- processSupervisor (pack ((:) "MLF-PROCESS-1" fields));
           ioReturn
             (let {
                matchValueShared1 = unpack reply
              } in
              case matchValueShared1 of {
                (:) matchValueShared2 matchValueShared3 ->
                  if MLF.Primitive.eqString matchValueShared2 "0"
                  then let {
                         values = matchValueShared3
                       } in
                       Right values
                  else case matchValueShared3 of {
                         (:) matchValueShared4 matchValueShared5 ->
                           case matchValueShared5 of {
                             [] ->
                               let {
                                 message = matchValueShared4
                               } in
                               let {
                                 code = matchValueShared2
                               } in
                               Left ((,) (readInt code) message);
                             _ -> Left ((,) 12 "invalid process supervisor response")
                           };
                         _ -> Left ((,) 12 "invalid process supervisor response")
                       };
                _ -> Left ((,) 12 "invalid process supervisor response")
              })
         }
}
