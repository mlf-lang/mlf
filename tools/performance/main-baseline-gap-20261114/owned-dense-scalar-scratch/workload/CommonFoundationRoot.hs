-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module CommonFoundationRoot (main) where {
  import MLF.Primitive;
  import qualified Bootstrap.Fresh as F0;
  import qualified Bootstrap.Host as F1;
  import qualified Bootstrap.IndexVec as F2;
  import qualified Bootstrap.IntMap as F3;
  import qualified Bootstrap.IntRank as F4;
  import qualified Bootstrap.IntSet as F5;
  import qualified Bootstrap.IntTree as F6;
  import qualified Bootstrap.Map as F7;
  import qualified Bootstrap.Regex as F8;
  import qualified Bootstrap.ST as F9;
  import qualified Bootstrap.Set as F10;
  import qualified Bootstrap.Std as F11;
  import qualified Bootstrap.Types as F12;
  import qualified Bootstrap.Unicode as F13;
  import qualified Bootstrap.Version as F14;
  primitiveBool :: Bool;
  primitiveBool = True;
  main :: Bool;
  main = primitiveBool
}
