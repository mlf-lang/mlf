module P2Controls where
import qualified RetainedP2Controls as Legacy
import qualified BinaryP2WriterControls as Binary
main = do
  putStrLn "P2 retained 2503: current pure/fingerprint encoders and authenticated prior text-writer projection; not current binary IO"
  Legacy.main
  Binary.main
