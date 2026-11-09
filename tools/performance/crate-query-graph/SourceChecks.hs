{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless, foldM)
import System.Environment (getArgs)
import System.Directory (createDirectoryIfMissing, doesFileExist)
import Data.List (isInfixOf)
import qualified Data.ByteString as BS
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.CrateGraph as CG
import qualified Bootstrap.CrateQuery as Old
import qualified Bootstrap.QueryGraph as G
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.PreparedLibraries as Libraries
import qualified Bootstrap.PreparedLibraryLiteral as Literal
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Data as Data
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.Runtime as R
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

expect label result = case result of T.Left e -> error (label ++ ": " ++ B.unpack e); T.Right v -> pure v
assert label predicate = unless predicate (error label)
int = T.SCon "Int" []
bool = T.SCon "Bool" []
cls = T.SClassDecl "Tag" [("a",T.Star)] [] [("tag",T.SArrow (T.STVar "a") int)]
instInt = T.SInstanceDecl [] [] "Tag" [int] [("tag",T.SLam "x" T.Nothing (T.SVar "x"))]
instBool = T.SInstanceDecl [] [] "Tag" [bool] [("tag",T.SLam "x" T.Nothing (T.SIntLit 42))]
add x y = T.SApp (T.SApp (T.SPrimitive T.PAddInt) x) y
tag x = T.SApp (T.SVar "tag") x
app n x = T.SApp (T.SVar n) x
roots = [
 ("sameDeps",T.SLet "known" (T.SSignature (tag (T.SIntLit 2)) (T.SAnnotation [] int)) (add (tag (T.SIntLit 1)) (T.SVar "known")),Just 3,0),
 ("f0",tag (T.SIntLit 21),Just 21,0),
 ("f1",add (T.SVar "f0") (T.SVar "f0"),Just 42,0),
 ("mixed",add (tag (T.SIntLit 19)) (tag (T.SBoolLit True)),Just 61,0),
 ("plain",add (T.SIntLit 1) (T.SIntLit 2),Just 3,0),
 ("nonground",T.SLam "x" T.Nothing (tag (T.SVar "x")),Nothing,1),
 ("nongroundUse",add (app "nonground" (T.SIntLit 21)) (app "nonground" (T.SBoolLit True)),Just 63,0),
 ("mixedResidual",T.SLam "x" T.Nothing (add (tag (T.SIntLit 21)) (tag (T.SVar "x"))),Nothing,2),
 ("partialScope",add (tag (T.SIntLit 21)) (tag (T.SBoolLit True)),Nothing,2),
 ("managedRoot",T.SLet "ignoredStack" (T.SVar "$MLF.Stack.callStack") (tag (T.SIntLit 21)),Nothing,1),
 ("managedUse",T.SVar "managedRoot",Nothing,1)]

contractView contracts = [(n,Pretty.prettyType (U.normalType (SI.contractType c)),SI.contractClasses c,SI.contractProtected c) | (n,c)<-M.toList contracts]
view f = (map (\(n,t)->(X.nameHint n,Pretty.prettyType (U.normalType t))) (O.parameters f),
          Pretty.prettyTerm (O.body f),
          map (\(n,t)->(X.nameHint n,Pretty.prettyType (U.normalType t))) (O.bindings f))

-- Independent executable observation: substitute previously built definitions,
-- then invoke the ordinary checker and interpreter on the complete closure.
strip (T.XWithData _ b) = strip b
strip b = b
findBinding wanted (T.XLet n rhs rest) | X.nameHint n == wanted = (n,rhs)
                                     | otherwise = findBinding wanted rest
findBinding wanted (T.XLetRec bs rest) = case [(n,rhs)|(n,_,rhs)<-bs,X.nameHint n==wanted] of
 [v] -> v
 [] -> findBinding wanted rest
 _ -> error "duplicate definition"
