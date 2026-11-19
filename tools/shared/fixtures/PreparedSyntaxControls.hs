{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (forM_, unless)
import Data.List (zip4)
import Data.IORef
import Control.Exception (SomeException, displayException, try)
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

-- Reconstruct the ordinary length-framed expression with host lists and scalar
-- lengths. The oracle has no dependency on the compiler's framing or budgets.
expandPositions wire =
  let frame x=show (length x) ++ ":" ++ x
      getField s=case span (\c -> c>='0' && c<='9') s of
        (n,':':xs) | not (null n) -> let k=read n; (x,rest)=splitAt k xs in
          if length x==k && show k==n then (x,rest) else error "invalid delta field length"
        _ -> error "missing delta field length"
      getFields 0 s=([],s)
      getFields k s=let (x,more)=getField s; (xs,end)=getFields (k-1::Int) more in (x:xs,end)
      signed s = let word scale total (ch:more)
                       | fromEnum ch < 128 = let u=toInteger (fromEnum ch)
                                                in if u<64 then (total+scale*u,more)
                                                   else word (scale*64) (total+scale*(u-64)) more
                     word _ _ _=error "invalid delta coordinate"
                     (u,rest)=word 1 0 s
                     number=if even u then u `div` 2 else negate ((u+1) `div` 2)
                 in (fromInteger number :: P.Int,rest)
      tree position (tag:s) = case tag of
        'a' -> let (left,middle,p)=tree position s; (right,end,p')=tree p middle
               in (tag:left++right,end,p')
        'l' -> withChild 2
        'S' -> withChild 2
        'd' -> local True
        'D' -> local False
        'v' -> leaf
        'i' -> leaf
        'x' -> leaf
        _ -> error "unknown delta syntax"
       where
        withChild n=let (xs,more)=getFields n s; (child,end,after)=tree position more
                    in (tag:concatMap frame xs++child,end,after)
        leaf=let (x,rest)=getField s in (tag:frame x,rest,position)
        local sameLine=let (label,z)=getField s
                           (l0,c0)=position
                           (dl,z1)=if sameLine then (0,z) else signed z
                           (dc,z2)=signed z1
                           (lineCount,z3)=if sameLine then (0,z2) else signed z2
                           (width,z4)=signed z3
                           l=l0+dl; c=c0+dc
                           (child,end,after)=tree (l,c) z4
                       in ('s':concatMap frame (label:map show [l,c,l+lineCount,c+width])++child,end,after)
      tree _ [] = error "missing delta syntax"
      (header,after)=getFields 5 wire
      (syntax,end,_)=tree (0,0) after
  in if null end then "P1"++concatMap frame header++syntax else error "trailing delta syntax"

expandSymbolTable poolConstructors wire =
  let frame x=show (length x)++":"++x
      get s=case span (\c->c>='0'&&c<='9') s of
        (n,':':xs)|not(null n)->let k=read n;(x,rest)=splitAt k xs in
          if length x==k&&show k==n then (x,rest) else error "pooled field length"
        _->error "pooled field prefix"
      fields 0 s=([],s)
      fields n s=let (v,t)=get s;(vs,end)=fields (n-1::Int) t in (v:vs,end)
      name names (tag:payload)
        | fromEnum tag==127=let (value,rest)=get payload in (value,rest,if length names<64 then names++[value] else names)
        | fromEnum tag<length names=(names!!fromEnum tag,payload,names)
      name _ _=error "undefined pooled name"
      number (d:ds)|fromEnum d<64=([d],ds)
                   |fromEnum d<128=let (x,end)=number ds in (d:x,end)
      number _=error "invalid pooled coordinate"
      numbers 0 s=("",s)
      numbers n s=let (v,t)=number s;(vs,end)=numbers (n-1::Int) t in (v++vs,end)
      node table@(symbols,constructors) (tag:s) = case tag of
        'a' -> let (x,s1,t1)=node table s;(y,rest,t2)=node t1 s1 in ('a':x++y,rest,t2)
        'l' -> nested 2
        'S' -> nested 2
        'd' -> located 2
        'D' -> located 4
        'v' -> let (v,r,t)=name symbols s in ('v':frame v,r,(t,constructors))
        'p' -> let (v,r,t)=name symbols s in ('x':frame(frame "primitive"++frame v),r,(t,constructors))
        'C' | poolConstructors -> let (v,r)=get s in
          if length constructors < 32 && length v <= 4096 && v `notElem` constructors
          then (constructor v,r,(symbols,constructors++[v])) else error "invalid constructor definition"
        'c' | poolConstructors -> case s of
          slot:r | fromEnum slot < length constructors -> (constructor (constructors!!fromEnum slot),r,table)
          _ -> error "undefined constructor reference"
        'x' -> raw
        'i' -> raw
        _ -> error "invalid pooled syntax"
       where
        constructor v='x':frame(frame "constructor"++frame v)
        raw=let (v,r)=get s in (tag:frame v,r,table)
        nested n=let (vs,r)=fields n s;(x,end,t)=node table r in (tag:concatMap frame vs++x,end,t)
        located n=let (v,r,t)=name symbols s;(coords,r1)=numbers n r;(x,end,t1)=node (t,constructors) r1
                  in (tag:frame v++coords++x,end,t1)
      node _ []=error "missing pooled syntax"
      (header,after)=fields 5 wire
      (syntax,end,_)=node ([],[]) after
  in if null end then expandPositions (concatMap frame header++syntax) else error "trailing pooled syntax"

restoreOrigin :: String -> String
restoreOrigin ('P':'4':wire) = restoreOrigin (expandSymbolTable True wire)
restoreOrigin ('P':'3':wire) = restoreOrigin (expandSymbolTable False wire)
restoreOrigin ('P':'2':wire) = restoreOrigin (expandPositions wire)
restoreOrigin ('P':'1':wire) = case fields 5 wire of
  ([pkg,modName,file,name,annotation],tree) ->
    let (body,tailText) = expr (frame ["source-span",pkg,modName,file]) tree
    in if null tailText then frame [frame ["member",name,annotation,body]] else error "trailing source fields"
  _ -> error "source header"
  where
    frame xs = concat [show (length x) ++ ":" ++ x | x <- xs]
    fields :: Int -> String -> ([String],String)
    fields 0 input = ([],input)
    fields n input = case span (\c -> c >= '0' && c <= '9') input of
      (digits,':':after) | not (null digits) ->
        let size = read digits
            (field,more) = splitAt size after
            (others,tailText) = fields (n-1) more
        in if length field == size && show size == digits then (field:others,tailText) else error "field length"
      _ -> error "source field"
    expr origin (tag:rest) = case tag of
      'a' -> let (f,r) = expr origin rest; (a,end) = expr origin r in (frame ["apply",f,a],end)
      'l' -> let (args,r) = fields 2 rest; (body,end) = expr origin r in (frame ("lambda":args++[body]),end)
      's' -> case fields 5 rest of
        (label:coords,r) -> let (body,end) = expr origin r in (frame ["call-site",label,origin++frame coords,body],end)
        _ -> error "local span"
      'S' -> let (args,r) = fields 2 rest; (body,end) = expr origin r in (frame ("call-site":args++[body]),end)
      'i' -> scalar "integer"
      'v' -> scalar "variable"
      'x' -> case fields 1 rest of { ([value],end) -> (value,end); _ -> error "opaque leaf" }
      _ -> error "source tag"
      where scalar label = let (args,r) = fields 1 rest in (frame (label:args),r)
    expr _ [] = error "truncated expression"
restoreOrigin _ = error "missing source prefix"

originChecks check expressions = do
  let local = T.SourceSpan "" "模:块" "dir/😀:0" 0 1 3 4
      call span label = T.SCallSite label span (T.SVar "x")
      pad 0 leaf = leaf
      pad n leaf = let half = pad (n-1 :: Int) leaf in T.SApp half half
      large span leaf = [("λ:member",T.Just C.annotation,T.SLam "名" T.Nothing
        (T.SApp (pad 7 (call span "先")) leaf))]
      sample span label value = T.SCallSite label span value
      encode original = B.unpack (G.compactOrigin original "fallback" "" [] [])
      prove original = restoreOrigin (encode original) == B.unpack (encoded original)
      spans = [local,T.SourceSpan "p" "模:块" "dir/😀:0" 0 1 3 4,
        T.SourceSpan "" "m" "dir/😀:0" 0 1 3 4,T.SourceSpan "" "模:块" "file" 0 1 3 4,
        T.SourceSpan "" "模:块" "dir/😀:0" 2 1 3 4,T.SourceSpan "" "模:块" "dir/😀:0" 0 2 3 4,
        T.SourceSpan "" "模:块" "dir/😀:0" 0 1 7 4,T.SourceSpan "" "模:块" "dir/😀:0" 0 1 3 9]
  forM_ expressions $ \body -> check "all source leaf encodings restore exactly" (prove (large local body))
  forM_ spans $ \sp -> do
    let original = large local (sample sp ":0😀" (T.SIntLit (-1)))
    check "local and external spans restore all fields" (prove original)
  let distinct = [encode (large local (sample sp ":0😀" (T.SIntLit (-1)))) | sp <- spans]
  check "span mutations have distinct keys" (and [a /= b | (i,a) <- zip [0::Int ..] distinct,b <- drop (i+1) distinct])
  let small = member (pad 6 (call local "read")); group = large local (T.SIntLit 0)
      budget rows lower names metadata = G.compactOrigin rows "fallback" lower names metadata
      tooLong = iterate (\text -> P.concatString text text) "😀" !! 23
      repeatedOrigin = T.SourceSpan "" "" (B.literal (replicate 33000 '😀')) 1 1 1 2
  check "small member uses ordinary fields" (budget small "" [] [] == "fallback")
  check "multiple members use ordinary fields" (budget (group++group) "" [] [] == "fallback")
  check "name and metadata count is bounded" (budget group "" (replicate 140 "") (replicate 110 "") == "fallback")
  check "oversize lowered field uses ordinary admission" (budget group tooLong [] [] == "fallback")
  check "logical UTF8 origin size enforces ordinary admission" (budget (large repeatedOrigin (T.SVar "x")) "" [] [] == "fallback")
  check "small fields can still use the compact form" (budget group "" ["😀"] [""] /= "fallback")

relativeChecks check = do
  let pack xs = concat [show (length x) ++ ":" ++ x | x <- xs]
      fields "" = []
      fields text = case span (\c -> c >= '0' && c <= '9') text of
        (digits,':':payload) | not (null digits) ->
          let width = read digits
              (field,rest) = splitAt width payload
          in if width == length field && show width == digits then field:fields rest else error "relative field length"
        _ -> error "relative field syntax"
      erase text = case fields text of
        ["apply",f,a] -> pack ["apply",erase f,erase a]
        ["lambda",n,ann,b] -> pack ["lambda",n,ann,erase b]
        ["call-site",_,_,b] -> erase b
        _ -> text
      restore first delta = case fields (restoreOrigin (B.unpack first)) of
        [decl] -> case fields decl of
          ["member",n,ann,e] ->
            let lowered = erase e in case B.unpack delta of
              "D1i" -> pack [pack ["member",n,ann,lowered]]
              ('D':'1':'c':encodedType) -> case fields encodedType of
                [ty] -> pack [pack ["member",n,ann,pack ["checked",ty,lowered]]]
                _ -> error "relative checked type"
              _ -> error "relative tag"
          _ -> error "relative declaration"
        _ -> error "relative group"
      stmt e = [("me",T.Just C.annotation,e)]
      loc = T.SourceSpan "p" "模" "a😀" 1 3 4 6
      spanE e = T.SCallSite "名:" loc e
      repeated 0 e = e
      repeated n e = let half = repeated (n-1::Int) e in T.SApp half half
      build f e = T.SLam "r" T.Nothing (T.SApp (repeated 8 (f (T.SVar "r"))) e)
      source leaf = stmt (build spanE (spanE leaf))
      plain leaf = build id leaf
      descriptor = G.relativePrepared
      assertPair before lowered = case descriptor before lowered [] [] of
        T.Just (first,delta) -> check "relative source and lowered fields reconstruct independently"
          (restoreOrigin (B.unpack first) == B.unpack (encoded before) && restore first delta == B.unpack (encoded lowered))
        T.Nothing -> check "large matching pair is admitted" False
      rejects a b = case descriptor a b [] [] of { T.Nothing -> True; _ -> False }
      a = source (T.SIntLit 1)
      naked = stmt (plain (T.SIntLit 1))
      wrapped ty = stmt (T.SChecked ty (plain (T.SIntLit 1)))
  forM_ C.expressions $ \e -> do
    let opaque = T.SSourceDefinition e
    assertPair (source opaque) (stmt (plain opaque))
    assertPair (source opaque) (stmt (T.SChecked (T.SCon "Int" []) (plain opaque)))
  let points = [0,1,31,32,63,64,4095,4096,-1,-65,2^53,maxBound,minBound] :: [P.Int]
      calls = foldr (\(sl,sc,el,ec) b -> T.SApp (T.SCallSite "名:" (T.SourceSpan "p" "模" "a😀" sl sc el ec) (T.SVar "r")) b)
                (T.SVar "r") (zip4 points (reverse points) (drop 1 (cycle points)) (drop 4 (cycle points)))
      unlocated = foldr (\_ b -> T.SApp (T.SVar "r") b) (T.SVar "r") points
  assertPair (stmt (build spanE calls)) (stmt (build id unlocated))
  let names = [B.literal ("m:"++show i++"\DEL😀") | i <- [0::Int .. 95]] ++ ["","x","m:1\DEL😀","x"]
      use n b = T.SApp (spanE (T.SVar n)) b
      bare n b = T.SApp (T.SVar n) b
  assertPair (stmt (build spanE (foldr use (T.SPrimitive T.PAddInt) (names++reverse names))))
    (stmt (build id (foldr bare (T.SPrimitive T.PAddInt) (names++reverse names))))
  let (slots,smallGroup) = fixture "me" "stable" [] False T.GivenEvidence
      group raw lowered = S.SlotPrepared slots (S.PreparedGroup raw lowered [] M.empty [] T.Nothing [])
      (_,smallCache) = G.preparedValueCached T.Nothing slots smallGroup
      ordinary text = case B.unpack text of
        'P':version:_ | version `elem` ("1234" :: String) -> restoreOrigin (B.unpack text)
        x -> x
      verifyEntry tag raw lowered expectRelative = do
        let current = group raw lowered
            (actual,cached) = G.preparedValueCached smallCache slots current
            expected = legacy slots current
        case actual of
          W.VNode 421 [version,names,W.VText first,W.VText second,metadata] -> do
            let relative = take 2 (B.unpack second) == "D1"
                lowerText = if relative then restore first second else B.unpack second
                restored = W.VNode 421 [version,names,W.VText (B.literal (ordinary first)),W.VText (B.literal lowerText),metadata]
            check (tag++" canonical fields") (same expected restored)
            check (tag++" descriptor") (relative == expectRelative)
            check (tag++" drops large preceding syntax") (not (present cached))
            let (again,nextCache)=G.preparedValueCached cached slots smallGroup
            check (tag++" small cache resumes") (present nextCache && same again (legacy slots smallGroup))
          _ -> check "prepared group has both ordered fields" False
      bound = T.SForall T.Flexible "a" T.SBottom (T.STVar "a")
      typed = T.SAnn (T.SVar "r") (T.SAnnotation [] (T.STVar "a"))
      rawPoly = source typed
      loweredPoly = stmt (T.SChecked bound (plain typed))
  verifyEntry "bare" a naked True
  verifyEntry "checked" a (wrapped (T.SCon "Int" [])) True
  check "raw polymorphic pair demonstrates the changed type scope" (not (rejects rawPoly loweredPoly))
  verifyEntry "polymorphic checked body" rawPoly loweredPoly False
  assertPair a naked
  assertPair a (wrapped (T.SCon "Int" []))
  check "a changed location inside an opaque leaf remains observable"
    (rejects (source (T.SSourceDefinition (spanE (T.SVar "x"))))
      (stmt (plain (T.SSourceDefinition (T.SCallSite "other" loc (T.SVar "x"))))))
  check "a call site retained outside an opaque leaf differs from the descriptor"
    (rejects a (stmt (plain (spanE (T.SIntLit 1)))))
  check "distinct integers cannot share a lowered descriptor" (rejects a (stmt (plain (T.SIntLit 2))))
  check "reversed operands cannot share a lowered descriptor"
    (rejects a (stmt (T.SLam "r" T.Nothing (T.SApp (T.SIntLit 1) (repeated 8 (T.SVar "r"))))))
  check "member identity belongs to the delta" (rejects a [("other",T.Just C.annotation,plain (T.SIntLit 1))])
  check "optional annotation belongs to the delta" (rejects a [("me",T.Nothing,plain (T.SIntLit 1))])
  check "the original sign bit remains part of an opaque leaf"
    (rejects (source (T.SDoubleLit (P.doubleFromBits 0))) (stmt (plain (T.SDoubleLit (P.doubleFromBits minBound)))))
  let choices = [naked,wrapped (T.SCon "Int" []),wrapped (T.SCon "Bool" [])]
      descriptors = [B.unpack d | b <- choices,T.Just (_,d) <- [descriptor a b [] []]]
  check "unwrapped and distinct checked types retain separate descriptors"
    (length descriptors == 3 && and [x/=y | (i,x) <- zip [0::Int ..] descriptors, y <- drop (i+1) descriptors])
  check "unbounded metadata count returns to ordinary planning"
    (case descriptor a naked (replicate 250 "") [] of { T.Nothing -> True; _ -> False })

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
  relativeChecks check
  originChecks check bodies
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
  -- Prepared input hashes must use scalar lengths and preserve the generic
  -- reader's demand order through both admission paths.
  let fields ns o l ms = W.VNode 421 [W.VText "prepared-declarations-1",
        A.toList W.VText ns,W.VText o,W.VText l,A.toList W.VText ms]
      answer action = do
        v <- try action :: IO (Either SomeException (T.Either B.String B.String))
        pure (case v of Left e -> displayException e; Right _ -> "success")
      samples = [([], "", "", []),(["λ", "0:"], "\0", "😀", ["", "λ"]),
                 (replicate 250 "", "a", "b", []),(replicate 251 "", "a", "b", []),
                 ([],B.literal (replicate 16384 '界'),"",[])]
  forM_ samples $ \(ns,o,l,ms) -> do
    a <- G.hashPrepared ns o l ms
    b <- G.hashRebuiltValue (fields ns o l ms)
    check "typed and generic Prepared hashes" (case (a,b) of (T.Right x,T.Right y) -> x == y; _ -> False)
  let names = [errorWithoutStackTrace "bad prepared name"]
      original = errorWithoutStackTrace "bad original syntax"
  typedError <- answer (G.hashPrepared names original "" [])
  wireError <- answer (G.hashRebuiltValue (fields names original "" []))
  check "Prepared input error precedence" (typedError == "bad prepared name" && typedError == wireError)
  total<-readIORef count
  putStrLn ("Prepared syntax controls: "++show total++" checks; "++show (length rows)++" syntax variants")
