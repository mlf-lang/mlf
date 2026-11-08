-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module QueryGraphBoundary where {
 import MLF.Primitive;
 import Bootstrap.Types;
 import Bootstrap.Std;
 import qualified Diagnostic.ReferenceQueryGraph as Q;
 import qualified Diagnostic.CandidateQueryGraph as P;
 import qualified Bootstrap.Map as M;
 import qualified Bootstrap.Bitstream as W;
 import qualified Bootstrap.Separate as Separate;
 import qualified Bootstrap.ArtifactStorage as Storage;
 require yes message = if yes then ioReturn () else panic message;
 forceValue value = case value of {
  W.VText text -> seq (stringLength text) 1;
  W.VInt n -> seq n 1;
  W.VBits n -> seq n 1;
  W.VNode tag children -> seq tag (foldlStrict (\total child -> total + forceValue child) 1 children)
 };
 tupleNodes = M.map (\(Q.QueryNode k h es p) -> P.QueryNode k h es p);
 forceNodeFields k h edges payload = stringLength k + stringLength h +
   foldlStrict (\total ((,) name digest) -> total + stringLength name + stringLength digest) 0 edges +
   (case payload of { Nothing -> 0; Just address -> stringLength address });
 forceReferenceNodes nodes = foldlStrict
   (\total (Q.QueryNode k h edges payload) -> total + forceNodeFields k h edges payload) 0 (M.elems nodes);
 forceCandidateNodes nodes = foldlStrict
   (\total (P.QueryNode k h edges payload) -> total + forceNodeFields k h edges payload) 0 (M.elems nodes);
 checkError expected config nodes = case (,) (Q.encodeIndex config nodes)
   (P.encodeIndex config (tupleNodes nodes)) of {
  (,) (Left old) (Left candidate) -> require
   (eqString old expected && eqString candidate expected) "error order/message changed";
  _ -> panic "negative index unexpectedly returned"
 };
 controls config nodes = do {
  let { zeros = concatStringList (replicate 64 "0"); bad = concatStringList (replicate 64 "g");
        add key digest reads = M.insert compareString key (Q.QueryNode key digest reads Nothing) nodes };
  checkError "empty query graph configuration" "" nodes;
  checkError "malformed module artifact framing" config (add "broken" zeros []);
  checkError "noncanonical query identity" config (add "07:Binding1:x" zeros []);
  checkError "unknown query kind" config (add (Q.key "Bogus" "x") zeros []);
  checkError "invalid query group members" config (add (Q.key "Scope" (Separate.pack ["x","x"])) zeros []);
  checkError "invalid query graph digest" config (add (Q.key "Binding" "fresh-negative") bad []);
  checkError "unknown snapshot identity" config (add (Q.key "Binding" "fresh-negative") zeros [(,) "absent-query-key" zeros]);
  checkError "malformed module artifact framing" "" (add "broken" bad []);
  checkError "invalid query group members" "" (add (Q.key "Scope" (Separate.pack ["x","x"])) bad []);
  checkError "empty snapshot identity" "" (add (Q.key "Binding" "") bad []);
  checkError "empty query graph configuration" "" (add (Q.key "Binding" "fresh-negative") bad []);
  checkError "invalid query graph digest" config (add (Q.key "Binding" "fresh-negative") bad [(,) "absent-query-key" zeros]);
  ioReturn ()
 };
 main :: IO ();
 main = do {
  input <- getEnv "BENCH_INPUT"; configFile <- getEnv "BENCH_CONFIG";
  output <- getEnv "BENCH_OUTPUT"; mode <- getEnv "BENCH_MODE";
  require (elem eqString mode ["reference","candidate","controls"]) "unknown mode";
  stats <- Q.profile; before <- Q.clock stats; config <- readFile configFile;
  loaded <- Storage.readRaw input;
  case loaded of { Left e -> panic e; Right bytes -> do {
   original <- byteArrayDigest bytes; decoded <- W.decodeGraph W.defaultLimits 6 bytes;
   case decoded of { Left e -> panic e; Right graph -> case Q.admitIndex config graph of {
    Left e -> panic e;
    Right ((,) nodes canonical) -> do {
     require canonical "input not canonical";
     let { tuple = tupleNodes nodes; count = M.size nodes; prepared = M.size tuple };
     require (count > 0 && prepared > 0) "empty nodes";
     -- Materialize both map spines and every node before either timed encoder.
     -- M.size alone only forces the root's cached size, leaving conversion lazy.
     let { referenceForced = forceReferenceNodes nodes; candidateForced = forceCandidateNodes tuple };
     require (referenceForced > 0 && referenceForced == candidateForced) "node preparation changed";
     started <- Q.clock stats;
     value <- if eqString mode "controls" then do { controls config nodes; ioReturn (W.VInt count) }
      else case (if eqString mode "candidate" then P.encodeIndex config tuple else Q.encodeIndex config nodes) of {
       Left e -> panic e; Right value -> do {
        let { forced = forceValue value }; require (forced > 0) "index result unforced"; ioReturn value
       }
      };
     ended <- Q.clock stats;
     result <- if eqString mode "controls" then ioReturn bytes else do {
      encoded <- Q.encodeHashed value;
      case encoded of { Left e -> panic e; Right ((,) digest result) -> do {
       require (eqString digest original) "boundary digest changed"; ioReturn result
      } }
     };
     same <- Storage.sameBytes bytes result; require same "boundary raw bytes changed";
     error <- writeByteFileOrError output result; require (eqString error "") error;
     putStrLn ("PREP_MS " ++ showInt (started-before));
     putStrLn ("TIMED_MS " ++ showInt (ended-started));
     putStrLn ("OK " ++ mode ++ " " ++ showInt count ++ " " ++ original)
    }
   } }
  } }
 }
}
