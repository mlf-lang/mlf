{-# LANGUAGE ForeignFunctionInterface #-}
module Main where
import qualified MLF.Primitive as M
import qualified MLF.Host.Base as B
import Control.Monad (replicateM_)
import Data.Int (Int64)
import Foreign.C.Types (CInt(..))
import System.Environment (getArgs)
foreign import ccall unsafe "mlf_spawn_stat" stat :: CInt -> IO Int64
foreign import ccall unsafe "mlf_spawn_fd_count" fds :: IO CInt
foreign import ccall unsafe "getpgrp" group :: IO CInt
main :: IO ()
main = do
  [child] <- getArgs
  current <- group
  let text = B.literal
      action cwd mode = do
        let fields = ["3","","","",child,mode,show current]
        code <- M.runProcess (text cwd) (text (concatMap (++"\0") fields))
        if code == 0 then pure () else error ("child state mismatch: " ++ show code)
  M.setEnv (text "MLF_SPAWN_SENTINEL") (text "inherited λ environment")
  M.unsetEnv (text "MLF_BUILD_SCOPE")
  action "" "own"
  before <- fds
  replicateM_ 9 (action "" "own")
  M.setEnv (text "MLF_BUILD_SCOPE") (text (show current))
  replicateM_ 9 (action "" "inherit")
  M.setEnv (text "MLF_BUILD_SCOPE") (text (show (current+1)))
  replicateM_ 9 (action "" "own")
  M.unsetEnv (text "MLF_BUILD_SCOPE")
  action "." "own"
  missing <- M.runProcess (text "") (text ("3\0\0\0\0" ++ child ++ ".missing\0"))
  if missing==127 then pure () else error "missing executable status"
  after <- fds
  values <- mapM stat [0..6]
  print (before,after,values)
