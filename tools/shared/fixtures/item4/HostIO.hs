{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import qualified MLF.Primitive as M
import qualified MLF.Host.Base as B
import qualified Control.Exception as E
import qualified System.IO.Error as I
import Data.IORef
import Control.Monad (unless)
assert p = unless p (error "assertion failed")
main = do
 let msg = "hé😀"
 assert (M.textToChars (M.textFromChars msg) == msg)
 assert (M.charCode (M.charFromCode 0xd800) == 0xd800)
 assert (map M.charCode (M.ioeGetErrorString (M.userError [M.charFromCode 0xd800])) == [0xd800])
 -- Constructing/returning an error action or a pure bottom does not execute it.
 _ <- E.evaluate (M.ioError (error "demanded unused error") :: IO ())
 _ <- pure (error "demanded pure return" :: ())
 _ <- M.catchIOError (M.ioError (M.userError (error "demanded message"))) (\_ -> pure ())
 count <- newIORef (0::Int)
 v <- M.catchIOError (M.fail msg >>= \(_::()) -> modifyIORef' count (+1) >> pure 0)
                    (\e -> assert (I.isUserError e && M.ioeGetErrorString e == msg) >> pure 42)
 assert (v == (42::Int)); readIORef count >>= assert . (==0)
 v2 <- M.catchIOError (M.catchIOError (M.ioError (M.userError msg)) M.ioError) (\_ -> pure 12)
 assert (v2 == (12::Int))
 x <- E.try (M.catchIOError (E.evaluate (M.panic (M.textFromChars "pure panic") :: ())) (\_ -> error "caught panic"))
 case x of Left (_::B.HostError) -> pure (); Right _ -> error "missing panic"
 y <- E.try (E.evaluate (M.textFromChars [M.charFromCode 0xd800]))
 case y of Left (_::B.HostError) -> pure (); Right _ -> error "accepted surrogate text"
 scope <- M.asyncScopeNew 16 16
 _ <- M.asyncEnqueue scope (M.fail msg)
 _ <- M.catchIOError (M.asyncStep scope) (\_ -> pure 42)
 _ <- M.asyncEnqueue scope (modifyIORef' count (+1) >> pure ())
 _ <- M.asyncStep scope
 readIORef count >>= assert . (==1)
 -- A normal catch frame must not intercept errors from its continuation.
 r <- M.catchIOError ((M.catchIOError (pure ()) (\_ -> error "expired handler")) >> M.fail msg) (\_ -> pure 7)
 assert (r == (7::Int))
 _ <- M.asyncNewCompletion scope (\cell -> do
      _ <- M.asyncSubscribeCompletion cell (\(_::()) -> M.fail msg)
      _ <- M.asyncResolveCompletion cell ()
      pure ()) (error "completion allocation failed")
 _ <- M.catchIOError (M.asyncStep scope) (\_ -> pure 42)
 _ <- M.asyncEnqueue scope (modifyIORef' count (+1) >> pure ())
 _ <- M.asyncStep scope
 readIORef count >>= assert . (==2)
 _ <- M.catchIOError (M.fail msg) (\_ -> pure (error "demanded handler result" :: ()))
 _ <- M.asyncEnqueue scope (M.catchIOError (M.fail msg) (\_ -> do
      status <- M.asyncStep scope
      assert (status == 8)
      pure ()))
 _ <- M.asyncStep scope
 inner <- M.asyncScopeNew 16 16
 _ <- M.asyncEnqueue inner (M.fail msg)
 _ <- M.asyncEnqueue scope (M.asyncStep inner >> pure ())
 _ <- M.catchIOError (M.asyncStep scope) (\_ -> pure 42)
 status1 <- M.asyncStep scope
 status2 <- M.asyncStep inner
 assert (status1 == 1 && status2 == 1)
 putStrLn "host item4 assertions PASS"
