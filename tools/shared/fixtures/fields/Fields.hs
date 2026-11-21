-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  reference fields = case fields of {
    [] -> "";
    (:) field rest -> showInt (stringLength field) ++ ":" ++ field ++ reference rest
  };
  encode engine fields = if eqString engine "primitive" then packStringFields fields else reference fields;
  patterns count = S.map (\i -> S.concatStrings (S.replicate (remInt (i * 37) 300) "aα😀")) (S.range 0 (count - 1));
  emit value = do { putStrLn value; printInt (stringLength value) };
  main = do {
    engine <- getArg 0; mode <- getArg 1;
    if eqString mode "list" then emit (encode engine (panic "list-first"))
    else if eqString mode "head" then emit (encode engine ((:) (panic "head-first") (panic "tail-second")))
    else if eqString mode "tail" then emit (encode engine ((:) "a" (panic "tail-required")))
    else if eqString mode "later-head" then emit (encode engine ((:) "a" ((:) (panic "second-first") (panic "tail-second"))))
    else if eqString mode "empty-tail" then emit (encode engine ((:) "" (panic "tail-required")))
    else if eqString mode "unused" then putStrLn (if True then "lazy" else encode engine (panic "unused"))
    else if eqString mode "boundary" then do {
      size <- getArg 2;
      emit (encode engine [S.concatStrings (S.replicate (readInt size) "aα😀"),"",":0:ab",stringFromCode 0])
    } else if eqString mode "many" then do { size <- getArg 2; emit (encode engine (patterns (readInt size))) }
    else if eqString mode "empty" then emit (encode engine [])
    else emit (encode engine ["","a:β","🌍",stringFromCode 0,"0:12:"])
  }
}
