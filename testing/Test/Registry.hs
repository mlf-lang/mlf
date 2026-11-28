-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.Registry where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Set as Set;
  import qualified Test.Descriptor as D;
  ensure condition message = if condition then Right () else Left message;
  unique values = S.length values == Set.size (Set.fromList compareString values);
  validIds :: [] String -> Either String ();
  validIds values =
    do {
      ensure (S.all D.validId values) "invalid test ID";
      ensure (unique values) "duplicate test ID"
    };
  -- Both sides are inventories, not sets made by silently dropping duplicates.
  exactInventory :: [] String -> [] String -> Either String ();
  exactInventory expected observed =
    do {
      validIds expected;
      validIds observed;
      ensure
        ((S.length expected == S.length observed) &&
         Set.isSubsetOf compareString (Set.fromList compareString observed) (Set.fromList compareString expected))
        "missing or unknown test ID"
    };
  validate :: [] D.Descriptor -> Either String ();
  validate entries =
    do {
      ensure (S.not (S.null entries)) "empty test inventory";
      validIds (S.map D.id entries);
      S.mapM_ D.validate entries
    };
  select :: [] String -> [] D.Descriptor -> Either String ([] D.Descriptor);
  select identities entries =
    do {
      validate entries;
      validIds identities;
      ensure (S.not (S.null identities)) "empty required test selection";
      let {
        selected = Set.fromList compareString identities;
        available = Set.fromList compareString (S.map D.id entries)
      };
      ensure (Set.isSubsetOf compareString selected available) "unknown test ID";
      Right (S.filter (\entry -> Set.member compareString (D.id entry) selected) entries)
    }
}
