-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.Case where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Test.Assert as A;
  import qualified Bootstrap.Std as S;
  import qualified Test.Descriptor as D;
  import qualified Test.Expectation as E;
  import qualified Test.Outcome as O;
  -- IDs are stable machine identities; names remain human-readable labels.
  data Case = Case String String ([] String) (A.Test ());
  test :: String -> String -> [] String -> A.Test () -> Case;
  test identity label labels body = Case identity label labels body;
  id :: Case -> String;
  id (Case identity _ _ _) = identity;
  name :: Case -> String;
  name (Case _ label _ _) = label;
  tags :: Case -> [] String;
  tags (Case _ _ labels _) = labels;
  action :: Case -> A.Test ();
  action (Case _ _ _ body) = body;
  -- Classification is metadata: preserve the case ID, label and action exactly.
  classified :: [] String -> [] String -> Case -> Case;
  classified categories techniques (Case identity label labels body) =
    Case identity label
      (S.nubBy eqString
         (S.append labels
            (S.append (S.map (\name -> ("category:" ++ name)) categories)
               (S.map (\name -> ("technique:" ++ name)) techniques))))
      body;
  -- Independent metadata axes; vocabulary belongs to the consuming repository.
  described :: String -> String -> [] String -> [] String -> [] String -> Case -> Case;
  described group level inputs oracles purposes (Case identity label labels body) =
    Case identity label
      (S.nubBy eqString
         (S.append labels
            (S.append ((:) ("group:" ++ group) ((:) ("level:" ++ level) []))
               (S.concatMap (\((,) prefix values) -> S.map (\name -> (prefix ++ name)) values)
                  ((:) ((,) "input:" inputs)
                     ((:) ((,) "oracle:" oracles) ((:) ((,) "purpose:" purposes) [])))))))
      body;
  fromIO :: String -> [] String -> (,) String (IO ()) -> Case;
  fromIO identity labels ((,) label body) = test identity label labels (A.liftIO body);
  toLegacy :: Case -> (,) String (IO ());
  toLegacy entry = (,) (name entry) (A.orExit (action entry));
  -- v1 cases retain their original action and wire descriptor. No action runs here.
  descriptor :: Case -> D.Descriptor;
  descriptor entry =
    D.Descriptor (id entry) (name entry) 1 (tags entry) D.Required (E.Accept O.Runtime)
}
