{-# LANGUAGE NoImplicitPrelude #-}
module HostCustomUnit where
import MLF.Primitive
-- Unit is an ordinary user ADT, not an alias or shadow of the real ().
data Unit = Unit
value :: Unit
value = Unit
nativeUnit :: IO ()
nativeUnit = putStr (textFromChars [])
check :: IO ()
check = do { () <- nativeUnit; case value of { Unit -> pure () } }
