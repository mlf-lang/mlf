module RawSolverRebind where
import qualified Bootstrap.CrateSession as C
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
bad :: T.Solver -> IO (T.Either B.String ())
bad solver = C.compileSpecFile solver (B.literal "unused")