findBinding _ _ = error "missing definition"
close definitions fragment rhs =
 let ps = O.parameters fragment
     ids = foldl (\acc (n,t)->U.typeIdentities t (IS.insert (X.nameId n) acc)) (U.termIdentities rhs IS.empty) ps
     start = 1 + maximum (0 : IS.toList ids)
     step (serial,bindings) (n,_) =
       case lookup (X.nameHint n) definitions of
        Nothing -> error ("missing dependency " ++ B.unpack (X.nameHint n))
        Just definition -> let (next,term)=U.freshObject serial (strip definition) in (next,bindings++[(n,term)])
     (_,bindings)=foldl step (start,[]) ps
 in T.XWithData (O.declarations (O.context fragment)) (foldr (\(n,t) b->T.XLet n t b) rhs bindings)
collect definitions (_,fragment) = foldM (\values (name,_) -> do
 let (_,rhs)=findBinding (X.nameHint name) (O.body fragment)
     term=close definitions fragment rhs
 _ <- expect "independent final body check" (Checked.check term)
 pure (values ++ [(X.nameHint name,term)])) definitions (O.bindings fragment)
observe definitions (name,_,expected,_) = case expected of
 Nothing -> pure ()
 Just wanted -> case lookup name definitions of
  Nothing -> error "root absent"
  Just term -> do
   (env,_)<-expect "runtime preparation" (R.prepare False term)
   actual<-expect "runtime evaluation" (R.evaluate env (R.REnv M.empty) (X.erase term))
   case actual of R.RInteger n -> assert ("runtime "++B.unpack name) (n==wanted); _ -> error "integer expected"

sourceChecks root = do
 let scopes=M.fromList P.compareString [(n,IS.fromList (if n=="partialScope"||n=="sameDeps" then [0] else [0,1]))|(n,_,_,_)<-roots]
 candidate<-expect "source plan" (SI.prepareSourcePlan M.empty [] [cls] [("tagInt",instInt),("tagBool",instBool)] scopes
   [IS.fromList [0,1],IS.fromList [0,1]] [(n,T.Nothing,e)|(n,e,_,_)<-roots])
 plan<-case candidate of T.Just p->pure p; _->error "source fallback"
 let oldCache=B.literal (root++"/old"); newCache=B.literal (root++"/graph")
 (old,_,oldContracts)<-Old.compileSourceGroups "source-oracle" oldCache [] M.empty plan >>= expect "old source oracle"
 (cold,coldReport,contracts)<-CG.compileSourceGroups False "source-oracle" newCache [] M.empty plan >>= expect "new cold source query"
 assert "cold groups" (Old.inferredCount coldReport==fromIntegral (length cold) && Old.reusedCount coldReport==0)
 case cold of
  (group,fragment):_ -> finishHashChecks group fragment
  [] -> error "missing finish hash fixture"
 assert "contracts match legacy source oracle" (contractView contracts==contractView oldContracts)
 oldOpen<-mapM (\o->expect "legacy receipt" (U.objectChecked o) >>= expect "open legacy receipt" . O.fromChecked) old
 assert "same source group inventory" (length oldOpen==length cold)
 mapM_ (\(oldObject,(_,newObject))->do
   _<-expect "open final audit" (O.audit newObject)
   _<-expect "renamed checked receipt audit" (O.audit (snd(O.fresh 100000 newObject)))
   assert "same final parameter and export types" (let (a,_,b)=view oldObject;(c,_,d)=view newObject in a==c&&b==d)
   assert "same final body as legacy independent route" (let (_,a,_)=view oldObject;(_,b,_)=view newObject in a==b)) (zip oldOpen cold)
 values<-foldM collect [] cold
 mapM_ (observe values) roots
 mapM_ (\(n,_,_,slots)->case M.lookup P.compareString n contracts of
   T.Just c->assert "expected residual contract" (SI.contractClasses c==replicate slots "Tag")
   _->error "contract absent") roots
 (warm,warmReport,warmContracts)<-CG.compileSourceGroups True "source-oracle" newCache [] M.empty plan >>= expect "warm source query"
 assert "all source raw hits" (Old.inferredCount warmReport==0 && Old.reusedCount warmReport==fromIntegral (length cold))
 assert "warm final parity" (map (view.snd) cold==map (view.snd) warm && contractView contracts==contractView warmContracts)
 putStrLn "PASS source query raw reuse, evidence, protection, independent old contracts/bodies, and runtime oracle"

