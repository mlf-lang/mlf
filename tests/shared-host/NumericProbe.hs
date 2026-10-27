{-# LANGUAGE ForeignFunctionInterface #-}
module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import Foreign.C
import Control.Monad
import System.Exit
foreign import ccall unsafe "mlf_probe_strtod" c_strtod :: CString -> IO CDouble
bits = F.doubleToBits
oracle s = withCString s $ \p -> do CDouble d <- c_strtod p; pure (bits d)
integers = [2^e + d | e <- [0,1,52,53,54,63,64,100,500,1023,1024,1100], d <- [-5..5]]
decimals = [s++m++"e"++show e | s <- ["","-","+"], m <- ["0","1","2","5","12345678901234567890123456789","9007199254740993","2.2250738585072011","2.2250738585072012","1.7976931348623157","4.9406564584124654"], e <- [-9999,-400,-325,-324,-323,-309,-308,-1,0,1,23,308,309,400,9999]] ++ ["0.1","-0","-0.0","-0e99999","1e000001","+1.1","3.1415926535897932384626433832795028841971","2.225073858507201136057409796709131975934819546351645648023426109724822222021745791434886043843670002339681613571512040776993543133862172310714034240924652994101391304109e-308"]
main = do
  ds <- forM decimals $ \s -> do
    expected <- oracle s
    let actual = bits (F.readDouble (B.literal s))
    when (expected /= actual) (putStrLn ("FAIL decimal "++s++" expected="++show expected++" actual="++show actual))
    pure (expected==actual)
  is <- forM integers $ \n -> do
    expected <- oracle (show n)
    let actual = bits (F.intToDouble n)
    when (expected /= actual) (putStrLn ("FAIL integer "++show n++" expected="++show expected++" actual="++show actual))
    pure (expected==actual)
  putStrLn ("TOTAL "++show (length (ds++is))++" FAILED "++show (length (filter not (ds++is))))
  unless (and (ds++is)) exitFailure
