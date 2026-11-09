{-# LANGUAGE ForeignFunctionInterface #-}
module Main where
import qualified MLF.Primitive as M
import qualified MLF.Host.Base as B
import Control.Monad (replicateM_)
import Data.Int (Int64)
import Foreign.C.Types (CInt(..))
foreign import ccall unsafe "mlf_ready_stat" stat :: CInt -> IO Int64
foreign import ccall unsafe "mlf_ready_fd_count" fds :: IO CInt
main :: IO ()
main = do
  let action = do
        code <- M.runProcess (B.literal "") (B.literal "3\0\0\0\0/usr/bin/true\0")
        if code == 0 then pure () else error "unexpected process exit"
  action
  before <- fds
  replicateM_ 32 action
  after <- fds
  values <- mapM stat [0..4]
  print (before,after,values)
