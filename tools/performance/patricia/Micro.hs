module Main(main) where
import Prelude
import Data.Int(Int64)
import Data.List(foldl')
import System.Environment(getArgs)
import qualified Bootstrap.IntMap as M
import qualified Bootstrap.IntSet as S
import qualified Bootstrap.Types as T

main = do
  [mode,shape,rawSize,rawRepeats] <- getArgs
  let count=read rawSize::Int
      repeats=read rawRepeats::Int
      key i=if shape=="dense" then fromIntegral(i-count `div` 2)
            else fromIntegral i * (-7046029254386353131)::Int64
      left=M.fromList[(key i,fromIntegral i::Int64)|i<-[0..count-1]]
      right=M.fromList[(key i,fromIntegral i::Int64)|i<-[count `div` 2..count+count `div` 2-1]]
      leftSet=S.fromList[key i|i<-[0..count-1]]
      rightSet=S.fromList[key i|i<-[count `div` 2..count+count `div` 2-1]]
      get i=case M.lookup(key(i `mod` (2*count)))left of T.Nothing->0;T.Just n->n
      sorted i=[(fromIntegral(j+i*10000000)::Int64,fromIntegral j::Int64)|j<-[0..count-1]]
      result=case mode of
        "lookup" -> foldl' (\acc i->acc+get i) 0 [0..count*repeats-1]
        "update" -> let changed=foldl' (\m i->M.insert(key(i `mod` count))(fromIntegral i)m)left[0..count*repeats-1]
                    in M.size changed+foldl' (+) 0 (M.elems changed)
        "map-merge" -> foldl' (\acc i->acc+M.size(M.union left(M.insert(key(count*2+i))1 right)))0[0..repeats-1]
        "set-merge" -> foldl' (\acc i->acc+S.size(S.union leftSet(S.insert(key(count*2+i))rightSet)))0[0..repeats-1]
        "map-sorted" -> foldl' (\acc i->acc+M.size(M.fromDistinctAscList(sorted i)))0[0..repeats-1]
        "set-sorted" -> foldl' (\acc i->acc+S.size(S.fromDistinctAscList(map fst(sorted i))))0[0..repeats-1]
        _ -> error "unknown microbenchmark mode"
  print result
