{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless, forM_)
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateQuery as Q
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

-- Compare the resolver-owned executable path against the unchanged named
-- compatibility path, including all prepared fields and checked slot reads.

need label value = unless value (error label)
int=T.SCon "Int" []; bool=T.SCon "Bool" []; fn=T.SArrow int int
a=T.STVar "a"
ann ty=T.SAnnotation [] ty
intX=T.XCon "Int" []
prev=V.fromInt 0; owner=V.fromInt 1
table=D.symbols [("prior/f",False),("local/f",False)]
externals=M.singleton "prior/f" fn
types=M.singleton "prior/f" (T.XArrow intX intX)
protected=M.singleton "prior/f" False
scopes=D.indexedScopes table [(owner,IS.empty)]
showContracts cs=[(n,classes,flag)|(n,classes,flag)<-cs]
aw auth=case auth of
 T.Nothing -> Nothing
 T.Just (S.RootAuthority n labels prot candidates flags) -> Just (n,labels,prot,[(Q.encodeRole role,name,Q.encodeXType ty)|(role,name,ty)<-candidates],flags)
vw p=(map Q.encodeMember (S.groupOriginal p),map Q.encodeMember (S.groupMembers p),
 map Q.encodeBinding (S.groupBindings p),M.toList (S.groupRegistry p),
 showContracts (S.groupContracts p),aw (S.groupAuthority p),S.groupParameterProtection p)
bind (T.Left e) _=T.Left e
bind (T.Right a) f=f a
new annotation body =
 bind (S.prepareResolvedSourcePlan (D.BoundValues table [D.Bound owner annotation body])
   externals [] [] [] [] scopes []) $ \(route,_) -> case route of
    T.Nothing -> T.Right []
    T.Just raw ->
     bind (S.initializeProtection raw protected) $ \plan ->
     bind (S.initialContracts plan types protected) $ \contracts ->
     let scope=S.planScope plan (M.keys contracts) in
     bind (S.installContracts scope contracts) $ \checked ->
     bind (S.querySteps plan scope) $ \steps ->
     traverseT (\(ids,prepare)->bind (prepare checked) $ \p ->
       bind (S.slotPrepared checked ids p) $ \(_,ready)->T.Right (vw ready)) steps
old annotation body =
 bind (S.prepareResolvedSourcePlan (D.BoundValues table [D.Bound owner annotation body])
   externals [] [] [] [] scopes []) $ \(route,_) -> case route of
    T.Nothing -> T.Right []
    T.Just raw ->
     bind (S.initializeProtection raw protected) $ \plan ->
     bind (S.initialContracts plan types protected) $ \contracts ->
     let scope=S.planScope plan (M.keys contracts) in
     bind (S.installContracts scope contracts) $ \checked ->
     bind (S.querySteps plan scope) $ \steps ->
     traverseT (\(ids,_)->bind (S.prepareGroup plan contracts (map (S.declName scope) ids)) $ \p ->
       bind (S.slotPrepared checked ids p) $ \(_,ready)->T.Right (vw ready)) steps
traverseT f xs=case xs of []->T.Right []; x:rest->bind (f x) $ \a -> bind (traverseT f rest) $ \as->T.Right (a:as)
norm (T.Left e)=Left (B.unpack e)
norm (T.Right x)=Right x
app2 p x y=R.App (R.App (R.Prim p) x) y
span0=T.SourceSpan "package" "Module" "source.hs" 2 3 4 5
leafs=[R.IntLit 7,R.BoolLit True,R.StringLit "α😀",R.DoubleLit (-0.0),R.Local "x",
 R.Global prev,R.Global owner,R.Prim T.PAddInt,R.CallStack]
bodies=leafs ++
 [R.Lam "x" T.Nothing (app2 T.PAddInt (R.Local "x") (R.IntLit 1)),
  R.Lam "f" T.Nothing (R.App (R.Global prev) (R.Local "f")),
  R.Lam "x" (T.Just (ann int)) (R.Local "x"),
  R.Let "x" (R.IntLit 3) (R.Local "x"),
  R.Let "f" (R.IntLit 3) (R.Global prev),
  R.Signature (R.Lam "x" T.Nothing (R.Local "x")) (ann fn),
  R.Ann (R.IntLit 3) (ann int),
  R.Case (R.BoolLit True) [(R.BoolPattern True,R.IntLit 1),(R.DefaultPattern T.Nothing,R.IntLit 2)],
  R.CallSite "f" span0 (R.Lam "x" T.Nothing (R.App (R.Global prev) (R.Local "x"))),
  R.SourceDefinition (R.Lam "x" T.Nothing (R.Local "x")),
  R.LetRec [("g",T.CheckRecursive (ann fn),R.Lam "x" T.Nothing (R.App (R.Local "g") (R.Local "x")))] (R.Local "g")]
annotations=[T.Nothing,T.Just (ann int),T.Just (ann bool),T.Just (ann fn),
 T.Just (ann (T.SForall T.Flexible "a" T.SBottom (T.SArrow a a))),
 T.Just (ann (T.SCon "Unknown" [])),
 T.Just (T.SAnnotation ["e"] (T.STVar "e"))]
brief (Left e)="Left "++e
brief (Right xs)="Right "++show [(map B.unpack a,map B.unpack b,map B.unpack c) | (a,b,c,_,_,_,_)<-xs]
main=do
 let cases=[(a,b)|a<-annotations,b<-bodies]
     plainBody=R.Lam "x" T.Nothing (app2 T.PAddInt (R.Local "x") (R.IntLit 1))
     importedBody=R.Lam "x" T.Nothing (R.App (R.Global prev) (R.Local "x"))
     succeeds result=case norm result of Right [_]->True; _->False
 need "plain signed preparation succeeds" (succeeds (new (T.Just (ann fn)) plainBody))
 need "signed import preparation succeeds" (succeeds (new (T.Just (ann fn)) importedBody))
 -- Unknown named types stay in the differential corpus. Final type checking,
 -- exercised by the CLI controls, owns their rejection after preparation.
 forM_ (zip [0 :: Int ..] cases) $ \(i,(a,b))->need ("indexed vs compatibility preparation "++show i++" NEW "++brief (norm (new a b))++" OLD "++brief (norm (old a b))) (norm (new a b)==norm (old a b))
 let eligible=[("f",T.Just (ann fn),T.SLam "x" T.Nothing (T.SVar "x"))]
 need "new indexed signed seam exercised" (S.eligibleIndexedSourceWith False eligible && not (S.eligibleSourceWith False eligible))
 need "self recursive signature stays grouped" (not (S.eligibleIndexedSourceWith True eligible))
 putStrLn ("PASS signed source roots: "++show (length cases)++" complete prepared/query-slot comparisons and nonvacuous eligibility/fallback controls")
