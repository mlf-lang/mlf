{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenPrefix where {
 import MLF.Primitive;
 import Bootstrap.Types;
 import Bootstrap.Std;
 import Bootstrap.Separate hiding (interfaceFields,interfaceFingerprint,encodeInterface,encodeObject);
 import qualified Bootstrap.Data as D;
 import qualified Bootstrap.X.Pretty as Pretty;
  interfaceFields i =
    let {
      metadata =
        unlines
          (append (map D.prettyDeclaration (unitData i))
             (append (map prettyClass (unitClasses i))
                (map (\p -> prettyInstance (snd p)) (unitInstances i))))
    } in
    let {
      bindings =
        pack
          (map (\((,) n t) -> pairEncoding ((,) n (Pretty.prettyType (normalType t))))
             (unitBindings i))
    } in
    (:) "MLFI-4"
      ((:) (unitName i)
         ((:) (pack (map pairEncoding (unitDependencies i)))
            ((:) (pack (map entityEncoding (unitExports i)))
               ((:) metadata ((:) (pack (map fst (unitInstances i))) ((:) bindings []))))));
  interfaceFingerprint i = fingerprint (pack (interfaceFields i));
  encodeInterface i = pack (snoc (interfaceFields i) (unitObjectFingerprint i));
  encodeObject object =
    let {
      i = objectInterface object
    } in
    pack
      ((:) "MLFO-1"
         ((:) (unitName i)
            ((:) (interfaceFingerprint i) ((:) (Pretty.prettyTerm (objectTerm object)) []))));
}
