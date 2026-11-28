{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module HistoricalHeaderNames where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Separate as Separate;
  definitionName :: String -> Modules.Entity -> String;
  definitionName identity = definitionNameEncoded (Separate.encoded identity);
  ordinaryDefinitionName :: String -> Modules.Entity -> String;
  ordinaryDefinitionName identity = ordinaryDefinitionNameEncoded (Separate.encoded identity);
  -- Partial application shares the immutable crate prefix across its exports.
  -- The ordinary encoder and complete entity identity remain unchanged.
  definitionNameEncoded :: String -> Modules.Entity -> String;
  definitionNameEncoded encodedIdentity entity =
    case Separate.managedBuiltinName entity of {
      Just name -> name;
      Nothing -> ordinaryDefinitionNameEncoded encodedIdentity entity
    };
  ordinaryDefinitionNameEncoded :: String -> Modules.Entity -> String;
  ordinaryDefinitionNameEncoded encodedIdentity entity =
    if (eqString (Modules.owner entity) "Prelude" || Modules.isRole Modules.BuiltinType entity)
    then Separate.stableName entity
    else ((if ((Modules.compareSpace (Modules.space entity) Modules.Types == 0) ||
               (case Modules.role entity of {
                  Modules.Constructor _ -> True;
                  _ -> False
                }))
           then "Module_"
           else "module_") ++
          (encodedIdentity ++
           ("z_" ++ Separate.encoded (Separate.entityEncoding entity))));
}
