module Main(main) where
import Prelude
import Data.Int(Int64)
import Data.Word(Word64)
import Data.Bits(xor)
import GHC.Float(castWord64ToDouble,castDoubleToWord64)
import Numeric(showHex)
import Control.Exception(try,evaluate)
import Control.Monad(forM_,unless)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as Solver
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.LLVM.Native as N
import qualified Bootstrap.LLVM.Build as Build
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Parser as Parser

check label ok = unless ok (errorWithoutStackTrace ("FAIL "++label))
observe :: Int64 -> IO(Either B.HostError Int64)
observe = try . evaluate
lo64, hi64 :: Integer
lo64 = toInteger (minBound::Int64)
hi64 = toInteger (maxBound::Int64)
clamp lo hi = if lo<lo64 || hi>hi64 then (minBound,maxBound) else (fromInteger lo,fromInteger hi)
main = do
  let ends=[minBound,minBound+1,-(2^62),-4294967296,-1,0,1,4294967296,2^62-1,maxBound-1,maxBound]::[Int64]
  forM_ ends $ \a -> forM_ ends $ \b -> do
    let mathematical=toInteger a+toInteger b
    result<-observe(S.advanceIdentity a b)
    if mathematical<lo64 || mathematical>hi64
      then case result of Left(B.HostError message)->check "counter exhaustion" (message=="identity supply exhausted");_->check "wrapped counter admitted" False
      else case result of Right n->check "counter result" (toInteger n==mathematical);_->check "in-range counter rejected" False
  check "maximum range terminates" (take 2(S.range maxBound maxBound)==[maxBound::Int64])
  check "minimum range terminates" (take 2(S.range minBound minBound)==[minBound::Int64])
  exhausted<-observe(G.nextId(snd(G.freshId(G.mkGraph IM.empty IM.empty maxBound))))
  case exhausted of Left(B.HostError message)->check "graph supply exhaustion" (message=="identity supply exhausted");_->check "graph wrapped" False
  let ranges=[(a,b)|a<-ends,b<-ends,a<=b]
  forM_ ranges $ \(a,b) -> do
    let graph=G.mkGraph (G.nodesFromList [(a,T.Node T.GBot T.Nothing T.Flexible),(b,T.Node T.GBot T.Nothing T.Flexible)]) IM.empty maxBound
        dense=toInteger b-toInteger a<=8*(if a==b then 1 else 2)
    case G.denseBounds graph of
      T.Nothing -> check "sparse graph span remains sparse" (not dense)
      T.Just (low,high) -> check "dense graph span cannot wrap" (dense && low==a && high==b)
  let levels n=if n<=1 then 1 else 1+levels((n+1) `div` 2)
  forM_ ends $ \count -> check "scope levels cannot wrap" (toInteger(Solver.scopeLevels count)==levels(toInteger count))
  let ground counter=G.mkGraph (G.nodesFromList
        [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),
         (1,T.Node (T.GArr 2 2) (T.Just 0) T.Flexible),
         (2,T.Node (T.GTyCon (B.literal "Int") T.Star) (T.Just 1) T.Rigid),
         (3,T.Node T.GBot (T.Just 4) T.Flexible),
         (4,T.Node (T.GGen 3) (T.Just 0) T.Flexible)]) IM.empty counter
  forM_ [maxBound-1,maxBound] $ \counter -> case Solver.prepare(ground counter) of
    T.Left message -> errorWithoutStackTrace("invalid ground fixture: "++B.unpack message)
    T.Right solver -> do
      result<-observe(case Solver.groundGraft 0 3 solver of
        T.Nothing -> errorWithoutStackTrace "ground graft path not entered"
        T.Just next -> G.nextId(Solver.graph next))
      if counter==maxBound
        then case result of Left(B.HostError message)->check "ground graft exhaustion" (message=="identity supply exhausted");_->check "ground graft wrapped" False
        else case result of Right next->check "ground graft last counter" (next==maxBound);_->check "ground graft rejected in-range counter" False
  forM_ ranges $ \(a,b) -> forM_ ranges $ \(c,d) -> do
    let products=[toInteger x*toInteger y|x<-[a,b],y<-[c,d]]
    check "exact product proof" (N.productBounds(a,b)(c,d)==clamp(minimum products)(maximum products))
    check "exact sum proof" (N.integerBounds T.PAddInt (a,b)(c,d)==clamp(toInteger a+toInteger c)(toInteger b+toInteger d))
    check "exact difference proof" (N.integerBounds T.PSubInt (a,b)(c,d)==clamp(toInteger a-toInteger d)(toInteger b-toInteger c))
  forM_ [0,1,0x8000000000000000,0x8000000000000001,0x3fe0000000000000,0xbfe0000000000000,0x7fefffffffffffff,0xffefffffffffffff,0x0010000000000000,0x8010000000000000] $ \bits -> do
    let value=castWord64ToDouble bits;decimal=B.unpack(Pretty.prettyDouble value);hex=showHex bits ""
    check "exact finite decimal roundtrip" (castDoubleToWord64(read decimal)==bits)
    check "LLVM unsigned hex bits" (B.unpack(Build.doubleLiteral value)=="0x"++replicate(16-length hex)'0'++hex)
    check "floating negation flips only sign" (castDoubleToWord64(S.negateDouble value)==xor bits 0x8000000000000000)
  forM_ [0,1,hi64,hi64+1,2^64,2^128] $ \n -> case Parser.decimal(B.literal(show n)) of
    T.Right k -> check "identity parse range" (n<=hi64 && toInteger k==n)
    T.Left message -> check "identity rejects overflow" (n>hi64 && B.unpack message=="identity is outside the supported integer range")
  check "negative minimum identity spelling" (B.unpack(Pretty.variable(T.XTyVar minBound))=="z9223372036854775808")
  putStrLn "PASS compiler Int64 controls: counter and ground-graft exhaustion, sparse spans, scope depth, range termination, exact LLVM interval proofs, float formatting/negation, bounded identity parsing"
