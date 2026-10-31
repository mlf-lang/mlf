{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless, forM_)
import Data.IORef
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Dependency as Dependency
import qualified Bootstrap.Separate as U
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

-- Independent scalar-length framing. Only AST expression positions are
-- expanded: strings containing framed-looking text must remain opaque.
pack :: [String] -> String
pack = concatMap (\s -> show (length s) ++ ":" ++ s)
unpack :: String -> [String]
unpack "" = []
unpack text = case break (==':') text of
  (digits,':':rest) -> let n=read digits; (value,tail)=splitAt n rest
                     in if length value==n then value:unpack tail else error "short framed field"
  _ -> error "invalid frame"
expandExpression :: [String] -> String -> String
expandExpression scopes text = pack $ case unpack text of
  ["wanted",dictionary,index] -> ["wanted",dictionary,scopes !! read index]
  ["lambda",name,annotation,body] -> ["lambda",name,annotation,ex body]
  ["apply",a,b] -> ["apply",ex a,ex b]
  ["let",name,a,b] -> ["let",name,ex a,ex b]
  [tag,body,annotation] | tag `elem` ["annotate","signature"] -> [tag,ex body,annotation]
  ["case",body,branches] -> ["case",ex body,many alternative branches]
  ["source-definition",body] -> ["source-definition",ex body]
  ["call-site",label,span,body] -> ["call-site",label,span,ex body]
  ["shared-bind",pattern,a,b,c,d] -> ["shared-bind",pattern,ex a,ex b,ex c,ex d]
  ["do",statements,body] -> ["do",many statement statements,ex body]
  ["equations",rows] -> ["equations",many equation rows]
  ["letrec",bindings,body] -> ["letrec",many recursive bindings,ex body]
  ["checked",ty,body] -> ["checked",ty,ex body]
  fields -> fields
  where
    ex=expandExpression scopes
    many f=pack . map (pack . f . unpack) . unpack
    alternative ["alternative",p,b]=["alternative",p,ex b]
    alternative _=error "alternative"
    equation ["equation",p,b]=["equation",p,ex b]
    equation _=error "equation"
    recursive ["recursive-infer",n,b]=["recursive-infer",n,ex b]
    recursive ["recursive",n,a,b]=["recursive",n,a,ex b]
    recursive _=error "recursive"
    statement ["do-bind",p,b]=["do-bind",p,ex b]
    statement ["do-then",b]=["do-then",ex b]
    statement ["do-let",n,a,b]=["do-let",n,a,ex b]
    statement ["do-letrec",bs]=["do-letrec",many recursive bs]
    statement _=error "statement"
expandQuery text = case unpack (B.unpack text) of
  ["MLF-SOURCE-CRATE-QUERY-6",crate,compiler,lowered,bindings,context,source,contracts,table] ->
    let scopes=unpack table
        member row=case unpack row of
          ["member",name,annotation,body] -> pack ["member",name,annotation,expandExpression scopes body]
          _ -> error "member"
        members=pack . map member . unpack
        group=case unpack source of
          tag:original:metadata -> pack (tag:members original:metadata)
          _ -> error "source group"
    in B.literal (pack ["MLF-SOURCE-CRATE-QUERY-5",crate,compiler,members lowered,bindings,context,group,contracts])
  _ -> error "source query version or inventory"
-- Frozen v5 envelope, with the pre-existing structural encoders as the oracle.
legacyQuery crate compiler prepared contracts context =
  let observed=Set.fromList P.compareString
        (map fst (SI.groupBindings prepared) ++ map fst (SI.groupCandidateBindings prepared) ++
         concatMap (Dependency.valueNames . Dependency.observeDeclaration) (SI.groupOriginal prepared))
      relevant=M.filterWithKey (\name _ -> Set.member P.compareString name observed) contracts
  in Q.node "MLF-SOURCE-CRATE-QUERY-5"
       [crate,compiler,Q.list (Q.encodeMember . Q.canonicalMember) (SI.groupMembers prepared),
        Q.list Q.encodeBinding (SI.groupBindings prepared),context,Q.encodeSourceGroup prepared,
        Q.list Q.encodeSourceContract (M.toList relevant)]

