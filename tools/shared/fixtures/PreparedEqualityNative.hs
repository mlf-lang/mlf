-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.SourceEquality as E;
  annotation = SAnnotation [] (SCon "Double" []);
  span = SourceSpan "package" "Module" "file.hs" 1 2 3 4;
  wrap mode value =
    if mode == 0 then value else
    if mode == 1 then SLam "x" Nothing value else
    if mode == 2 then SApp value value else
    if mode == 3 then SLet "x" value value else
    if mode == 4 then SAnn value annotation else
    if mode == 5 then SSignature value annotation else
    if mode == 6 then SCase (SIntLit 0) [SAlternative (SDefaultPattern Nothing) value] else
    if mode == 7 then SSourceDefinition value else
    if mode == 8 then SCallSite "call" span value else
    if mode == 9 then SSharedBind (SDefaultPattern Nothing) value value value value else
    if mode == 10 then SDo [SDoBind (SDefaultPattern Nothing) value] (SIntLit 0) else
    if mode == 11 then SDo [SDoThen value] (SIntLit 0) else
    if mode == 12 then SDo [SDoLet "x" Nothing value] (SIntLit 0) else
    if mode == 13 then SDo [SDoLetRec [(,,) "x" InferRecursive value]] (SIntLit 0) else
    if mode == 14 then SEquations [(,) [] value] else
    if mode == 15 then SLetRec [(,,) "x" (CheckRecursive annotation) value] (SIntLit 0) else
    if mode == 16 then SChecked (SCon "Double" []) value else
    SDeclScope [V.fromInt 0] value;
  main = do {
    mode <- getArg 0; first <- getArg 1; second <- getArg 2;
    let { a = wrap (readInt mode) (SDoubleLit (doubleFromBits (readInt first)));
          b = wrap (readInt mode) (SDoubleLit (doubleFromBits (readInt second))) };
    putStrLn ((if E.eqSExprBits a b then "1" else "0") ++ (if E.eqSExpr a b then "1" else "0"))
  }
}
