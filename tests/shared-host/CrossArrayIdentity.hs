{-# LANGUAGE NoImplicitPrelude #-}
module CrossArrayIdentity where
import MLF.Primitive
badRead :: IntArray -> Int -> IO Int
badRead = readByteArray
badWrite :: ByteArray -> Int -> Int -> IO Unit
badWrite = writeIntArray
