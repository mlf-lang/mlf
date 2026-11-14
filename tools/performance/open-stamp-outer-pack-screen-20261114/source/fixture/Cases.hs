{-# LANGUAGE OverloadedStrings #-}
module Cases where
import Prelude
import Control.Exception (Exception,throw)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T

data Sentinel = Sentinel String deriving Show
instance Exception Sentinel
poison :: String -> a
poison = throw . Sentinel

data Raw = Raw [T.DataDecl] [(T.XName,T.XType)] T.XTerm [(T.XName,T.XType)]
intType, stringType :: T.XType
intType = T.XCon "Int" []
stringType = T.XCon "String" []
unit :: T.XTerm
unit = T.XConstructor "()" []
name :: P.Int -> String -> T.XName
name i s = T.XName i (B.literal s)
baseRaw :: Raw
baseRaw = Raw [] [] (T.XIntTerm 0) []

finiteRaw :: [(String,Raw)]
finiteRaw =
 [("empty-fields",baseRaw),
  ("ids-min-and-negative",Raw [] [(name minBound "left",intType),(name (-7) "right",intType)] unit [(name 8 "out",intType)]),
  ("canonical-declaration",Raw [T.DataDecl "Box" ["original"] [T.ConstructorDecl "BoxValue" [T.Parameter "original"]]] [] unit []),
  ("higher-kinded-type",Raw [] [(name 9 "k",T.XForall (T.XTyVar (-2)) (T.XBotKind (T.KArrow T.Star T.Star)) (T.XApply (T.XVar (T.XTyVar (-2))) intType))] unit []),
  ("escaped-string",Raw [] [] (T.XStringTerm (B.literal "\NUL\t\n\r\"\\:\DEL")) [])]
 ++ [("unicode-"++show i,Raw [] [(name (fromIntegral i) [c,':'],stringType)]
        (T.XStringTerm (B.literal [c,c])) [(name (fromIntegral (i+20)) ['x',c],stringType)])
     | (i,c)<-zip [1::Int ..] ['\x7f','\x80','\x7ff','\x800','\xffff','\x10000','\x10ffff']]
 ++ [("length-"++show n,Raw [] [(name 17 (replicate n 'x'),intType)]
        (T.XStringTerm (B.literal (replicate n 'a'))) [(name 18 (replicate n 'y'),intType)])
     | n<-[0,1,9,10,99,100]]

poisonRaw :: [(String,String,Raw)]
poisonRaw =
 [("environment-first","env",Raw (poison "env") (poison "ps") (poison "term") (poison "bs")),
  ("environment-tail","env-tail",Raw (T.DataDecl "Box" [] []:poison "env-tail") (poison "ps") unit []),
  ("parameter-spine","ps",Raw [] (poison "ps") (poison "term") []),
  ("parameter-id-before-hint","id",Raw [] [(T.XName (poison "id") (poison "hint"),poison "type")] unit []),
  ("parameter-hint-before-type","hint",Raw [] [(T.XName 0 (poison "hint"),poison "type")] unit []),
  ("parameter-type-before-tail","type",Raw [] ((name 0 "x",poison "type"):poison "ps-tail") unit []),
  ("parameter-tail-before-term","ps-tail",Raw [] ((name 0 "x",intType):poison "ps-tail") (poison "term") []),
  ("term-before-bindings","term",Raw [] [] (poison "term") (poison "bs")),
  ("term-left-before-right","left",Raw [] [] (T.XApp (poison "left") (poison "right")) []),
  ("strict-text-tail-before-bindings","text-tail",Raw [] [] (T.XStringTerm (B.literal ('x':poison "text-tail"))) (poison "bs")),
  ("binding-spine","bs",Raw [] [] unit (poison "bs")),
  ("binding-hint-before-type","hint",Raw [] [] unit [(T.XName 1 (poison "hint"),poison "type")]),
  ("binding-type-before-tail","type",Raw [] [] unit ((name 1 "x",poison "type"):poison "bs-tail")),
  ("binding-tail","bs-tail",Raw [] [] unit ((name 1 "x",intType):poison "bs-tail"))]

-- Four finite fields exercise exact decimal scalar-length framing independently
-- of the stamp's inner pretty-printing. No decoder/model replaces the real stamp.
framingFields :: [[B.String]]
framingFields = map (map B.literal)
 [["","","",""],["1:","a:b","\NUL", "\x10000"],
  [replicate 9 'x',replicate 10 'x',replicate 99 'x',replicate 100 'x'],
  ["\x7f\x80\x7ff\x800","\xffff\x10000\x10ffff","a\n\\\"", "\x301"],
  [replicate 2 'a',replicate 3 'b',replicate 4 'c',replicate 5 'd'],
  [replicate 7 'e',replicate 8 'f',"",""]]

-- Fixed ordinary public-API workload. A checked declaration spine ending in ()
-- is necessary for OpenFragment.check; no precomputed fingerprint is supplied.
{-# NOINLINE benchmarkTerm #-}
benchmarkTerm :: Int -> Int -> T.XTerm
benchmarkTerm count repetition = T.XLetRec
 [(name (fromIntegral (1000*repetition+i))
      ("entry"++show repetition++":"++show i++":"++replicate 24 'n'),
   stringType,T.XStringTerm (B.literal ("payload:"++show i++":\x96ea\x1f642:"++replicate 40 'p')))
  | i<-[1..count]] unit

forceText :: B.String -> ()
forceText text = go (B.unpack text) where
 go []=();go (c:cs)=c `seq` go cs
forceName :: T.XName -> ()
forceName (T.XName i hint)=i `seq` forceText hint
forceBindings :: [(T.XName,T.XType)] -> ()
forceBindings []=()
forceBindings ((n,t):xs)=forceName n `seq` forceType t `seq` forceBindings xs
forceType :: T.XType -> ()
forceType (T.XCon n [])=forceText n
forceType _=error "fixture forceType outside fixed benchmark domain"
forceBenchmark :: T.XTerm -> ()
forceBenchmark (T.XLetRec bindings (T.XConstructor end []))=walk bindings `seq` forceText end where
 walk []=()
 walk ((n,t,T.XStringTerm s):xs)=forceName n `seq` forceType t `seq` forceText s `seq` walk xs
 walk _=error "fixture forceBenchmark outside fixed benchmark domain"
forceBenchmark _=error "fixture expected declaration spine"

-- Real threshold cases use constructor spelling, not recursive string escaping:
-- prettyTerm is exactly "construct " ++ spelling ++ "()", so field length
-- is spelling length + 12. The other three raw stamp fields are empty.
guardLimit :: P.Int
guardLimit = 1048576
boundaryRaw :: [(String,Bool,Raw)]
boundaryRaw =
 [("guard-boundary-"++kind++"-"++tag,delta<=0,
   Raw [] [] (T.XConstructor (B.literal (replicate (262112+delta) c)) []) [])
  | (kind,c)<-[("ascii",'x'),("astral",'\x10000')],
    (tag,delta)<-[("below",-1),("at",0),("above",1)]]

hostErrorRaw :: [(String,String,Raw)]
hostErrorRaw =
 [("invalid-scalar-before-type","host:invalid Unicode scalar",
   Raw [] [(T.XName 0 (B.literal ('\xd800':poison "after-surrogate")),poison "type")]
     (poison "term") (poison "bs")),
  ("sentinel-before-invalid-scalar","sentinel:id",
   Raw [] [(T.XName (poison "id") (B.literal ['\xd800']),poison "type")] unit [])]
