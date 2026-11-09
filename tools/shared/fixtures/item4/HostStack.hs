{-# LANGUAGE ScopedTypeVariables, FlexibleContexts #-}
module Main where
import qualified MLF.Primitive as M
import qualified Control.Exception as E
import qualified System.IO.Error as I
import System.Environment
import Control.Monad(unless)
assert p = unless p (error "assertion failed")
t = M.textFromChars
frame n l = M.MLFStackFrame (t n) (t "pkg") (t "Mod") (t "file.hs") l 2 (l+2) 9
stack = M.mlfPushCallStack (frame "inner" 10) (M.mlfPushCallStack (frame "outer" 20) M.mlfEmptyCallStack)
raise s = M.mlfIOErrorWithStack (M.userError s) stack
named :: M.HasCallStack => M.CallStack
named = M.callStack
main = do
 args <- getArgs
 case args of
  ["direct"] -> raise "source"
  ["nested"] -> M.catchIOError (M.catchIOError (raise "a") (\_ -> raise "b")) (\_ -> raise "c")
  ["active"] -> M.catchIOError (raise "a") (\_ -> M.catchIOError (raise "b") (\_ -> raise "c"))
  ["public"] -> M.ioError (M.userError "public")
  _ -> do
   let unicode = M.MLFStackFrame (t "函数λ😀") (t "包") (t "模") (t "源.hs") 7 8 9 10
   assert (M.mlfPrettyCallStack (M.mlfPushCallStack unicode M.mlfEmptyCallStack) == "CallStack (from HasCallStack):\n  函数λ😀, called at 源.hs:7:8 in 包:模")
   surrogate <- M.catchIOError (M.mlfIOErrorWithStack (M.userError [M.charFromCode 55296]) M.mlfEmptyCallStack) (pure . M.ioeGetErrorString)
   assert (surrogate == [M.charFromCode 55296])
   assert (M.mlfPrettyCallStack M.mlfEmptyCallStack == "")
   assert (M.mlfPrettyCallStack stack == "CallStack (from HasCallStack):\n  inner, called at file.hs:10:2 in pkg:Mod\n  outer, called at file.hs:20:2 in pkg:Mod")
   assert (take 5 (M.prettyCallStack named) == "CallS")
   let lazy = M.mlfPushCallStack (M.MLFStackFrame undefined undefined undefined undefined undefined undefined undefined undefined) M.mlfEmptyCallStack
   assert (take (length "CallStack (from HasCallStack):\n  ") (M.mlfPrettyCallStack lazy) == "CallStack (from HasCallStack):\n  ")
   _ <- E.evaluate (M.mlfIOErrorWithStack undefined undefined :: IO ())
   _ <- M.catchIOError (M.mlfIOErrorWithStack (M.userError undefined) undefined) (\_ -> pure ())
   caught <- M.catchIOError (raise "caught") (pure . M.ioeGetErrorString)
   assert (caught == "caught")
   putStrLn "host stack assertions PASS"
