{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module PublicControls where
import Prelude
import Control.Monad (forM_)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.Constraint as C
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Set as Set
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS
import qualified FrozenConstraint as FC
import qualified SessionGraftFixtures as A
import qualified SessionFieldFixtures as F
import SessionOracle
import TransactionOracle (checkTransactionalOutcome)

isRight :: T.Either a b -> Bool
isRight (T.Right _)=True
isRight _=False
bind :: T.Either a b -> (b -> T.Either a c) -> T.Either a c
bind (T.Left e) _=T.Left e
bind (T.Right x) f=f x
checkGraph :: String -> T.Either B.String T.Graph -> T.Either B.String T.Graph -> IO ()
checkGraph label old new=case(old,new)of
 (T.Left a,T.Left b)->assert(label++" exact first error")(B.v_eqString a b)
 (T.Right a,T.Right b)->do
  assert(label++" full physical graph, links and counter")(sameGraphPhysical a b)
  _<-right(label++" frozen graph check")(FG.validateGraph b)
  _<-right(label++" current graph check")(G.validateGraph b)
  pure()
 (T.Left e,T.Right _)->errorWithoutStackTrace(label++" accepted frozen rejection "++B.unpack e)
 (T.Right _,T.Left e)->errorWithoutStackTrace(label++" rejected frozen success "++B.unpack e)

-- Literal transcription of the finite repository GraphValidation corpus.
-- Candidate validation never chooses which graphs enter unification controls.
smallGraphs :: [T.Graph]
smallGraphs=[T.Graph(IM.fromList
 [(0,T.Node(T.GGen 1)T.Nothing T.Flexible),(1,T.Node top parent T.Flexible),
  (2,T.Node left lp T.Flexible),(3,T.Node right rp T.Rigid)])aliases 6
 |top<-[T.GArr 2 3,T.GArr 2 2,T.GTyApp 2 3,T.GCon "Pair"[2,3],T.GArr 5 3],
 left<-[T.GBot,T.GTyCon "F"(T.KArrow T.Star T.Star),T.GArr 3 3,T.GGen 3],
 right<-[T.GBot,T.GTyCon "G"(T.KArrow T.Star T.Star),T.GArr 2 2,T.GArr 9 9],
 parent<-[T.Nothing,T.Just 0,T.Just 2],lp<-[T.Nothing,T.Just 0,T.Just 1,T.Just 3,T.Just 9],
 rp<-[T.Nothing,T.Just 0,T.Just 1,T.Just 2,T.Just 9],
 aliases<-[IM.empty,IM.fromList[(5,4),(4,2)]]]
equations :: [[(Integer,Integer)]]
equations=[[],[(1,2)],[(1,3)],[(2,3)],[(2,2)],[(0,1)],[(1,2),(2,3)],[(2,3),(1,2)],[(3,2),(2,1)]]
withFlags :: T.Graph -> T.Flag -> T.Flag -> T.Flag -> T.Graph
withFlags g a b c=T.Graph(IM.mapWithKey(\n v->T.Node(FG.tag v)(FG.binder v)
 (case n of 1->a;2->b;3->c;_->FG.flag v))(FG.nodes g))(FG.links g)(FG.nextId g)
inputs :: [(T.Graph,[(Integer,Integer)])]
inputs=[(withFlags g a b c,es)|g<-filter(isRight.FG.validateGraph)smallGraphs,
 a<-[T.Flexible,T.Rigid],b<-[T.Flexible,T.Rigid],c<-[T.Flexible,T.Rigid],es<-equations]

-- Determine unchanged/changed binder premises with the complete frozen PURE
-- sparse binder construction, then classify the ACTUAL dense rebinder outcome.
-- A rejected initial graph, first-order equation, binder build, or raising never
-- enters a bucket. Rejection buckets admit only the four downstream permission
-- errors from FrozenGraph.rebind, not a final validateGraph/unify rejection.
permissionErrors :: [String]
permissionErrors=["cannot instantiate a rigid or protected type variable",
 "cannot raise a protected type variable","cannot weaken a protected type variable",
 "cannot merge distinct protected type variables"]
raisedClassification :: T.Graph -> [(Integer,Integer)] -> Maybe (Bool,Bool,String)
raisedClassification old es=case FG.validateGraph old of
 T.Left _->Nothing
 T.Right()->case FG.denseBounds old of
  T.Nothing->Nothing
  T.Just _->case FG.checkedFirstOrder es old of
   T.Left _->Nothing
   T.Right raw->
    let skeleton=FG.canonicalize raw
        classes=FG.classesIndex old skeleton
        parents=FG.parentsIndex skeleton
        grafted=FG.graftedNodes old skeleton
        candidates=FG.candidateIndex old skeleton classes parents grafted
        dependencies=IM.mapWithKey(\n cs->IS.union(IS.fromList cs)(IM.findWithDefault IS.empty n parents))candidates
    in case FG.rebuildBinders candidates dependencies of
     T.Left _->Nothing
     T.Right tree->case FG.mapE(FG.raisedBinder old skeleton tree)(IM.toList(FG.nodes old))of
      T.Left _->Nothing
      T.Right pairs->
       let same=all(\(n,b)->sameMaybe(==) b(FG.binder(FG.nodeAt old n)))pairs
       in case FG.rebind old skeleton of
        T.Right _->Just(same,True,"")
        T.Left error->let message=B.unpack error
                      in if message `elem` permissionErrors then Just(same,False,message) else Nothing

rawCase :: String -> T.Graph -> [(Integer,Integer)] -> IO Bool
rawCase label g es=do
 let expected=FG.unify es g;actual=G.unify es g
 checkGraph(label++" raw")expected actual
 checkOutcome(label++" indexed")True
  (bind(FS.prepare g)(FS.solverUnify es))
  (bind(S.prepare g)(S.solverUnify es))
 pure(isRight expected)
finiteCorpus :: IO ()
finiteCorpus=do
 assert "literal 12000 validation corpus"(length smallGraphs==12000)
 forM_(zip[0::Int ..]smallGraphs)$ \(i,g)->case(FG.validateGraph g,G.validateGraph g)of
  (T.Left a,T.Left b)->assert("validation error "++show i)(B.v_eqString a b)
  (T.Right(),T.Right())->pure()
  _->errorWithoutStackTrace("validation decision "++show i)
 outcomes<-mapM(\(i,(g,es))->rawCase("finite "++show i)g es)(zip[0::Int ..]inputs)
 let accepted=length(filter id outcomes)
     premises=[raisedClassification g es|(g,es)<-inputs]
     unchanged=length[()|Just(True,_,_)<-premises]
     changed=length[()|Just(False,_,_)<-premises]
     buckets=[length[()|Just(p,ok,_)<-premises,p==same,ok==wanted]|same<-[True,False],wanted<-[True,False]]
     rejectionCounts=[(message,length[()|Just(_,False,observed)<-premises,observed==message])|message<-permissionErrors]
 assert "nonvacuous success and failure corpus"(accepted>100&&accepted<length inputs-100)
 assert "both permission reuse and invalidation premises exercised"(unchanged>100&&changed>0)
 assert "reuse and invalidation each exercise acceptance and rejection"(all(>0)buckets)
 putStrLn("PASS finite validation=12000 unification="++show(length inputs)++" accepted="++show accepted++" unchanged-binders="++show unchanged++" changed-binders="++show changed)
 putStrLn("PASS frozen binder-premise outcomes [same-success,same-rejection,changed-success,changed-rejection]="++show buckets)
 putStrLn("PASS frozen dense-rebind permission rejection inventory="++show rejectionCounts)
 let transforms=[("offset-positive",\n->n+37),("offset-negative",\n->n-37),
                 ("offset-huge",\n->n+10^40),("offset-huge-negative",\n->n-10^40),
                 ("sparse",\n->n*100003-9001)]
 forM_(zip[0::Int ..](take 80 inputs))$ \(i,(g,es))->forM_ transforms$ \(name,image)->do
  _<-rawCase(name++show i)(A.rename image g)(map(\(a,b)->(image a,image b))es)
  pure()
 putStrLn "PASS first 80 frozen cases x five identity layouts = 400 renamed raw/indexed executions"


-- Independently authored legal graphs establish each branch premise explicitly.
-- Their only changing fields are a parent flag and the second bottom's binder.
-- With a rigid arrow parent, a local flexible bottom is protected (Red).
-- Equal binders reject a distinct protected merge; unequal binders reject raising
-- that protected bottom to the gen. A flexible parent allows both operations.
permissionGraph :: T.Flag -> Bool -> T.Graph
permissionGraph top changed=T.Graph(IM.fromList
 [(0,T.Node(T.GGen 1)T.Nothing T.Flexible),
  (1,T.Node(T.GArr 2 3)(T.Just 0)top),
  (2,T.Node T.GBot(T.Just 1)T.Flexible),
  (3,T.Node T.GBot(T.Just(if changed then 0 else 1))T.Flexible)])IM.empty 4
permissionPremiseControls :: IO ()
permissionPremiseControls=do
 forM_[("same-success",T.Flexible,False,True,""),
       ("same-protected-merge",T.Rigid,False,False,"cannot merge distinct protected type variables"),
       ("changed-success",T.Flexible,True,True,""),
       ("changed-protected-raise",T.Rigid,True,False,"cannot raise a protected type variable")]$ \(label,flag,changed,wanted,error)->do
  let original=permissionGraph flag changed
  _<-right(label++" authored legal graph")(FG.validateGraph original)
  assert(label++" independent exact dense permission premise and result")
   (raisedClassification original[(2,3)]==Just(not changed,wanted,error))
  accepted<-rawCase label original[(2,3)]
  assert(label++" authored acceptance")(accepted==wanted)
 putStrLn "PASS four authored legal dense permission cases: reuse/fallback x success/exact protected rejection"

bottom :: T.Graph
bottom=T.Graph(IM.fromList[(0,T.Node(T.GGen 1)T.Nothing T.Flexible),
 (1,A.node(T.GCon "Unit"[])0 T.Rigid),(2,A.node(T.GGen 3)0 T.Flexible),
 (3,A.node T.GBot 2 T.Flexible),(4,A.node(T.GGen 5)0 T.Flexible),(5,A.node T.GBot 4 T.Flexible)])IM.empty 6
shaped :: T.Graph
shaped=A.replace 8(A.node(T.GArr 9 10)7 T.Flexible)(A.replace 9(A.node T.GBot 8 T.Flexible)
 (A.replace 10(A.node(T.GArr 9 11)8 T.Rigid)(A.replace 11(A.node(T.GCon "Int"[])10 T.Rigid)A.poly)))
ground :: T.Graph
ground=A.replace 3(A.node(T.GCon "Int"[])2 T.Rigid)(A.without[4,5,6]A.poly)
instanceStep :: Integer -> Integer -> T.SolveStep
instanceStep a b=T.Instantiate(T.Edge a b)
traceCases :: [(String,T.Graph,[(Integer,Integer)],[T.SolveStep])]
traceCases=[(label,g,[],[instanceStep 2 8])|(label,_,g)<-A.cases]++
 [("ground graft",ground,[],[instanceStep 2 8]),
  ("ground already",A.replace 8(A.node(T.GCon "Int"[])7 T.Flexible)ground,[],[instanceStep 2 8]),
  ("congruent retained",shaped,[],[instanceStep 2 8]),
  ("congruent fallback",A.replace 9(A.node T.GBot 7 T.Flexible)shaped,[],[instanceStep 2 8]),
  ("selected field",F.base,[],[T.ProjectCase[(2,4)]]),("empty fields",F.base,[],[T.ProjectCase[]]),
  ("ineligible field",FG.setNode 2(T.Node(T.GArr 3 5)(T.Just 0)T.Flexible)F.base,[],[T.ProjectCase[(2,4)]]),
  ("later descriptor",F.base,[],[T.ProjectCase[(2,4),(2,999)]]),
  ("duplicate descriptor",F.base,[],[T.ProjectCase[(2,4),(2,4)]]),
  ("replay descriptor",F.base,[],[T.ProjectCase[(2,4)],T.ProjectCase[(2,4)]]),
  ("initial reflexive",A.poly,[(4,4)],[instanceStep 2 8]),
  ("initial merge",A.poly,[(4,8)],[instanceStep 2 8]),
  ("initial missing",A.poly,[(999,4)],[instanceStep 2 8]),
  ("ordered missing",A.poly,[(999,4),(998,4)],[instanceStep 2 8])]
traceOne :: (String,T.Graph,[(Integer,Integer)],[T.SolveStep]) -> IO ()
traceOne(label,g,es,steps)=do
 let constraints=T.Constraints g(errorWithoutStackTrace "unused typed skeleton")es steps
 checkTransactionalOutcome(label++" complete prepared")(FC.solvePrepared constraints)(C.solvePrepared constraints)
 let old=bind(FS.prepare g)(FS.solverUnify es);new=bind(S.prepare g)(S.solverUnify es)
 checkOutcome(label++" initial")True old new
 walk label 0 old new steps
 where
 walk _ _ _ _ []=pure()
 walk name i(T.Right a)(T.Right b)(step:rest)=do
  let expected=FC.evaluateStep a step;actual=C.evaluateStep b step
  checkOutcome(name++" transition "++show i)True expected actual
  -- Repeat from the same immutable pre-state after the first result, including
  -- rejection. A leaked mutation or half-committed ST update changes this.
  checkOutcome(name++" repeat/rollback "++show i)True expected(C.evaluateStep b step)
  checkSolver(name++" preserved source state "++show i)True a b
  walk name(i+1)expected actual rest
 walk _ _ _ _ _=pure()

edgeControls :: IO ()
edgeControls=do
 let empty=T.Graph IM.empty IM.empty 0
     single=T.Graph(IM.singleton 0(T.Node T.GBot T.Nothing T.Flexible))IM.empty 1
     missing=FG.setNode 3(A.node(T.GArr 4 999)2 T.Flexible)A.poly
     cyclic=FG.setNode 3(A.node(T.GArr 3 4)2 T.Flexible)A.poly
     aliased=T.Graph(FG.nodes A.poly)(IM.fromList[(11,2),(12,8),(13,12)])14
 forM_[ ("empty",empty,[]),("single non-gen root",single,[]),
         ("missing edge",missing,[(3,8)]),("cycle",cyclic,[(3,8)]),
         ("aliases",aliased,[(13,4)]),("missing first",A.poly,[(999,4),(998,4)]),
         ("later missing priority",A.poly,[(3,6),(999,4)]),
         ("rigid rejection",A.replace 4(A.node T.GBot 2 T.Rigid)A.poly,[(4,6)])]$ \(label,g,es)->do
  _<-rawCase label g es;pure()
 old<-right "rollback prepare"(FS.prepare A.poly)
 new<-right "rollback candidate prepare"(S.prepare A.poly)
 let failure=S.solverUnify[(999,4),(998,4)]new
 checkOutcome "exact missing rejection" True(FS.solverUnify[(999,4),(998,4)]old)failure
 assert "literal missing-first error"(case failure of T.Left e->B.unpack e=="missing graph node 999";_->False)
 checkOutcome "success after rejected attempt on same state" True(FS.solverUnify[(4,8)]old)(S.solverUnify[(4,8)]new)
 checkSolver "failed attempt preserved original"True old new
 let forged=T.Solver(S.graph new)(IM.insert 999(IS.singleton 0)(S.structuralParents new))(S.bindingChildren new)(S.scopeIndex new)
 checkOutcome "forged disconnected index audit"True(FS.finishNormalized forged)(S.finishNormalized forged)
 assert "literal index audit rejection"(case S.finish forged of T.Left e->B.unpack e=="incremental graph index disagrees with the graph";_->False)
 checkOutcome "empty selected field preserves final index audit"True(FS.projectCaseFields[]forged)(S.projectCaseFields[]forged)
 putStrLn "PASS eight boundary cases, ordered exact rejection, retry/rollback and forged-index final audit"

programs :: [(B.String,Bool)]
programs=[("\\x -> x",True),("\\x -> x x",False),("\\f x -> f x",True),
 ("let id = \\x -> x in let a = id 42 in id true",True),
 ("(\\(f : forall a. a -> a) -> f f) (\\x -> x)",True),
 ("let choose = ((\\x y -> x) : forall a. a -> a -> a) in let id = \\x -> x in let g = choose id in g g",True),
 ("(\\x -> x) : forall (a >= forall b. b -> b). a -> a",True),
 ("(\\x -> x) : Int -> Bool",False)]
parsedConstraints :: IO ()
parsedConstraints=do
 forM_(zip[0::Int ..]programs)$ \(i,(source,wanted))->do
  expression<-right ("parsed expression "++show i)(Parser.parseExpr "<frozen control>"source)
  canonical<-right ("canonical source "++show i)(Classes.canonicalSourceProgram Set.empty(T.SProgram[]expression))
  (core,_)<-right ("production source lowering "++show i)(Classes.lowerClasses canonical)
  constraints<-right ("frozen generated constraint "++show i)(FC.generateProgram core)
  let old=FC.solvePrepared constraints;new=C.solvePrepared constraints
  assert("hand source acceptance "++show i)(isRight old==wanted)
  checkTransactionalOutcome("parsed source "++show i) old new
 putStrLn "PASS eight parsed-expression constraints with handwritten success/rejection expectations"

main :: IO ()
main=do
 finiteCorpus
 permissionPremiseControls
 assert "28 fixed public traces"(length traceCases==28)
 mapM_ traceOne traceCases
 putStrLn "PASS 28 finite public solver full-state traces and repeated failure/success transitions"
 edgeControls
 parsedConstraints
 A.main
 F.main
 putStrLn "{\"complete\":true,\"public_trace_cases\":28,\"validation_cases\":12000,\"renamed_cases\":400,\"parsed_expression_cases\":8,\"authored_permission_cases\":4,\"a1_private_controls_applicable\":false,\"candidate_output_used_for_expectations\":false}"
