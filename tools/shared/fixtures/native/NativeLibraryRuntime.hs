{-# LANGUAGE OverloadedStrings #-}
-- Public checked-library API only: no copied lowering or forged receipts.
module Main where
import Prelude
import Control.Monad (forM_)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.LLVM.Library as N
import qualified MLF.Primitive as P

right (T.Right value) = value
right (T.Left message) = error (P.textToChars message)
identity = P.textFromChars (replicate 64 'a')
key i = P.textFromChars ("export" ++ show i)
int = T.XCon "Int" []
unit = T.XConstructor "()" []
poison = T.XApp (T.XApp (T.XPrimitive T.PQuotInt []) (T.XIntTerm 1)) (T.XIntTerm 0)
action = T.XApp (T.XPrimitive T.PPutStrLn []) (T.XStringTerm "native-action")
emit directory label values = do
 let entries = [(key i,key i,ty) | (i,(ty,_)) <- zip [0..] values]
     layout = right (N.prepareLayout identity entries [])
     linked = foldl (\prior (i,(_,value)) -> right (C.appendSpine prior
       (right (C.check (T.XLet (T.XName i (key i)) value unit)))))
       C.emptySpine (zip [0..] values)
     llvm = right (N.emitLibrary layout linked)
 writeFile (directory ++ "/" ++ label ++ ".ll") (concatMap P.textToChars llvm)
emitExtension directory = do
 let saved = T.DataDecl "Saved" [] [T.ConstructorDecl "SavedValue" [T.Applied "Int" []]]
     user = T.DataDecl "User" [] [T.ConstructorDecl "UserBox" [T.Applied "Int" []]]
     ty = T.XCon "Saved" []
     entries = [("saved","parameter",ty)]
     base = right (N.prepareLayout identity entries [saved])
     fragment = T.XWithData [saved] (T.XLet (T.XName 0 "saved")
       (T.XApp (T.XConstructor "SavedValue" []) (T.XIntTerm 42)) unit)
     linked = right (C.appendSpine C.emptySpine (right (C.check fragment)))
     census = right (N.libraryTypeNames base linked)
     layout = right (N.prepareLayoutWithTypeNames identity entries [saved] census)
     arg = T.XName 0 "parameter"; field = T.XName 1 "field"; result = T.XName 2 "result"
     ioUnit = T.XCon "IO" [T.XCon "()" []]
     body = T.XAbs arg ty (T.XCase (T.XVarTerm arg) ioUnit
       [T.XAlternative (T.XConstructorPattern "SavedValue" [T.Just field])
         (T.XCase (T.XApp (T.XConstructor "UserBox" []) (T.XVarTerm field)) ioUnit
           [T.XAlternative (T.XConstructorPattern "UserBox" [T.Just result])
             (T.XApp (T.XPrimitive T.PPrintInt []) (T.XVarTerm result))])])
 writeFile (directory ++ "/extension-library.ll") (concatMap P.textToChars (right (N.emitLibrary layout linked)))
 forM_ [("extension-user-first",[user,saved]),("extension-saved-first",[saved,user])] $ \(label,ds) ->
   writeFile (directory ++ "/" ++ label ++ ".ll") (concatMap P.textToChars
     (right (N.emitRoot layout ["saved"] (right (C.check (T.XWithData ds body))))))
emitOpenFields directory = do
 let box = T.DataDecl "DoubleBox" [] [T.ConstructorDecl "MkDoubleBox" [T.Applied "Double" []]]
     boxTy = T.XCon "DoubleBox" []; boolTy = T.XCon "Bool" []; doubleTy = T.XCon "Double" []
     x = T.XName 10 "box"; field = T.XName 11 "field"
     inspect = T.XAbs x boxTy (T.XCase (T.XVarTerm x) boolTy
       [T.XAlternative (T.XConstructorPattern "MkDoubleBox" [T.Just field])
         (T.XApp (T.XApp (T.XPrimitive T.PEqDouble []) (T.XVarTerm field)) (T.XDoubleTerm 9))])
     ignore = T.XAbs x boxTy (T.XCase (T.XVarTerm x) boolTy
       [T.XAlternative (T.XConstructorPattern "MkDoubleBox" [T.Nothing]) (T.XBoolTerm True)])
     values = [("seed",boxTy,T.XApp (T.XConstructor "MkDoubleBox" []) (T.XDoubleTerm 1)),
               ("inspect",T.XArrow boxTy boolTy,inspect),("ignore",T.XArrow boxTy boolTy,ignore)]
     entries = [(key,key,ty) | (key,ty,_) <- values]
     linked = foldl (\prior (i,(key,_,value)) -> right (C.appendSpine prior
       (right (C.check (T.XWithData [box] (T.XLet (T.XName i key) value unit)))))) C.emptySpine (zip [0..] values)
     base = right (N.prepareLayout identity entries [box])
     layout = right (N.prepareLayoutWithTypeNames identity entries [box] (right (N.libraryTypeNames base linked)))
     delayed = T.XApp (T.XApp (T.XPrimitive T.PAddDouble []) (T.XDoubleTerm 4)) (T.XDoubleTerm 5)
     poisonDouble = T.XApp (T.XPrimitive T.PPanic [doubleTy]) (T.XStringTerm "lazy-field-demanded")
     ioUnit = T.XCon "IO" [T.XCon "()" []]
     printInt n = T.XApp (T.XPrimitive T.PPrintInt []) (T.XIntTerm n)
 writeFile (directory ++ "/open-fields-library.ll") (concatMap P.textToChars (right (N.emitLibrary layout linked)))
 forM_ [("open-fields-delayed","inspect",delayed),("open-fields-unused","ignore",poisonDouble),
        ("open-fields-demanded","inspect",poisonDouble)] $ \(label,key,value) -> do
   let function = T.XName 20 key
       condition = T.XApp (T.XVarTerm function) (T.XApp (T.XConstructor "MkDoubleBox" []) value)
       body = T.XAbs function (T.XArrow boxTy boolTy)
         (T.XApp (T.XApp (T.XApp (T.XPrimitive T.PIfThenElse [ioUnit]) condition) (printInt 1)) (printInt 0))
   writeFile (directory ++ "/" ++ label ++ ".ll") (concatMap P.textToChars
     (right (N.emitRoot layout [key] (right (C.check (T.XWithData [box] body))))))
main = do
 args <- getArgs
 case args of
  [directory] -> do
   forM_ [0,1,7,65] $ \count -> emit directory ("poison" ++ show count) (replicate count (int,poison))
   emit directory "io" [(T.XCon "IO" [T.XCon "()" []],action),(int,poison)]
   emitExtension directory
   emitOpenFields directory
   putStrLn "PASS emitted checked native libraries: poison0 poison1 poison7 poison65 io"
   putStrLn "PASS emitted native datatype extension: user-first saved-first"
   putStrLn "PASS emitted native open fields: delayed unused demanded"
  _ -> error "expected output directory"