sourceChanges root = do
 let plain n e=(n,T.Nothing,e)
     ident=T.SLam "x" T.Nothing (T.SVar "x")
     caller=plain "greeting" (T.SLam "x" T.Nothing (app "getName" (T.SVar "x")))
     untouched=plain "untouched" ident
     ordinary ds members=(ds,[],[],M.fromList P.compareString [(n,IS.empty)|(n,_,_)<-members],[],members)
     body k=ordinary [] [plain "getName" (T.SLam "x" T.Nothing (add (T.SVar "x") (T.SIntLit k))),caller,untouched]
     typed ty annotation=ordinary [] [("getName",if annotation then T.Just(T.SAnnotation [] (T.SArrow ty ty)) else T.Nothing,ident),caller,untouched]
     datatype field value=ordinary [T.DataDecl "User" [] [T.ConstructorDecl "User" [T.Applied field []]]]
       [plain "value" (T.SApp(T.SConstructor "User") value),plain "copy" (T.SVar "value"),untouched]
     recursive yes=ordinary [] [plain "f" (T.SLam "x" T.Nothing(app "g"(T.SVar "x"))),
       plain "g" (if yes then T.SLam "x" T.Nothing(app "f"(T.SVar "x")) else ident),untouched]
     scoped instances=let keys=IS.fromList [0..fromIntegral(length instances)-1] in
       ([],[cls],instances,M.fromList P.compareString [("f",keys),("untouched",IS.empty)],replicate(length instances) keys,
        [plain "f"(tag(T.SBoolLit True)),untouched])
     cases=[("body",[body 1,body 2]),("type",[typed int True,typed bool True]),
       ("protection",[typed int True,typed int False]),
       ("datatype",[datatype "Int"(T.SIntLit 1),datatype "Bool"(T.SBoolLit True)]),
       ("scc",[recursive True,recursive False,recursive True]),
       ("scope",[scoped [],scoped[("tagBool",instBool)],scoped []]),
       ("scope-order",[scoped[("tagInt",instInt),("tagBool",instBool)],scoped[("tagBool",instBool),("tagInt",instInt)]])]
     rawHashes (Old.QueryReport _ _ groups)=[h|Old.GroupResult _ _ _ _ h<-groups]
 mapM_ (\(label,versions)->mapM_ (\(version,(ds,classes,instances,scopes,instanceScopes,members))->do
   prepared<-expect "changed source plan"(SI.prepareSourcePlan M.empty ds classes instances scopes instanceScopes members)
   plan<-case prepared of T.Just p->pure p;_->error "changed source fallback"
   let identity=B.literal("source-changes/"++label)
       cache=B.literal(root++"/"++label)
       cleanCache=B.literal(root++"/"++label++"-clean-"++show version)
   (inc,report,contracts)<-CG.compileSourceGroups True identity cache [] M.empty plan >>= expect "incremental source change"
   (clean,_,cleanContracts)<-CG.compileSourceGroups True identity cleanCache [] M.empty plan >>= expect "clean source change"
   (_,cleanReport,_)<-CG.compileSourceGroups True identity cleanCache [] M.empty plan >>= expect "clean source warm report"
   assert "incremental/clean source bodies and contracts"(map(view.snd) inc==map(view.snd) clean && contractView contracts==contractView cleanContracts)
   assert "incremental/clean raw SHA"(rawHashes report==rawHashes cleanReport)
   mapM_ (expect "changed source body audit" . O.audit . snd) inc
   (warm,warmReport,_)<-CG.compileSourceGroups True identity cache [] M.empty plan >>= expect "changed source warm"
   assert "changed source all warm hits"(Old.inferredCount warmReport==0 && length inc==length warm && map(view.snd) inc==map(view.snd) warm)
   if label=="body" && version==1 then assert "source body edit one inferred"(Old.inferredCount report==1) else pure ()
   putStrLn("PASS source change "++label++" "++show version)) (zip [0::Int ..] versions)) cases

