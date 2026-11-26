{-# LANGUAGE OverloadedStrings #-}
module NamedQueryControls (checkRejections) where

import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_)
import Data.List (isInfixOf)
import qualified Bootstrap.Types as T

-- Exercise every adapter boundary. Undefined payloads ensure the named oracle
-- refuses these forms itself, before touching data it cannot interpret.
checkRejections :: (T.SExpr -> a) -> (T.SExpr -> b) -> (T.SExpr -> c)
                -> (T.SPattern -> d) -> (T.SPattern -> e) -> IO Int
checkRejections encode key canonical encodePattern canonicalPattern = do
  let payload = errorWithoutStackTrace "unsupported constructor payload was forced"
      expressions =
        [ T.SGlobal payload payload
        , T.SDeclScope payload payload
        , T.SWantedRefs payload payload
        , T.SWantedScope payload payload
        , T.SGivenScope payload payload
        , T.SApplyDictionaries payload payload
        , T.SBindDictionaries payload payload
        ]
      pattern = T.SIndexedStringPattern payload payload payload
  forM_ expressions $ \expression -> do
    rejects (encode expression)
    rejects (key expression)
    rejects (canonical expression)
  rejects (encodePattern pattern)
  rejects (canonicalPattern pattern)
  pure (length expressions * 3 + 2)

rejects :: a -> IO ()
rejects value = do
  outcome <- try (evaluate value >> pure ()) :: IO (Either SomeException ())
  case outcome of
    Left exception
      | "indexed syntax in historical named query oracle" `isInfixOf` displayException exception -> pure ()
      | otherwise -> fail ("wrong query oracle rejection: " ++ displayException exception)
    Right () -> fail "named query oracle accepted an unsupported constructor"
