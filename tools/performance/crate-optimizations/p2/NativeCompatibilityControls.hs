{-# LANGUAGE OverloadedStrings #-}
-- Later reviewed native-integration controls. The historical 2503 P2 and 922
-- P3 controls remain byte-identical and run separately. Expected digests come
-- only from FrozenFingerprint's original indexed recurrence, never candidates.
module NativeCompatibilityControls where
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.IORef
import qualified Data.ByteString as BS
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as L
import qualified Bootstrap.Data as D
import qualified Bootstrap.Map as M
import qualified Bootstrap.Separate as S
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Checked as Checked
import qualified FrozenFingerprint as Old
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

check count label result = do
  unless result (error ("native compatibility control failed: " ++ label))
  modifyIORef' count (+1)
textEqual count label a b = check count label (H.utf8 a == H.utf8 b)
join = foldr P.concatString ""
observe value = do
  result <- try (evaluate (BS.length (H.utf8 value) `seq` H.unpack value))
  pure $ case result of
    Left exception -> Left (takeWhile (/='\n') (displayException (exception :: SomeException)))
    Right answer -> Right answer
render answer = case answer of T.Left message -> P.concatString "Left:" message; T.Right () -> "Right"
right answer = case answer of T.Left message -> error (H.unpack message); T.Right value -> value

-- Literal old Data.distinct, independently preserved rather than routed through
-- the changed shared validator. Full source validation remains shared in P2/P3.
oldDistinct what xs =
  if L.length xs == L.length (L.nubBy P.eqString xs)
  then T.Right () else T.Left (P.concatString "duplicate " what)

texts :: [H.String]
texts = ["", "ASCII", "λ中文🙂", "é", "nul\0\n", "\x10ffff",
         H.literal (replicate 257 'x'), H.literal (concat (replicate 17 "λ🙂"))]
int = T.XCon "Int" []
var = T.XTyVar 2
name = T.XName 3 "λ\0value"
box = T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
changed = T.DataDeclK "Box" [("a",T.Star)] [T.ConstructorDecl "Box" [T.Function (T.Parameter "a") (T.Parameter "a")]]
types = [T.XVar var, T.XVar (T.XTyVar (-3)), T.XBot,
         T.XBotKind (T.KArrow T.Star T.Star), T.XArrow int (T.XArrow int int),
         int, T.XCon "Pair" [int,T.XArrow int int], T.XApply (T.XVar var) int,
         T.XForall var T.XBot (T.XVar var), T.XForall var int (T.XArrow (T.XVar var) int)]
computations = [T.XRefl,T.XBottom int,T.XHyp var,T.XInner T.XRefl,
                T.XOuter var (T.XBottom int),T.XElim,T.XIntro var,
                T.XIntroKind var (T.KArrow T.Star T.Star),T.XThen T.XRefl T.XElim]
terms = [T.XVarTerm name,T.XAbs name int (T.XVarTerm name),
         T.XApp (T.XVarTerm name) (T.XIntTerm 1),
         T.XTypeAbs var T.XBot (T.XConstructor "K" [T.XVar var]),
         T.XTypeApp (T.XVarTerm name) (T.XThen T.XRefl T.XElim),
         T.XLet name (T.XIntTerm 1) (T.XVarTerm name),
         T.XLetRec [(name,int,T.XIntTerm 1)] (T.XVarTerm name),T.XLetRec [] (T.XIntTerm 0),
         T.XIntTerm (-123456789012345678901234567890),T.XDoubleTerm (-0.25),
         T.XBoolTerm True,T.XBoolTerm False,T.XStringTerm "λ\0\n🙂",
         T.XPrimitive T.PAddInt [int],T.XConstructor "Pair" [int,int],
         T.XCase (T.XVarTerm name) int
           [T.XAlternative (T.XConstructorPattern "K" [T.Nothing,T.Just name]) (T.XIntTerm 1),
            T.XAlternative (T.XDefaultPattern T.Nothing) (T.XIntTerm 2)],
         T.XCase (T.XIntTerm 1) int [],
         T.XWithData [box,changed] (T.XIntTerm 2),T.XWithData [] (T.XIntTerm 3)]

main = do
  count <- newIORef (0 :: Int)
  -- 16 single-text + 64 * 11 composed-text controls. Canonical seeds only:
  -- the new summary API explicitly does NOT promise signed-state recurrence.
  forM_ texts $ \a -> do
    let encoded = S.encodingText a
    check count "text scalar length" (S.encodingLength encoded == P.stringLength a)
    textEqual count "text old digest" (Old.oldFingerprint a) (S.encodingFingerprint encoded)
    forM_ texts $ \b -> do
      let combined = P.concatString a b
          parts = [S.encodingText a,S.encodingText b]
          appended = S.encodingConcat parts
          framed = S.encodingPack parts
          rawFramed = S.pack [a,b]
          chunks = S.encodingChunks M.empty [a,b,a] S.encodingEmpty
          rawChunks = join [a,b,a]
          continued = snd (S.encodingChunks (fst chunks) [b,a] (snd chunks))
          rawContinued = join [a,b,a,b,a]
      forM_ [("append",combined,appended),("pack",rawFramed,framed),
             ("chunks",rawChunks,snd chunks),("continued",rawContinued,continued)] $ \(label,raw,summary) -> do
        check count (label ++ " scalar length") (S.encodingLength summary == P.stringLength raw)
        textEqual count (label ++ " old digest") (Old.oldFingerprint raw) (S.encodingFingerprint summary)
      forM_ [(0,1),(17,29),(2147483646,2147483628)] $ \seed ->
        check count "canonical summary state" $
          Old.oldFingerprintStateFrom combined 0 (fst seed) (snd seed) == S.encodingState seed appended
  -- Ordinary printers are unchanged by the exact historical source projection.
  -- Check every current constructor plus precedence and Unicode framing.
  forM_ types $ \ty -> forM_ [-1,0,1,2,3] $ \precedence -> do
    let raw = Pretty.typeAt precedence ty; chunks = Pretty.typeChunks precedence ty []
    textEqual count "type chunks bytes" raw (join chunks)
    textEqual count "type chunks old digest" (Old.oldFingerprint raw)
      (S.encodingFingerprint (snd (S.encodingChunks M.empty chunks S.encodingEmpty)))
  forM_ computations $ \proof -> do
    let raw = Pretty.prettyComputation proof; chunks = Pretty.computationChunks proof []
    textEqual count "computation chunks bytes" raw (join chunks)
    textEqual count "computation chunks old digest" (Old.oldFingerprint raw)
      (S.encodingFingerprint (snd (S.encodingChunks M.empty chunks S.encodingEmpty)))
  forM_ terms $ \term -> forM_ [-1,0,1,2,3] $ \precedence -> do
    let raw = Pretty.termAt precedence term; chunks = Pretty.termChunks precedence term []
        summary = snd (S.encodingChunks M.empty chunks S.encodingEmpty)
    textEqual count "term chunks bytes" raw (join chunks)
    textEqual count "term chunks old digest" (Old.oldFingerprint raw) (S.encodingFingerprint summary)
    check count "term chunks scalar length" (P.stringLength raw == S.encodingLength summary)
  forM_ [[],[box],[changed,box]] $ \ds ->
    forM_ [[],[("value",int)],[("λ\0",T.XForall var T.XBot (T.XArrow (T.XVar var) int)),("other",int)]] $ \bindings ->
      forM_ ["0-1","λ\0🙂"] $ \objectHash -> do
        let iface = S.UnitInterface "Unit" [("Dep","1-2")] [] ds [] [] bindings objectHash
            raw = S.encodeInterface iface
            (pool,summary) = S.encodingInterface M.empty iface
            reused = snd (S.encodingInterface pool iface)
        textEqual count "interface old digest" (Old.oldFingerprint raw) (S.encodingFingerprint summary)
        check count "interface scalar length" (P.stringLength raw == S.encodingLength summary)
        textEqual count "interface pool reuse" (Old.oldFingerprint raw) (S.encodingFingerprint reused)
  let distinctCases = [([],True),(["a"],True),(["a","b"],True),(["a","a"],False),
        (["b","a","b"],False),(["λ","中"],True),(["é","é"],True),
        (["nul\0","nul"],True),(["",""],False),(["","a",""],False)]
  forM_ distinctCases $ \(values,accepted) -> do
    let expected = if accepted then "Right" else "Left:duplicate names"
    textEqual count "distinct literal outcome" expected (render (D.distinct "names" values))
    textEqual count "distinct old algorithm" (render (oldDistinct "names" values)) (render (D.distinct "names" values))
  let poison = H.failure "distinct value"
      distinctPoison = [(H.failure "unused label",[],False),
        (H.failure "duplicate label",["a","a"],True),
        ("names",error "distinct spine",True),
        ("names",[poison,"a"],True),("names",poison:error "distinct tail",True)]
  forM_ distinctPoison $ \(label,values,failed) -> do
    old <- observe (render (oldDistinct label values)); new <- observe (render (D.distinct label values))
    check count "distinct failure/demand order" (old == new)
    check count "distinct expected demand" (case new of Left _ -> failed; Right _ -> not failed)
  -- Intentional, documented shared-validation demand delta: Map.node forces
  -- its key even for singleton insertion, while old nubBy never compares it.
  -- Preserve BOTH authored outcomes; do not call this arbitrary-bottom parity.
  oldSingleton <- observe (render (oldDistinct "names" [poison]))
  newSingleton <- observe (render (D.distinct "names" [poison]))
  check count "old distinct ignores singleton name" (oldSingleton == Right "Right")
  check count "new distinct demands singleton name" (newSingleton == Left "HostError \"distinct value\"")
  forM_ [(T.XIntTerm 1,"Int"),(T.XStringTerm "λ\0🙂","String"),(T.XWithData [box] (T.XIntTerm 2),"Int")] $ \(term,ty) -> do
    let ordinary = right (Checked.check term)
        pooled = right (Checked.checkWithContexts (Checked.contextPool [[box],[]]) term)
    textEqual count "ordinary checked body" (Pretty.prettyTerm term) (Pretty.prettyTerm (Checked.term ordinary))
    textEqual count "ordinary checked type" ty (Pretty.prettyType (Checked.typeOf ordinary))
    textEqual count "context checked body" (Pretty.prettyTerm term) (Pretty.prettyTerm (Checked.term pooled))
    textEqual count "context checked type" ty (Pretty.prettyType (Checked.typeOf pooled))
  forM_ [[H.failure "chunk text"],error "chunk list",["a",H.failure "chunk tail"],[H.literal ['\xd800']]] $ \chunks -> do
    old <- observe (Old.oldFingerprint (join chunks))
    new <- observe (S.encodingFingerprint (snd (S.encodingChunks M.empty chunks S.encodingEmpty)))
    check count "chunk error parity" (old == new && case old of Left _ -> True; Right _ -> False)
  check count "encoding length ignores state" $
    S.encodingLength (S.FingerprintEncoding 7 (error "power a") (error "power b") (error "state a") (error "state b")) == 7
  textEqual count "empty chunks do not demand pool" (Old.oldFingerprint "")
    (S.encodingFingerprint (snd (S.encodingChunks (error "unused pool") [] S.encodingEmpty)))
  check count "zero chunk length" (S.encodingLength (snd (S.encodingChunks M.empty [] S.encodingEmpty)) == 0)
  let unit n header body term =
        let full = T.XWithData body term
            iface = S.UnitInterface n [] [] header [] [] [] (Old.oldFingerprint (Pretty.prettyTerm full))
        in S.UnitObject iface full
      one = unit "One" [box] [box] (T.XIntTerm 1)
      two = unit "Two" [box] [box] (T.XStringTerm "λ🙂")
      checkedTerm = T.XStringTerm "checked λ"
      checkedIface = S.UnitInterface "Checked" [] [] [] [] [] [] (Old.oldFingerprint (Pretty.prettyTerm checkedTerm))
      checked = S.CheckedUnitObject checkedIface (right (Checked.check checkedTerm))
      mismatch = unit "Different" [box] [changed] (T.XIntTerm 3)
  forM_ [[],[one],[one,two],[checked],[mismatch]] $ \fragments -> do
    let (digest,summaries) = A.fingerprintPooled fragments
    textEqual count "pooled payload old digest" (Old.oldFingerprint (Old.oldEncodePooledPayload fragments)) digest
    check count "pooled body inventory" (length summaries == length fragments)
    forM_ (zip fragments summaries) $ \(fragment,summary) ->
      textEqual count "pooled body old digest" (Old.oldFingerprint (Pretty.prettyTerm (S.objectBody fragment)))
        (S.encodingFingerprint summary)
  total <- readIORef count
  unless (total == 1243) (error ("native control inventory changed: " ++ show total))
  putStrLn ("{\"complete\":true,\"native_compatibility_controls\":" ++ show total ++ "}")