finishHashChecks group fragment = do
 let refs = [("a","version-a"),("b","version-b")]
     content rs = G.hashValue (CG.rawValue rs group fragment) >>= expect "canonical fragment content"
 raw <- content refs
 let previous = G.QueryNode "raw" raw [] (T.Just raw)
     finalHash mode body node rs =
       CG.finishContentHash mode group body fragment node refs rs
 kept <- finalHash False SI.KeepRawBody previous refs >>= expect "retained raw content"
 checked <- finalHash True SI.KeepRawBody previous refs >>= expect "verified retained content"
 adapted <- finalHash False (SI.AdaptedBody fragment) previous refs >>= expect "identical adapted content"
 assert "equal final values keep one SHA through either recipe" (raw == kept && raw == checked && raw == adapted)
 reordered <- finalHash False SI.KeepRawBody previous (reverse refs) >>= expect "changed environment"
 expected <- content (reverse refs)
 assert "ordered environment is part of the final fragment" (reordered == expected && reordered /= raw)
 mismatch <- finalHash True SI.KeepRawBody (G.QueryNode "raw" "incorrect" [] T.Nothing) refs
 assert "ICH verifies the retained fragment" (case mismatch of T.Left _ -> True; _ -> False)

graphChecks root = do
 let path=B.literal (root++"/graph-controls"); config="compiler-a/builtin-a/checker-1"
 s<-G.begin path config >>= expect "start graph"
 (input,s1)<-G.record (G.inputKey (G.key "Prepared" (U.pack ["f"]))) [] False (W.VText "old body") s >>= expect "input"
 (binding,s2)<-G.record (G.key "Binding" "f") [G.edge input] True (W.VText "Int -> Int / unprotected") s1 >>= expect "binding"
 (caller,s3)<-G.record (G.key "InferScc" (U.pack ["g"])) [G.edge binding] True (W.VText "caller body") s2 >>= expect "caller"
 _<-G.publish s3 >>= expect "publish controls"
 next<-G.begin path config >>= expect "reopen controls"
 (changed,next1)<-G.record (G.inputKey (G.key "Prepared" (U.pack ["f"]))) [] False (W.VText "new body") next >>= expect "changed input"
 assert "changed source invalidates binding" (case fst(G.validate (G.nodeKey binding) next1) of T.Nothing->True;_->False)
 (equal,next2)<-G.record (G.nodeKey binding) [G.edge changed] True (W.VText "Int -> Int / unprotected") next1 >>= expect "equal recomputed contract"
 assert "red/green result equality" (G.nodeHash binding==G.nodeHash equal)
 assert "unchanged contract preserves caller" (case fst (G.validate (G.nodeKey caller) next2) of T.Just _->True;_->False)
 changedCompiler<-G.begin path "compiler-b/builtin-a/checker-1" >>= expect "compiler invalidation"
 changedBuiltins<-G.begin path "compiler-a/builtin-b/checker-1" >>= expect "builtin invalidation"
 assert "identity changes cold miss" (all (\session->case fst(G.validate (G.nodeKey caller) session) of T.Nothing->True;_->False) [changedCompiler,changedBuiltins])
 let actualBuiltinChange=T.DataDecl "ChangedBuiltin" [] [T.ConstructorDecl "ChangedBuiltin" []]:Data.builtinDeclarations
 assert "actual dictionary changes identity with fixed compiler" (Old.sourceFormatFor actualBuiltinChange/=Old.sourceQueryFormat)
 let poison=G.QueryNode (G.key "Q" "poison") (error "later dependency forced after red edge") [] T.Nothing
     old=M.fromList P.compareString [(G.key "Q" "caller",G.QueryNode (G.key "Q" "caller") "hash" [(G.nodeKey changed,"different"),(G.key "Q" "poison","poison")] T.Nothing),(G.key "Q" "poison",poison)]
     selected=G.Session path config "" old (M.fromList P.compareString [(G.nodeKey changed,changed)]) M.empty
 assert "old read order short-circuits after first changed edge" (case fst (G.validate (G.key "Q" "caller") selected) of T.Nothing->True;_->False)
 let cyclic=M.fromList P.compareString [(G.key "Q" "a",G.QueryNode (G.key "Q" "a") "h" [(G.key "Q" "b","h")] T.Nothing),(G.key "Q" "b",G.QueryNode (G.key "Q" "b") "h" [(G.key "Q" "a","h")] T.Nothing)]
 assert "query cycle rejected" (case fst(G.validate (G.key "Q" "a") (G.Session path config "" cyclic M.empty M.empty)) of T.Nothing->True;_->False)
 putStrLn "PASS graph read order, red/green propagation, compiler/builtin namespace, and cycle handling"

