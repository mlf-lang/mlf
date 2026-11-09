-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Kind where {
  import MLF.Primitive;
  import Bootstrap.Types;
  eqKind :: Kind -> Kind -> Bool;
  eqKind Star Star = True;
  eqKind (KArrow a b) (KArrow c d) = (eqKind a c && eqKind b d);
  eqKind _ _ = False;
  kindEqual = eqKind;
  prettyKind :: Kind -> String;
  prettyKind Star = "*";
  prettyKind (KArrow a b) = (leftKind a ++ (" -> " ++ prettyKind b));
  leftKind :: Kind -> String;
  leftKind Star = "*";
  leftKind k = ("(" ++ (prettyKind k ++ ")"));
  applyKind :: Kind -> Kind -> Either String Kind;
  applyKind Star _ = Left "invalid type constructor arity: a type of kind * cannot be applied";
  applyKind (KArrow domain result) argument =
    if eqKind domain argument
    then Right result
    else Left
           ("kind mismatch: expected " ++ (prettyKind domain ++ (", got " ++ prettyKind argument)));
  kindArity :: Kind -> Int;
  kindArity Star = 0;
  kindArity (KArrow _ k) = (1 + kindArity k)
}
