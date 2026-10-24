-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.Mlfpkg where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Version as Version;
  import qualified Package.OS as O;
  import qualified Package.Command as C;
  main =
    do {
      args <- O.allArguments;
      let {
        matchValueShared1 = args
      } in
      case matchValueShared1 of {
        (:) matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "--implementation-identity"
          then case matchValueShared3 of {
                 [] -> putStrLn ("MLF/shared-haskell-v1 " ++ implementationHost);
                 _ -> C.run args
               }
          else if MLF.Primitive.eqString matchValueShared2 "--version"
          then case matchValueShared3 of {
                 [] -> putStrLn ("mlfpkg " ++ Version.version);
                 _ -> C.run args
               }
          else C.run args;
        _ -> C.run args
      }
    }
}