formalChecks file = do
 let directory=reverse(dropWhile (/='/') (reverse file))
 entries<-Artifact.loadInterfaces [B.literal file] >>= expect "formal dependency closure"
 objects<-mapM (\(path,iface)->do
   object<-Artifact.readObject (Artifact.objectPath path) iface >>= expect "different executable reads checked object"
   mh<-P.fileDigest path
   oh<-P.fileDigest (Artifact.objectPath path)
   pure (Libraries.LibraryObject mh oh object)) entries
 let names=[n|(_,iface)<-entries,n<-Artifact.crateModules iface,not(Modules.isBuiltinModule n)]
 sources<-mapM (\name->do
   let path=B.literal(directory++B.unpack name++".hs")
   source<-P.readFile path
   parsed<-expect "prepared source parse" (Parser.parseModule path source)
   digest<-P.fileDigest path
   pure(Libraries.LibrarySource name path source digest (Modules.sourceSyntax parsed))) names
 identity<-P.fileDigest(B.literal file)
 raw<-expect "prepared library open-object admission" (Libraries.prepareFresh identity T.ImplicitPrelude sources objects)
 _<-expect "prepared native literal compatibility" (Libraries.nativeLibrary raw)
 let (declarations,expression)=Literal.rawLibraryPieces raw
 assert "prepared literal rendered" (P.stringLength declarations>0 && P.stringLength expression>0)
 putStrLn "PASS cross-executable formal loading and legacy prepared-native literal compatibility"

