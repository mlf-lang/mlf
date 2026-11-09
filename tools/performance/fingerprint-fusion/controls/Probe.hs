module Probe where
import qualified MLF.Primitive as M

stepA, namedA, stepB, namedB, unmatchedMultiplier, unmatchedModulus :: M.Int -> M.Int -> M.Int
stepA a c = ((a M.* 65599) M.+ c) M.% 2147483647
namedA a c = M.remInt (M.addInt (M.mulInt a 65599) c) 2147483647
stepB a c = ((a M.* 131) M.+ c) M.% 2147483629
namedB a c = M.remInt (M.addInt (M.mulInt a 131) c) 2147483629
unmatchedMultiplier a c = ((a M.* 65598) M.+ c) M.% 2147483647
unmatchedModulus a c = ((a M.* 65599) M.+ c) M.% 2147483646
