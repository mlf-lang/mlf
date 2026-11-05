-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Checked (CheckedTerm, check, term, typeOf, declarationBindings) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.X.Check as Check;
  -- The constructor is private. The term and its inferred type come from the
  -- same successful independent check; callers cannot attach a type to a term.
  data CheckedTerm = CheckedTerm XTerm XType (Either String ([] ((,) XName XType)));
  check :: XTerm -> Either String CheckedTerm;
  check source =
    do {
      answer <- Check.checkClosedWithBindings source;
      case answer of {
        (,) ty bindings -> Right (CheckedTerm source ty bindings)
      }
    };
  term :: CheckedTerm -> XTerm;
  term (CheckedTerm source _ _) = source;
  typeOf :: CheckedTerm -> XType;
  typeOf (CheckedTerm _ ty _) = ty;
  -- Inferred by the very check that constructed this opaque value. The
  -- inventory excludes leading import parameters and all RHS-local binders.
  declarationBindings :: CheckedTerm -> Either String ([] ((,) XName XType));
  declarationBindings (CheckedTerm _ _ bindings) = bindings
}
