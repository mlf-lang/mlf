module Main where
import qualified Data.List as L
import qualified Prelude as H
import Prelude (IO, ($), (.), (++), (==), not, (&&), error, putStrLn, show)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Parser as P
import qualified Bootstrap.Module as M
import qualified MLF.Host.Base as B
list []=[]
list ((:) x xs)=x:list xs
text=B.unpack
header="-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n"
parse profile body=P.parseModuleWithProfile profile (B.literal "Syntax.hs") (B.literal ((case profile of T.SharedHaskellV1->header;_->"")++"module Syntax where { import MLF.Primitive; "++body++" }\n"))
refs e=case e of
 T.SConstructor n->[text n]
 T.SVar n->[text n]
 T.SCallSite _ _ x->refs x
 T.SApp f x->refs f++refs x
 T.SLam _ _ x->refs x
 T.SLet _ x y->refs x++refs y
 T.SAnn x _->refs x
 T.SChecked _ x->refs x
 T.SLetRec ds x->H.concatMap (\((,,) _ _ v)->refs v) (list ds)++refs x
 T.SEquations rs->H.concatMap (\((,) ps x)->H.concatMap pat (list ps)++refs x) (list rs)
 T.SCase x bs->refs x++H.concatMap (\(T.SAlternative p y)->pat p++refs y) (list bs)
 T.SSharedBind p x y b f->pat p++refs x++refs y++refs b++refs f
 T.SDo _ _->["OLD-DO"]
 _->[]
pat p=case p of
 T.SConstructorPattern n _->[text n]
 T.SNestedPattern n ps->text n:H.concatMap pat (list ps)
 T.SOverloadedStringPattern _ a b->[text a,text b]
 T.SAsPattern _ x->pat x
 T.SLazyPattern x->pat x
 _->[]
allrefs m=H.concatMap (\((,,) _ _ e)->refs e) (list (M.sourceValues m))
typeRefs ty=case ty of
 T.SCon n xs->text n:H.concatMap typeRefs (list xs)
 T.SArrow a b->typeRefs a++typeRefs b
 T.STypeApp a b->typeRefs a++typeRefs b
 T.SForall _ _ a b->typeRefs a++typeRefs b
 T.SQualified ps x->H.concatMap (\(T.SPredicate _ xs)->H.concatMap typeRefs(list xs)) (list ps)++typeRefs x
 _->[]
annotationRefs (T.SAnnotation _ ty)=typeRefs ty
fieldRefs f=case f of
 T.Applied n xs->text n:H.concatMap fieldRefs(list xs)
 T.Application a b->fieldRefs a++fieldRefs b
 T.Function a b->fieldRefs a++fieldRefs b
 T.Quantified _ _ x->fieldRefs x
 _->[]
declRefs d=case d of
 T.DataDecl _ _ cs->ctors cs
 T.DataDeclK _ _ cs->ctors cs
 where ctors cs=H.concatMap (\(T.ConstructorDecl _ fs)->H.concatMap fieldRefs(list fs)) (list cs)
allTypeRefs m=H.concatMap (\((,,) _ a _)->case a of T.Nothing->[];T.Just x->annotationRefs x) (list(M.sourceValues m))++H.concatMap declRefs(list(M.sourceDatatypes m))
check profile label body names=case parse profile body of
 T.Left e->error(label++": "++text e)
 T.Right m->if H.all (`H.elem` allrefs m) names && not ("OLD-DO" `H.elem` allrefs m) && not(H.any (`H.elem` allTypeRefs m) ["List","Pair","Triple","Quad","Unit"]) then putStrLn("PASS "++label) else error(label++": wrong references "++show(allrefs m))
reject profile=case parse profile ("main = ("++H.replicate 64 ','++");") of
 T.Left e->if not ("tuple arity must be between 2 and 64" `L.isInfixOf` text e) then error ("wrong tuple65 diagnostic: "++text e) else putStrLn("PASS tuple65 rejects: "++text e)
 T.Right _->error "tuple65 accepted"
run profile=do
 check profile "prefixcons term/type" "main :: [] Int; main = (:) 1 [];" [":","[]"]
 check profile "prefixtuple term/type" "main :: (,) Int Int; main = (,) 1 2;" ["(,)"]
 check profile "prefixcons pattern" "f ((:) x xs) = x; main = f [1];" [":","[]"]
 check profile "prefixtuple pattern" "f ((,) x y) = x; main = f (1,2);" ["(,)"]
 check profile "prefix field partial constructor" "data Box = Box ([] Int) ((,) Int Int); main = Box [] (1,2);" ["[]","(,)"]
 check profile "canonicalunit" "main = ();" ["()"]
 check profile "oldnominal List stays distinct" "data List = Nil; main = [];" ["[]"]
 check profile "oldnominal Pair stays distinct" "data Pair = Pair Int Int; main = (1,2);" ["(,)"]
 check profile "canonicaldo" "main = do { x <- pure 1; pure x };" ["$MLF.Primitive.>>="]
 check profile "lexical equality expression" "main = 1 == 2;" ["=="]
 check profile "canonical stringpattern" "f \"x\" = 1; f _ = 2; main = f \"x\";" ["$MLF.Primitive.==","$MLF.Primitive.fromString"]
 check profile "tuple64 partial constructor" ("main = ("++H.replicate 63 ','++") 1;") ["("++H.replicate 63 ','++")"]
 check profile "tuple64 saturated type" ("main :: ("++H.replicate 63 ','++") "++H.unwords(H.replicate 64 "Int")++"; main = ("++H.replicate 63 ','++");") ["("++H.replicate 63 ','++")"]
 reject profile
main :: IO ()
main=run T.SharedHaskellV1 H.>> run T.LegacyEmlfV1
