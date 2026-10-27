{-# LANGUAGE NoImplicitPrelude #-}
module ApplicativePure where
import MLF.Primitive
import SharedIdentity (Box(..))
standardPure :: Box Int
standardPure = pure 1
