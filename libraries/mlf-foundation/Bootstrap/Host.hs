-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Host where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  -- Optional, exclusive wall-clock accounting for nested IO phases. Callers
  -- choose the labels and explicitly demand lazy pure results inside a phase.
  -- No clock, traversal or output is performed when the handle is Nothing.
  data PhaseProfile = PhaseProfile ([] String) IntArray;
  phaseClock = do {
    reply <- processSupervisor "MLF-PROCESS-1\0clock\0";
    if stringLength reply >= 4 && eqString (stringSlice reply 0 2) "0\0"
      then ioReturn (readInt (stringSlice reply 2 (stringLength reply - 3)))
      else panic "phase profiling clock unavailable"
  };
  newPhaseProfile labels = do {
    counters <- newIntArray (length labels + 2) 0;
    writeIntArray counters (length labels) (0 - 1);
    now <- phaseClock;
    writeIntArray counters (length labels + 1) now;
    ioReturn (Just (PhaseProfile labels counters))
  };
  switchPhase (PhaseProfile labels counters) next = do {
    now <- phaseClock;
    let { count = length labels };
    previous <- readIntArray counters count;
    start <- readIntArray counters (count + 1);
    if previous < 0 then ioReturn () else do {
      elapsed <- readIntArray counters previous;
      writeIntArray counters previous (elapsed + now - start)
    };
    writeIntArray counters count next;
    writeIntArray counters (count + 1) now;
    ioReturn previous
  };
  phaseIndex name labels index = case labels of {
    [] -> panic ("unknown profile phase: " ++ name);
    (:) label rest -> if eqString name label then index else phaseIndex name rest (index + 1)
  };
  phaseIO profile name action = case profile of {
    Nothing -> action;
    Just handle@(PhaseProfile labels _) -> do {
      previous <- switchPhase handle (phaseIndex name labels 0);
      result <- action;
      seq result (ioReturn ());
      _ <- switchPhase handle previous;
      ioReturn result
    }
  };
  phaseValue profile name demand value = case profile of {
    Nothing -> ioReturn value;
    Just _ -> phaseIO profile name (seq (demand value) (ioReturn value))
  };
  phaseEither demand value = case value of {
    Left message -> seq (stringLength message) ();
    Right result -> seq (demand result) ()
  };
  writePhaseProfile path profile = case profile of {
    Nothing -> ioReturn ();
    Just (PhaseProfile labels counters) -> do {
      values <- mapM (readIntArray counters) (range 0 (length labels - 1));
      writeFile path ("{" ++ intercalate "," (map (\((,) label value) ->
        "\"" ++ label ++ "\":" ++ showInt value) (zip labels values)) ++ "}\n")
    }
  };
  separator :: Int -> Bool;
  separator code = ((code == 47) || (code == 92));
  driveRoot path =
    ((stringLength path >= 3) &&
     ((((stringCodeAt path 0 >= 65) && (stringCodeAt path 0 <= 90)) ||
       ((stringCodeAt path 0 >= 97) && (stringCodeAt path 0 <= 122))) &&
      ((stringCodeAt path 1 == 58) && separator (stringCodeAt path 2))));
  uncRoot path =
    ((stringLength path >= 2) &&
     (((stringCodeAt path 0 == 92) && (stringCodeAt path 1 == 92)) ||
      ((stringCodeAt path 0 == 47) && (stringCodeAt path 1 == 47))));
  absolutePath path =
    (((stringLength path > 0) && (stringCodeAt path 0 == 47)) || (driveRoot path || uncRoot path));
  lastSeparator :: String -> Int -> Int;
  lastSeparator path i =
    if (i < 0)
    then (-1)
    else if separator (stringCodeAt path i) then i else lastSeparator path (i - 1);
  parentDirectory path =
    let {
      end = lastSeparator path (stringLength path - 1)
    } in
    if (end < 0)
    then "."
    else if (end == 0)
         then stringSlice path 0 1
         else if ((end == 2) && driveRoot path)
              then stringSlice path 0 3
              else stringSlice path 0 end;
  isWindows =
    do {
      system <- getEnv "OS";
      executable <- getExecutablePath;
      ioReturn (eqString system "Windows_NT" || (driveRoot executable || uncRoot executable))
    };
  windowsHost =
    do {
      selected <- getEnv "MLF_WINDOWS_HOST";
      executable <- getExecutablePath;
      ioReturn
        (if eqString selected "" then (parentDirectory executable ++ "/mlf-host.exe") else selected)
    };
  -- Keep argv structured on both platforms. The compiler's query cache and the
  -- package manager use the same native filesystem helper on Windows.
  argumentsFor windows host argv =
    if not windows
    then argv
    else case argv of {
           (:) command rest ->
             let {
               operation =
                 lookup eqString command
                   ((:) ((,) "/bin/mkdir" "mkdir")
                      ((:) ((,) "/bin/cp" "copy")
                         ((:) ((,) "/bin/mv" "move")
                            ((:) ((,) "/bin/rm" "remove")
                               ((:) ((,) "/bin/test" "test")
                                  ((:) ((,) "/bin/ln" "link")
                                     ((:) ((,) "/usr/bin/uname" "uname")
                                        ((:) ((,) "uname" "uname")
                                           ((:) ((,) "mktemp" "mktemp") [])))))))))
             } in
             case operation of {
               Nothing -> argv;
               Just name -> (:) host ((:) name rest)
             };
           [] -> []
         };
  hostArguments argv =
    do {
      windows <- isWindows;
      if not windows
      then ioReturn argv
      else do {
             host <- windowsHost;
             ioReturn (argumentsFor True host argv)
           }
    }
}
