{-# LANGUAGE OverloadedStrings #-}
-- An independent decoder recovers the legacy framed syntax, not the new encoder.
module PreparedInputChecks where
import Prelude
import Control.Monad (unless, forM_)
import System.Environment (setEnv, unsetEnv)
import qualified Data.ByteString as BS
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.CrateGraph as CG
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as S
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.QueryGraph as G
import qualified MLF.Primitive as P

assert label condition = unless condition (error label)
expect label result = case result of
  T.Left e -> error (label ++ ": " ++ P.textToChars e)
  T.Right x -> pure x
reject label expected result = case result of
  T.Left e -> assert label (e == expected)
  _ -> error (label ++ ": unexpectedly accepted")
restore table value = case value of
  W.VText text -> text
  W.VNode 427 fields -> S.pack (map (restore table) fields)
  W.VNode 428 [W.VInt index] ->
    if index < 0 || fromIntegral index >= length table then error "scope index"
    else table !! fromIntegral index
  _ -> error "unknown prepared syntax node"
unpool value = case value of
  W.VNode 429 [W.VNode 427 fields,W.VNode 427 scopes] ->
    let table = map (restore []) scopes in map (restore table) fields
  _ -> error "unknown prepared syntax root"
hash key = G.hashValue (Q.pooledSourceValue [key]) >>= expect "hash"
expression = Q.expressionKey Q.KeyScope
member name ann body = Q.memberKey Q.KeyScope (Q.canonicalMember (name,ann,body))
annotation = T.SAnnotation ["exists"] (T.SForall T.Rigid "a" T.SBottom
  (T.SQualified [T.SPredicate "C" [T.STVar "a"]] (T.SArrow (T.STVar "a") (T.SCon "Int" []))))
x = T.SVar "x"
scopes = [[(T.GivenEvidence,"a"),(T.InstanceEvidence,"b"),(T.GivenEvidence,"a")],
          [(T.InstanceEvidence,"b"),(T.GivenEvidence,"a")], [], [(T.SuperclassEvidence,"a")]]
patterns = [T.SConstructorPattern "C" [T.Just "a",T.Nothing], T.SDefaultPattern T.Nothing,
 T.SNestedPattern "N" [T.SIntPattern 2], T.SAnnotatedPattern "p" annotation,
 T.SIntPattern (-3), T.SStringPattern "λ:雪", T.SBoolPattern True,
 T.SOverloadedStringPattern (T.ScalarString "hi") "equal" "from",
 T.SOverloadedStringPattern (T.CharString [0,55296,1114111]) "equal" "from",
 T.SAsPattern "all" (T.SDefaultPattern (T.Just "part")), T.SLazyPattern (T.SIntPattern 4)]
recursive = [("f",T.InferRecursive,x),("g",T.CheckRecursive annotation,x)]
expressions = [x,T.SConstructor "C",T.SLam "a" T.Nothing x,T.SLam "a" (T.Just annotation) x,
 T.SApp x x,T.SLet "a" x x,T.SAnn x annotation,T.SSignature x annotation,T.SIntLit (-1),
 T.SDoubleLit 0,T.SDoubleLit (-0.0),T.SDoubleLit (P.doubleFromBits 0x7ff8000000000001),
 T.SDoubleLit (P.doubleFromBits 0x7ff8000000000002),T.SBoolLit False,T.SStringLit "λ:雪\0",
 T.SPrimitive T.PAddInt,T.SCase x [T.SAlternative p x | p <- patterns],
 T.SDo [T.SDoBind p x | p <- patterns] x,
 T.SDo [T.SDoThen x,T.SDoLet "a" (T.Just annotation) x,T.SDoLetRec recursive] x,
 T.SEquations [(patterns,x)],T.SLetRec recursive x,T.SChecked (T.SBottomKind (T.KArrow T.Star T.Star)) x,
 T.SSourceDefinition x,T.SCallSite "site" (T.SourceSpan "p" "M" "file" 1 2 3 4) x,
 T.SSharedBind (head patterns) x x x x] ++ map (T.SWanted "dict") scopes
semanticMutations = [
 ("variable",expression (T.SVar "x"),expression (T.SVar "y")),
 ("constructor",expression (T.SVar "x"),expression (T.SConstructor "x")),
 ("application order",expression (T.SApp x (T.SVar "y")),expression (T.SApp (T.SVar "y") x)),
 ("declaration provenance",expression (T.SAnn x annotation),expression (T.SSignature x annotation)),
 ("source wrapper",expression x,expression (T.SSourceDefinition x)),
 ("checked type",expression (T.SChecked T.SBottom x),expression (T.SChecked (T.SCon "Int" []) x)),
 ("positive/negative zero",expression (T.SDoubleLit 0),expression (T.SDoubleLit (-0.0))),
 ("NaN payload",expression (T.SDoubleLit (P.doubleFromBits 0x7ff8000000000001)),
   expression (T.SDoubleLit (P.doubleFromBits 0x7ff8000000000002))),
 ("infinity sign",expression (T.SDoubleLit (P.doubleFromBits 0x7ff0000000000000)),
   expression (T.SDoubleLit (P.doubleFromBits (-4503599627370496)))),
 ("call span",expression (T.SCallSite "s" (T.SourceSpan "p" "M" "f" 1 2 3 4) x),
   expression (T.SCallSite "s" (T.SourceSpan "p" "M" "f" 1 2 3 5) x)),
 ("quantifier rigidity",expression (T.SChecked (T.SForall T.Flexible "a" T.SBottom (T.STVar "a")) x),
   expression (T.SChecked (T.SForall T.Rigid "a" T.SBottom (T.STVar "a")) x)),
 ("annotation presence",member "m" T.Nothing x,member "m" (T.Just annotation) x),
 ("member identity",member "m" T.Nothing x,member "n" T.Nothing x),
 ("evidence name",expression (T.SWanted "d" [(T.GivenEvidence,"a")]),expression (T.SWanted "d" [(T.GivenEvidence,"b")])),
 ("evidence role",expression (T.SWanted "d" [(T.GivenEvidence,"a")]),expression (T.SWanted "d" [(T.InstanceEvidence,"a")])),
 ("evidence duplicate",expression (T.SWanted "d" [(T.GivenEvidence,"a")]),expression (T.SWanted "d" [(T.GivenEvidence,"a"),(T.GivenEvidence,"a")])),
 ("evidence order",expression (T.SWanted "d" [(T.GivenEvidence,"a"),(T.GivenEvidence,"b")]),
   expression (T.SWanted "d" [(T.GivenEvidence,"b"),(T.GivenEvidence,"a")]))]
preparedIdentityChecks = do
  let original = [("member",T.Nothing,T.SIntLit 1)]
      lowered = [("member",T.Nothing,T.SIntLit 2)]
      prepared a b flag = Source.PreparedGroup a b [] M.empty [("member",[],flag)] T.Nothing []
  h <- G.hashValue (CG.preparedValue (prepared original lowered False)) >>= expect "prepared identity"
  forM_ [("original field",prepared lowered lowered False),("lowered field",prepared original original False),
         ("original/lowered order",prepared lowered original False),("protection",prepared original lowered True)] $ \(label,p) -> do
    altered <- G.hashValue (CG.preparedValue p) >>= expect label
    assert ("prepared field mutation: " ++ label) (h /= altered)

-- Cache basis migration must not mutate or silently reuse an old generation.
migrationChecks root = do
  let path = P.textFromChars (root ++ "/prepared-format-migration")
      oldConfig = S.pack ["crate","compiler",Q.sourceQueryFormat,"open-fragment-checker-1","source"]
      newConfig = S.pack ["crate","compiler",Q.sourceQueryFormat,"open-fragment-checker-1","prepared-source-tree-1","source"]
      wanted = G.key "InferScc" "member"
      record source session = do
        (input,next) <- G.record (G.inputKey "Prepared") [] False source session >>= expect "record prepared"
        G.record wanted [G.edge input] True (W.VText "same checked result") next >>= expect "record result"
  old <- G.begin path oldConfig >>= expect "old basis"
  (oldNode,oldReady) <- record (W.VText "legacy prepared") old
  _ <- G.publish oldReady >>= expect "publish old"
  reopened@(G.Session _ _ generation _ _ _) <- G.begin path oldConfig >>= expect "reopen old"
  let pointer = P.textToChars path ++ "/CURRENT"
      retained = [P.textToChars (G.payloadPath reopened (G.nodeHash oldNode)),
                  P.textToChars path ++ "/generations/" ++ P.textToChars generation ++ ".mlfqg"]
  oldPointer <- BS.readFile pointer
  oldBytes <- mapM BS.readFile retained
  fresh <- G.begin path newConfig >>= expect "new basis cold"
  (_,refreshed) <- G.record (G.inputKey "Prepared") [] False (W.VText "legacy prepared") fresh >>= expect "refresh old value"
  assert "new basis cannot reuse old provider despite equal refreshed input" (case fst (G.validate wanted refreshed) of T.Nothing -> True; _ -> False)
  unchanged <- BS.readFile pointer
  assert "basis mismatch does not publish" (oldPointer == unchanged)
  let newValue = Q.pooledSourceValue [expression (T.SIntLit 1)]
  (_,newReady) <- record newValue fresh
  setEnv "MLF_QUERY_FAILPOINT" "before-current"
  failed <- G.publish newReady
  unsetEnv "MLF_QUERY_FAILPOINT"
  reject "migration failure reached before-current" "query publication interrupted before current" failed
  stillOld <- BS.readFile pointer
  assert "failed migration retains CURRENT" (oldPointer == stillOld)
  _ <- G.publish newReady >>= expect "retry migration"
  warm <- G.begin path newConfig >>= expect "new basis warm"
  (_,warmInput) <- G.record (G.inputKey "Prepared") [] False newValue warm >>= expect "refresh new prepared"
  assert "new basis second run reuses result" (case fst (G.validate wanted warmInput) of T.Just node -> G.nodeHash node == G.nodeHash oldNode; _ -> False)
  after <- mapM BS.readFile retained
  assert "old reachable payload and generation remain byte identical" (oldBytes == after)
  putStrLn "prepared input: old basis/new cold/new warm and failed replacement retention passed"

main = do
  preparedIdentityChecks
  forM_ semanticMutations $ \(label,a,b) -> do
    ha <- hash a; hb <- hash b
    assert ("one-field semantic mutation: " ++ label) (ha /= hb)
  alphaA <- hash (member "m" T.Nothing (T.SLam "x" T.Nothing (T.SVar "x")))
  alphaB <- hash (member "m" T.Nothing (T.SLam "y" T.Nothing (T.SVar "y")))
  assert "canonical alpha-renaming retains identity" (alphaA == alphaB)
  let members = [("member",T.Just annotation,e) | e <- expressions]
      value = Q.pooledSourceValue (map (Q.memberKey Q.KeyScope) members)
  assert "all syntax constructors preserve legacy framing" (unpool value == map Q.encodeMember members)
  forM_ [T.Nothing,T.Just (Source.RootAuthority "root" [("binder","C","dictionary")] False
      [(T.GivenEvidence,"candidate",T.XBot)] ["candidate"])] $ \authority -> do
    let prepared = Source.PreparedGroup members (reverse members) [] M.empty
          [("member",["C"],False)] authority [("parameter",True)]
        canonical = Q.list (Q.encodeMember . Q.canonicalMember)
        expected = [canonical members,canonical (reverse members),Q.list id (Q.sourceGroupMetadataUsing CG.candidateMetadata prepared)]
    case CG.preparedValue prepared of
      W.VNode 421 [body] -> assert "actual original/members/metadata oracle" (unpool body == expected)
      _ -> error "wrong prepared envelope"
  bytes <- W.encode W.defaultLimits 6 [value] >>= expect "encode"
  decoded <- W.decode W.defaultLimits 6 bytes >>= expect "decode"
  case decoded of
    [result] -> assert "binary roundtrip preserves legacy framing" (unpool result == map Q.encodeMember members)
    _ -> error "wrong roots"
  let scope = [(T.InstanceEvidence,P.textFromChars ("candidate" ++ show n)) | n <- [1..256::Int]]
      large = replicate 4096 (expression (T.SWanted "d" scope))
      legacy = Q.list Q.encodeExpression (replicate 4096 (T.SWanted "d" scope))
  assert "regression exceeds old symbol limit" (P.stringLength legacy > W.maxSymbolBytes W.defaultLimits)
  rejected <- W.encode W.defaultLimits 6 [W.VText legacy]
  reject "old field fails at symbol limit" "binary symbol byte limit exceeded" rejected
  _ <- W.encode W.defaultLimits 6 [Q.pooledSourceValue large] >>= expect "large structural prepared input"
  rejectedAtom <- W.encode W.defaultLimits 6 [Q.pooledSourceValue [Q.KeyText legacy]]
  reject "real oversized atom stays rejected" "binary symbol byte limit exceeded" rejectedAtom
  let exactUtf8 = P.textFromChars (replicate (fromIntegral (W.maxSymbolBytes W.defaultLimits `div` 4)) '\x1f600')
  _ <- W.encode W.defaultLimits 6 [Q.pooledSourceValue [Q.KeyText exactUtf8]] >>= expect "UTF8 atom exact byte limit"
  utf8Over <- W.encode W.defaultLimits 6 [Q.pooledSourceValue [Q.KeyText (P.concatString exactUtf8 "a")]]
  reject "UTF8 byte limit despite fewer characters" "binary symbol byte limit exceeded" utf8Over
  let nested = foldr (\_ body -> Q.KeyFields [body]) (Q.KeyText "leaf") [1..W.maxDepth W.defaultLimits + 1]
  depth <- W.encode W.defaultLimits 6 [Q.pooledSourceValue [nested]]
  reject "default depth limit unchanged" "binary graph depth limit exceeded" depth
  let W.Limits a b c d e f g _ = W.defaultLimits
      limitedWork = W.Limits a b c d e f g 32
  work <- W.encode limitedWork 6 [Q.pooledSourceValue [Q.KeyFields (replicate 20 (Q.KeyText "xx"))]]
  reject "expanded work still charged" "binary expanded-work limit exceeded" work
  putStrLn "prepared input: syntax oracle, binary roundtrip, semantic identities, >16MiB regression and resource guards passed"
