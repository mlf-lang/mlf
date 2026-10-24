-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ProcessHost where {
  import MLF.Primitive;
  import Bootstrap.Types;
  -- The released seed uses bootstrap/seed-compat/Bootstrap/ProcessHost.emlf
  -- only while compiling stage 1. Stage 2 uses this real runtime bridge.
  request :: String -> IO String;
  request = processSupervisor;
  begin :: IO String;
  begin =
    ioBind (request "MLF-PROCESS-1\0checkpoint\0")
      (\reply -> ioReturn (stringSlice reply 2 (stringLength reply - 3)));
  -- Each interpreted entry owns only scopes opened since its checkpoint.
  -- A successful entry joins leaked raw scopes; an error cancels and joins.
  -- Existing outer native/interpreted scopes are left intact.
  finish :: forall a. String -> Either String a -> IO (Either String a);
  finish checkpoint result =
    do {
      let {
        mode =
          case result of {
            Right _ -> "0";
            Left _ -> "1"
          }
      };
      reply <- request ("MLF-PROCESS-1\0finish\0" ++ (checkpoint ++ ("\0" ++ (mode ++ "\0"))));
      ioReturn
        (if eqString reply "0\0"
         then result
         else case result of {
                Left message -> Left (message ++ "; process scope cleanup failed");
                Right _ -> Left "process scope cleanup failed"
              })
    };
  -- Metadata-only timer bridge; user values and callbacks stay in the IO store.
  clock :: IO Int;
  clock =
    ioBind (request "MLF-PROCESS-1\0clock\0")
      (\reply ->
         if ((stringLength reply >= 4) && eqString (stringSlice reply 0 2) "0\0")
         then ioReturn (readInt (stringSlice reply 2 (stringLength reply - 3)))
         else panic "monotonic clock requires the stage-2 compiler");
  pause :: Int -> IO Unit;
  pause milliseconds =
    ioBind (request ("MLF-PROCESS-1\0pause\0" ++ (showInt milliseconds ++ "\0")))
      (\reply -> if eqString reply "0\0" then ioReturn Unit else panic "invalid monotonic pause")
}
