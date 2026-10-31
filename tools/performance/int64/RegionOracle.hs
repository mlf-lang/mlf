module Main(main) where
import Prelude
import Data.Int(Int64)
import Data.Bits((.&.))
main=do
 let limit=2^62 :: Int64
     values=[negate maxBound,-limit-1,-limit,-3,0,3,limit-1,limit,maxBound]
     pairs=[(a,b)|a<-values,b<-[-1,2,limit-1]]
 mapM_ print [v|(a,b)<-pairs,v<-[a*b,a `quot` (-1),a `rem` (-1),a `quot` 3,a `rem` 3,a `quot` (-3),a `rem` (-3),a .&. b]]
 print ((minBound::Int64) `rem` (-1))
