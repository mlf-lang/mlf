module Main where
import SharedIdentity
import ApplicativePure
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import Control.Monad
asPreludeBool :: Bool
asPreludeBool = truth
main = do
  let Box value = custom
  unless (value == 42 && numberPattern 0 == 7 && numberGuard 0 == 9 && asPreludeBool && large == 2^100 && B.unpack message == "a😀\0") (error "identity failure")
  let Box valueFromBoxPure = standardPure
  unless (valueFromBoxPure==1) (error "standard Applicative pure failure")
  let Box valueFromPreludeFunctor = fmap (+1) (pure 41 :: Box Integer)
      Box valueFromPreludeMonad = custom >>= (\x -> pure (x+1))
  unless (valueFromPreludeFunctor==42 && valueFromPreludeMonad==43) (error "standard class identity failure")
  valueFromPure <- F.pure (8::Integer)
  unless (valueFromPure==8) (error "pure alias failure")
  putStrLn "PASS actual Prelude.Bool, standard Functor/Applicative/Monad, polymorphic pure, numeric patterns/guards and opaque String literals"
