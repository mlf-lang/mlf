{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (forM_, unless)
import Data.IORef
import qualified Corpus as C
import qualified Bootstrap.SourceEquality as E
import qualified Bootstrap.CrateGraph as G
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.ArtifactStructure as A
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

member body = [("member",T.Nothing,body)]
key = Q.keyList (Q.memberKey Q.inlineScopeKey)
encoded = Q.list Q.encodeMember
present T.Nothing = False
present (T.Just _) = True
same a b = case (a,b) of
  (W.VInt x,W.VInt y) -> x==y
  (W.VBits x,W.VBits y) -> x==y
  (W.VText x,W.VText y) -> x==y
  (W.VNode x xs,W.VNode y ys) -> x==y && length xs==length ys && and (zipWith same xs ys)
  _ -> False
-- Frozen uncached path, independent of preparedValueCached and SourceKey.
legacy slots prepared = let
  table=Q.referenceTable slots prepared
  encode=Q.encodeMember . Q.referenceMember table
  token=Q.referenceToken table
  candidate protected (role,n,_)=Q.node "candidate"
    [Q.encodeRole role,token n,Q.boolean (n `elem` protected)]
  in W.VNode 421 [W.VText "prepared-declarations-1",A.toList A.toText (Q.referenceDefinitions table),
       W.VText (Q.list encode (S.groupOriginal prepared)), W.VText (Q.list encode (S.groupMembers prepared)),
       A.toList A.toText (Q.sourceGroupMetadataWith token candidate prepared)]
fixture owner stable registry protected role = let
  symbols=D.symbolsWithKeys [(owner,stable,False),("dependency","external-key",False)]
  scope=S.declarationScope symbols [V.fromInt 0] [] []
  slots=S.GroupSlots scope [V.fromInt 0] [V.fromInt 1] [V.fromInt 1]
  members=[(owner,T.Nothing,T.SLam "arg" T.Nothing (T.SApp (T.SGlobal (V.fromInt 1) "dependency") (T.SVar "arg")))]
  metadata=T.Just (S.RootAuthority owner [("slot","Class","dictionary")] protected
    [(role,"dependency",error "candidate type is not part of this value")] (if protected then ["dependency"] else []))
  prepared=S.PreparedGroup members members [] (M.fromList P.compareString registry)
    [(owner,["Class"],protected)] metadata [("dependency",protected)]
  in (slots,prepared)

main = do
  count<-newIORef (0::Int)
  let check label ok=do unless ok (error label);modifyIORef' count (+1)
      floats=map (T.SDoubleLit . P.doubleFromBits) [0,-9223372036854775808,9218868437227405312,
        -4503599627370496,9221120237041090561,9221120237041090562]
      annotations=[T.SAnnotation [] ty | ty <- [T.STVar "x",T.SBottom,T.SBottomKind (T.KArrow T.Star T.Star),
        T.SArrow (T.STVar "a") (T.STVar "b"),T.SCon "List" [T.STVar "a"],T.STypeApp (T.STVar "f") (T.STVar "a"),
        T.SForall T.Rigid "a" T.SBottom (T.STVar "a"),T.SQualified [T.SPredicate "Eq" [T.STVar "a"]] (T.STVar "a")]]
      scopes=[[],C.scope,reverse C.scope,head C.scope:C.scope,[(T.InstanceEvidence,"given")],[(T.GivenEvidence,"other")]]
      extra=[T.SGlobal (V.fromInt 0) "ignored-display",T.SGlobal (V.fromInt 1) "ignored-display",
        T.SDeclScope [V.fromInt 0,V.fromInt 1] C.wanted,T.SDeclScope [V.fromInt 1,V.fromInt 0] C.wanted,
        T.SWantedRefs "Dict" [(T.GivenEvidence,T.LexicalRef "x"),(T.InstanceEvidence,T.DeclRef (V.fromInt 2) "show")],
        T.SCase C.wanted [T.SAlternative (T.SIndexedStringPattern (T.CharString [97,55296])
          (T.DeclRef (V.fromInt 0) "equal") (T.LexicalRef "from")) C.wanted],
        T.SCallSite "other-call" C.span0 C.wanted,
        T.SCallSite "call" (T.SourceSpan "package" "Module" "source.hs" 1 2 3 5) C.wanted]
      bodies=C.expressions++floats++extra++[T.SAnn C.wanted a|a<-annotations]++[T.SWanted "Dict" s|s<-scopes]
      rows=map member bodies++[[],[("different",T.Nothing,T.SVar "x")],[("member",T.Just C.annotation,T.SVar "x")],
        [("member",T.Nothing,T.SVar "x"),("another",T.Nothing,T.SIntLit 0)]]
      seed=member (T.SIntLit 99)
  forM_ (zip [0::Int ..] rows) $ \(i,original)->do
    let (a,b,cache)=G.preparedSyntax T.Nothing original seed
        (a2,b2,hit)=G.preparedSyntax cache original seed
    check ("cold original "++show i) (a==encoded original && b==encoded seed)
    check ("hit original "++show i) (a2==a && b2==b && present cache && present hit)
    let (c,d,lowerCache)=G.preparedSyntax cache seed original
        (c2,d2,_)=G.preparedSyntax lowerCache seed original
    check ("changed both lanes "++show i) (c==encoded seed && d==encoded original && c2==c && d2==d)
    forM_ (zip [0::Int ..] rows) $ \(j,next)->do
      check ("exact key equivalence "++show (i,j)) (G.samePreparedMembers original next==(encoded original==encoded next))
      let (x,y,_)=G.preparedSyntax cache next seed
          (z,t,_)=G.preparedSyntax cache original next
      check ("original transition "++show (i,j)) (x==encoded next && y==encoded seed)
      check ("lowered transition "++show (i,j)) (z==encoded original && t==encoded next)
  let (_,_,small)=G.preparedSyntax T.Nothing seed seed
      deep=member (foldr (\_ a->T.SSourceDefinition a) (T.SIntLit 0) [1..40::Int])
      broad=[("member",T.Nothing,T.SIntLit i)|i<-[1..80]]
      large=member (T.SStringLit (B.literal (replicate 17000 'x')))
  forM_ [deep,broad,large] $ \largeRow->do
    let (a,b,next)=G.preparedSyntax small seed largeRow
        (c,d,recovered)=G.preparedSyntax next seed seed
    check "oversized input uses exact uncached output" (a==encoded seed && b==encoded largeRow && not (present next))
    check "small input resumes caching" (c==encoded seed && d==encoded seed && present recovered)
  check "combined node bound" (not (G.smallPreparedKey (Q.KeyFields (replicate 256 (Q.KeyText "")))))
  check "combined scalar bound" (not (G.smallPreparedKey (Q.KeyFields [Q.KeyText (B.literal (replicate 9000 'x')),Q.KeyText (B.literal (replicate 9000 'y'))])))
  check "external scope retention forbidden" (not (G.smallPreparedKey (Q.KeyScope [])))
  let wrappers=[id,T.SLam "x" T.Nothing,\v->T.SApp v v,\v->T.SLet "x" v v,
        \v->T.SAnn v C.annotation,\v->T.SSignature v C.annotation,
        \v->T.SCase (T.SIntLit 0) [T.SAlternative (T.SDefaultPattern T.Nothing) v],
        T.SSourceDefinition,T.SCallSite "call" C.span0,
        \v->T.SSharedBind (T.SDefaultPattern T.Nothing) v v v v,
        \v->T.SDo [T.SDoBind (T.SDefaultPattern T.Nothing) v] (T.SIntLit 0),
        \v->T.SDo [T.SDoThen v] (T.SIntLit 0),
        \v->T.SDo [T.SDoLet "x" T.Nothing v] (T.SIntLit 0),
        \v->T.SDo [T.SDoLetRec [("x",T.InferRecursive,v)]] (T.SIntLit 0),
        \v->T.SEquations [([],v)],\v->T.SLetRec [("x",T.CheckRecursive C.annotation,v)] (T.SIntLit 0),
        T.SChecked (T.SCon "Double" []),T.SDeclScope [V.fromInt 0]]
  forM_ (zip [0::Int ..] wrappers) $ \(i,wrap)->
    forM_ floats $ \a->forM_ floats $ \b->do
      let left=member (wrap a);right=member (wrap b)
          (_,_,cache)=G.preparedSyntax T.Nothing seed left
          (actualFirst,actualSecond,_)=G.preparedSyntax cache seed right
      check ("nested IEEE policy "++show i) (G.samePreparedMembers left right==(encoded left==encoded right))
      check ("nested IEEE cache transition "++show i) (actualFirst==encoded seed && actualSecond==encoded right)
  let cases=[fixture "owner" "local-key" [] False T.GivenEvidence,
        fixture "renamed" "another-local-key" [] False T.GivenEvidence,
        fixture "owner" "local-key" [("Class","dictionary")] False T.GivenEvidence,
        fixture "owner" "local-key" [] True T.GivenEvidence,
        fixture "owner" "local-key" [] False T.InstanceEvidence]
      (firstSlots,firstPrepared)=head cases
      (first,firstCache)=G.preparedValueCached T.Nothing firstSlots firstPrepared
  check "initial full value equals legacy" (same first (legacy firstSlots firstPrepared))
  forM_ (zip [0::Int ..] (tail cases)) $ \(i,(slots,prepared))->do
    let (actual,_)=G.preparedValueCached firstCache slots prepared
    check ("complete value preserves current metadata "++show i) (same actual (legacy slots prepared))
    check ("current identity and metadata stay distinct "++show i) (not (same first actual))
  check "old expression equality keeps numerical zero semantics" (E.eqSExpr (T.SDoubleLit (P.doubleFromBits 0)) (T.SDoubleLit (P.doubleFromBits (-9223372036854775808))))
  check "old expression equality keeps NaN semantics" (not (E.eqSExpr (T.SDoubleLit (P.doubleFromBits 9221120237041090561)) (T.SDoubleLit (P.doubleFromBits 9221120237041090561))))
  check "exact expression equality distinguishes zero sign" (not (E.eqSExprBits (T.SDoubleLit (P.doubleFromBits 0)) (T.SDoubleLit (P.doubleFromBits (-9223372036854775808)))))
  check "exact expression equality admits identical NaN payload" (E.eqSExprBits (T.SDoubleLit (P.doubleFromBits 9221120237041090561)) (T.SDoubleLit (P.doubleFromBits 9221120237041090561)))
  total<-readIORef count
  putStrLn ("Prepared syntax controls: "++show total++" checks; "++show (length rows)++" syntax variants")
