{-# LANGUAGE BangPatterns #-}
-- Diagnostic only. The compiler is run serially, and every root is forced to
-- Either WHNF before its observation closes. No production owner imports this.
module KindCounters (root, visit, report) where
import Prelude
import Control.Exception (evaluate, finally)
import Data.IORef
import qualified Data.IntSet as Set
import System.IO (hPutStrLn, stderr)
import System.IO.Unsafe (unsafePerformIO)
import Data.Int (Int64)

data Local = Local !Int !(Set.IntSet)
data Totals = Totals !Int !Int !Int !Int !Int
{-# NOINLINE active #-}
active :: IORef [Local]
active = unsafePerformIO (newIORef [])
{-# NOINLINE totals #-}
totals :: IORef Totals
totals = unsafePerformIO (newIORef (Totals 0 0 0 0 0))

{-# NOINLINE root #-}
root :: a -> a
root value = unsafePerformIO $ do
  modifyIORef' active (Local 0 Set.empty :)
  evaluate value `finally` do
    current <- readIORef active
    case current of
      [] -> error "kind diagnostic root stack underflow"
      Local visits identities : rest -> do
        writeIORef active rest
        let !unique = Set.size identities
        modifyIORef' totals $ \(Totals roots count distinct maximum repeated) ->
          Totals (roots+1) (count+visits) (distinct+unique) (max maximum visits)
            (repeated + if visits > unique then 1 else 0)

{-# NOINLINE visit #-}
visit :: Int64 -> a -> a
visit identity value = unsafePerformIO $ do
  modifyIORef' active $ \current -> case current of
    [] -> error "kind diagnostic visit outside root"
    Local count seen : rest -> Local (count+1) (Set.insert (fromIntegral identity) seen) : rest
  pure value

report :: IO ()
report = do
  Totals roots visits unique maximum repeated <- readIORef totals
  hPutStrLn stderr ("KIND_DIAGNOSTIC {\"roots\":" ++ show roots ++
    ",\"recursive_visits\":" ++ show visits ++ ",\"unique_variable_roots\":" ++ show unique ++
    ",\"max_visits_per_root\":" ++ show maximum ++ ",\"roots_with_repeats\":" ++ show repeated ++ "}")