loweredChecks root = do
 let members=[("copy",T.Nothing,T.SSourceDefinition(T.SIntLit 42)),
              ("readCopy",T.Nothing,add(T.SVar "copy")(T.SIntLit 1))]
     scopes=M.fromList P.compareString [(n,IS.empty)|(n,_,_)<-members]
 plan<-expect "copied-definition routing"(SI.prepareSourcePlan M.empty [] [] [] scopes [] members)
 assert "copied definition selects actual whole lowered fallback"(case plan of T.Nothing->True;_->False)
 lowered<-expect "fallback lowering"(Inference.lowerDeclarationsWithImports M.empty [] [] [] scopes [] members)
 executable<-P.getExecutablePath; compiler<-P.fileDigest executable
 let path=B.literal(root++"/lowered"); ds=Inference.loweredData lowered; values=Inference.loweredValues lowered
 cold<-CG.compileLowered True "copied-fallback" compiler path [] ds values >>= expect "lowered graph cold"
 let (objects,report,_,session)=CG.result cold
 _<-G.publish session >>= expect "lowered transaction"
 assert "lowered cold count"(Old.inferredCount report==2)
 (legacy,_)<-Old.compileGroups "copied-fallback" (B.literal(root++"/lowered-legacy")) [] ds values >>= expect "old lowered oracle"
 expected<-mapM (\o->expect "old lowered check"(U.objectChecked o) >>= expect "old lowered open" . O.fromChecked) legacy
 assert "lowered final parity"(map view expected==map(view.snd) objects)
 linked<-foldM collect [] objects
 observe linked ("readCopy",T.SIntLit 0,Just 43,0)
 warm<-CG.compileLowered True "copied-fallback" compiler path [] ds values >>= expect "lowered graph warm"
 let (reused,warmReport,_,_)=CG.result warm
 assert "lowered warm parity"(Old.inferredCount warmReport==0 && Old.reusedCount warmReport==2 && map(view.snd) objects==map(view.snd) reused)
 putStrLn "PASS actual copied-definition fallback, legacy parity, runtime result, and warm graph reuse"

sessionTransactionChecks root = do
 let folder=root++"/session-transaction"
     source=folder++"/Tx.hs"; spec=folder++"/crate.spec"; cache=folder++"/cache"
     pointer=cache++"/query-graph-v2/CURRENT"
     header="-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule Tx where { import MLF.Primitive; "
     program value rhs=header++"ok :: Int; ok = "++value++"; bad :: Int; bad = "++rhs++" }\n"
     compile label=Session.compileSpecFile (B.literal spec) (B.literal(folder++"/"++label))
     failed label=do
       result<-compile label
       case result of
        T.Left e->assert "actual type failure reached inference" ("mismatch" `isInfixOf` B.unpack e)
        T.Right _->error "invalid SCC accepted"
 createDirectoryIfMissing True folder
 writeFile spec (B.unpack(U.pack ["MLF-CRATE-1","session-transaction","","true",
   U.pack[U.pack["Tx",B.literal source]],"",B.literal cache,B.literal(folder++"/builtin/unit")]))
 writeFile source (program "1" "if ok then 2 else 3")
 failed "cold-failure"
 exists<-doesFileExist pointer
 assert "failed crate does not publish its successful prerequisite" (not exists)
 writeFile source (program "1" "ok")
 _<-compile "good" >>= expect "same-process retry releases session lock"
 firstReport<-readFile(folder++"/good.queries")
 assert "retry infers both unpublished groups" ("\"inferred_groups\":2" `isInfixOf` firstReport)
 before<-BS.readFile pointer
 original<-mapM (BS.readFile . ((folder++"/good")++)) [".mlfci",".mlfco"]
 writeFile source (program "2" "if ok then 2 else 3")
 failed "warm-failure"
 after<-BS.readFile pointer
 assert "failed replacement retains current generation" (before==after)
 writeFile source (program "1" "ok")
 _<-compile "restored" >>= expect "same-process warm retry releases session lock"
 restoredReport<-readFile(folder++"/restored.queries")
 restored<-mapM (BS.readFile . ((folder++"/restored")++)) [".mlfci",".mlfco"]
 assert "restored generation fully reuses both groups" ("\"inferred_groups\":0" `isInfixOf` restoredReport && "\"reused_groups\":2" `isInfixOf` restoredReport)
 assert "restored final artifacts are exact" (original==restored)
 putStrLn "PASS actual Session same-process failure/retry, lock release, whole-crate publication and retained generation"

main = do
 arguments <- getArgs
 let directory=head arguments
 createDirectoryIfMissing True directory
 graphChecks directory
 sourceChecks directory
 sourceChanges directory
 loweredChecks directory
 sessionTransactionChecks directory
 case tail arguments of []->pure (); [file]->formalChecks file; _->error "expected directory [formal-interface]"
