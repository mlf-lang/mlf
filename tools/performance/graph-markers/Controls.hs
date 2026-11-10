module Main where
import GraphProgress
import Prelude
import Control.Concurrent (threadDelay)
import Control.Exception (bracket)
import Control.Monad (unless)
import Data.IORef (readIORef)

check b label = unless b (error label)
stages = ["scc.begin","scc.prepared-record.enter","scc.scope-inventory.enter",
          "scc.raw-infer.await-whnf","scc.raw-record.enter","scc.finish.enter","scc.finished.fresh"]
closed start s = foldl (\v (t,l)->advance t l v) s (zip [start,start+10..] stages)
main = do
  let s=closed 100 zero
  check (started s==1 && fresh s==1 && totalGroups s==Nothing && openWindow s==Nothing) "closed SCC"
  check (closedTotals s==[Total name 10 1 | Total name _ _<-zeroTotals]) "closed windows"
  let partial=advance 200 "scc.begin" s
  check (currentIdentity partial==Nothing && totalGroups partial==Nothing) "clear identity"
  let opened=advance 210 "scc.prepared-record.enter" partial
  check (openWindow opened==Just ("prepared_record",210)) "open window"
  let failed=advance 220 "control.error" opened
  check (openWindow failed==openWindow opened && closedTotals failed==closedTotals s &&
         fresh failed==1 && reused failed==0 && totalGroups failed==Nothing) "failed group remains partial"
  let reusedState=foldl (\v (t,l)->advance t l v) zero
        (zip [100,110..] (take 6 stages ++ ["scc.finished.reused"]))
  check (fresh reusedState==0 && reused reusedState==1 && openWindow reusedState==Nothing &&
         closedTotals reusedState==closedTotals s) "reused success windows"
  check ("\"age_ns\":20" `contains` snapshotJSON "control" 230 opened) "open age"
  let varied v n=foldl (\s (t,l)->advance t l s) v
        (zip [100*n,100*n+1,100*n+2,100*n+3,100*n+4,100*n+5,100*n+5+n] stages)
      many=foldl varied zero [1..7]
  check (length (slowest many)==5 && fresh many==7) "bounded top five"
  check ([ordinal | Completed ordinal _ _ _<-slowest many]==[7,6,5,4,3]) "top five ordering"
  forceState many `seq` pure ()
  let done=advance 800 "groups.complete" many
  check (totalGroups done==Just 7) "natural total"
  check (jsonString "a\n\"\\"=="\"a\\u000a\\\"\\\\\"") "JSON escaping"
  bracket startReporting stopReporting $ \_ -> do
    event "scc.begin"
    identity 8 ([(i, replicate 96 'x' ++ error "unbounded name tail") | i<-[1..4]] ++ error "unbounded member tail")
    a<-readIORef state
    case currentIdentity a of
      Just (Identity n pairs)->check (n==8 && length pairs==4 && all ((==96).length.snd) pairs) "bounded identity"
      _ -> error "missing identity"
    event "scc.prepared-record.enter"
    threadDelay 2100000
    event "scc.scope-inventory.enter"
    event "scc.raw-infer.await-whnf"
    event "scc.raw-record.enter"
    event "scc.finish.enter"
    event "scc.finished.fresh"
    completed<-readIORef state
    check (currentIdentity completed==Nothing) "clear completed identity"
    event "scc.begin"
    a<-readIORef state
    check (currentIdentity a==Nothing && lastCompleted a/=Nothing) "reset and last complete"
    snapshot "identity-cleared"
  putStrLn "PASS graph marker controls"
  where contains needle haystack = any (prefix needle) (tails haystack)
        prefix [] _ = True
        prefix _ [] = False
        prefix (a:as) (b:bs) = a==b && prefix as bs
        tails [] = [[]]
        tails xs@(_:rest) = xs:tails rest