annotation=T.SAnnotation ["a"] (T.SForall T.Flexible "a" T.SBottom (T.SArrow (T.STVar "a") (T.STVar "a")))
scope=[(T.GivenEvidence,"given"),(T.SuperclassEvidence,"super"),(T.InstanceEvidence,"instance")]
wanted=T.SWanted "Dict" scope
span0=T.SourceSpan "package" "Module" "source.hs" 1 2 3 4
patterns=[T.SConstructorPattern "C" [T.Just "x",T.Nothing],T.SDefaultPattern (T.Just "x"),
  T.SNestedPattern "C" [T.SIntPattern 2],T.SAnnotatedPattern "x" annotation,
  T.SAsPattern "x" (T.SLazyPattern (T.SStringPattern "quoted\n\"")),
  T.SOverloadedStringPattern (T.ScalarString "α😀") "eq" "fromString",
  T.SOverloadedStringPattern (T.CharString [97,55296]) "eq" "fromString",T.SBoolPattern True]
expressions=[T.SVar "x",T.SConstructor "C",T.SLam "x" (T.Just annotation) wanted,
  T.SApp wanted wanted,T.SLet "x" wanted wanted,T.SAnn wanted annotation,T.SSignature wanted annotation,
  T.SIntLit (-42),T.SDoubleLit (-0.0),T.SBoolLit False,T.SStringLit "6:wanted4:Dict1:0\0α😀",
  T.SPrimitive T.PAddInt,T.SCase wanted [T.SAlternative p wanted|p<-patterns],
  T.SSourceDefinition wanted,T.SCallSite "call" span0 wanted,
  T.SSharedBind (head patterns) wanted wanted wanted wanted,
  T.SDo [T.SDoBind (head patterns) wanted,T.SDoThen wanted,T.SDoLet "x" T.Nothing wanted,
         T.SDoLetRec [("f",T.CheckRecursive annotation,wanted)]] wanted,
  T.SEquations [(patterns,wanted)],
  T.SLetRec [("f",T.InferRecursive,wanted),("g",T.CheckRecursive annotation,wanted)] wanted,
  wanted,T.SChecked (T.SCon "Int" []) wanted]
prepared body = let members=[("value",T.Nothing,body)] in
  SI.PreparedGroup members members [] M.empty [("value",[],False)] T.Nothing []
query body=Q.sourceQueryKeyWithContext "crate" "compiler" (prepared body) M.empty "datatype-context"
main = do
  count<-newIORef (0::Int)
  let check label ok=do unless ok (error label);modifyIORef' count (+1)
  forM_ (zip [0::Int ..] expressions) $ \(index,body)->do
    let label=show index; p=prepared body
    check ("linear structural expression "++label)
      (Q.renderKey M.empty (Q.expressionKey Q.inlineScopeKey body)==Q.encodeExpression body)
    check ("pooled query reconstructs exact legacy inputs "++label)
      (expandQuery (query body)==legacyQuery "crate" "compiler" p M.empty "datatype-context")
  let variants=[T.SWanted "OtherDict" scope,
        T.SWanted "Dict" (reverse scope),T.SWanted "Dict" ((T.InstanceEvidence,"given"):tail scope),
        T.SWanted "Dict" ((T.GivenEvidence,"other"):tail scope),T.SWanted "Dict" (head scope:scope),
        T.SWanted "Dict" []]
  forM_ (zip [0::Int ..] variants) $ \(index,value)->
    check ("role, identity, order, multiplicity and empty scope "++show index) (query value/=query wanted)
  check "distinct scopes stay distinct" (query (T.SApp wanted (variants!!3))/=query (T.SApp wanted wanted))
  let alpha name=T.SLam name T.Nothing (T.SWanted "Dict" [(T.GivenEvidence,name)])
  check "canonical local identity preserves alpha equivalence" (query (alpha "a")==query (alpha "b"))
  check "binder annotations remain semantic" (query (T.SLam "a" (T.Just (T.SAnnotation [] (T.SCon "Int" []))) wanted)/=
    query (T.SLam "a" (T.Just (T.SAnnotation [] (T.SCon "Bool" []))) wanted))
  let candidates=[(T.InstanceEvidence,B.literal (replicate 240 'x'++show i))|i<-[0..63::Int]]
      repeated=foldr (\_ body->T.SApp (T.SWanted "Dict" candidates) body) (T.SIntLit 0) [1..256::Int]
      compact=query repeated; old=legacyQuery "crate" "compiler" (prepared repeated) M.empty "datatype-context"
      fields=unpack (B.unpack compact)
  check "one exact candidate table for 256 uses" (length (unpack (last fields))==1)
  check "materially bounded repeated-scope encoding" (P.stringLength compact*20<P.stringLength old)
  check "large pooled key exact reconstruction" (expandQuery compact==old)
  total<-readIORef count
  putStrLn ("Query encoding audit: "++show total++" checks passed")
