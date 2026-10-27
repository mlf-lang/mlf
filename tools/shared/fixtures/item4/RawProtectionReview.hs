{-# LANGUAGE OverloadedStrings #-}
module RawProtectionReview(runRawProtectionReview) where
import Prelude
import Control.Monad(unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Separate as U
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.Data as D
import qualified Bootstrap.Map as M
import qualified MLF.Host.Base as B

expect label value=case value of T.Left e->error(label++": "++B.unpack e);T.Right a->pure a
assert label ok=unless ok(error label)
int=T.XCon "Int" []
p=T.XName 1 "protected"
q=T.XName 2 "ordinary"
local=T.XName 3 "protected"
root=T.XName 4 "root"
mk params rhs=do
 let core=T.XLet root rhs(T.XConstructor "()" [])
     term=T.XWithData [] (foldr(\(n,t)b->T.XAbs n t b)core params)
 checked<-expect "independent raw object target check"(Checked.check term)
 ds<-expect "empty data env"(D.validateDeclarations [])
 bs<-expect "independent raw binding metadata"(U.collectBindings ds(T.XEnv M.empty(M.fromList X.compareName params))core)
 let iface=U.UnitInterface "review" [] [] [] [] [] [(X.nameHint n,t)|(n,t)<-bs](U.fingerprint(Pretty.prettyTerm term))
 pure(U.CheckedUnitObject iface checked)
runRawProtectionReview=do
 let flags=[("protected",True),("ordinary",False)]
     both=[(p,int),(q,int)]
     check label params rhs wanted=do
      obj<-mk params rhs
      actual<-expect label(S.checkedDependencyProtected flags obj)
      assert label(actual==wanted)
      putStrLn("PASS RAW PROTECTION REVIEW "++label)
 check "unused protected header is availability not use" both (T.XIntTerm 1) False
 check "ordinary actual use ignores protected availability" both (T.XVarTerm q) False
 check "actual protected parameter remains protected" both (T.XVarTerm p) True
 check "outer data and type wrappers retain actual use" both (T.XTypeAbs(T.XTyVar 20)T.XBot(T.XVarTerm p)) True
 check "local same-hint lambda is not external identity" both (T.XAbs local int(T.XVarTerm local)) False
 check "local same-hint let is not external identity" both (T.XLet local(T.XIntTerm 1)(T.XVarTerm local)) False
 check "external ID under same-hint lambda remains used" both (T.XAbs local int(T.XVarTerm p)) True
 let f=T.XName 5 "loop";x=T.XName 6 "x"
 check "recursive binding body retains protected external use" both (T.XLetRec[(f,T.XArrow int int,T.XAbs x int(T.XVarTerm p))](T.XVarTerm f)) True
 check "case-bound same-hint identity remains local" both (T.XCase(T.XIntTerm 1)int[T.XAlternative(T.XDefaultPattern(T.Just local))(T.XVarTerm local)]) False
 unused<-mk both(T.XIntTerm 1)
 noUse<-expect "unused header needs no use authority"(S.checkedDependencyProtected [] unused)
 assert "unused header needs no use authority"(not noUse)
 putStrLn "PASS RAW PROTECTION REVIEW unused header needs no use authority"
 used<-mk both(T.XVarTerm p)
 assert "used missing authority rejects"(case S.checkedDependencyProtected [] used of T.Left "used checked predecessor lacks protection authority"->True;_->False)
 putStrLn "PASS RAW PROTECTION REVIEW used missing authority rejects"
 let bad=U.UnitObject(U.objectInterface unused)(T.XWithData [](T.XLet root(T.XVarTerm p)(T.XConstructor "()" [])))
 assert "unowned free ID rejects"(case S.checkedDependencyProtected flags bad of T.Left "checked raw implementation has an unowned free parameter"->True;_->False)
 putStrLn "PASS RAW PROTECTION REVIEW unowned free ID rejects"
 let pg b=S.PreparedGroup [] [] [] M.empty [] T.Nothing[("protected",b)]
 assert "sealed raw predecessor flags affect encoded prepared key"(Q.encodeSourceGroup(pg True)/=Q.encodeSourceGroup(pg False))
 putStrLn "PASS RAW PROTECTION REVIEW sealed raw predecessor flags affect encoded prepared key"
