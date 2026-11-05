{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenPrefix where {
 import MLF.Primitive;
 import Bootstrap.Types;
 import Bootstrap.Std;
 import Bootstrap.Separate hiding (interfaceFields,interfaceFingerprint,encodeInterface,encodeObject);
 import Bootstrap.CrateQuery hiding (encodeCached,sourceQueryKey);
 import qualified Bootstrap.Separate as Separate;
 import qualified Bootstrap.Data as D;
 import qualified Bootstrap.X.Pretty as Pretty;
 import qualified Bootstrap.SourceInference as Source;
 import qualified Bootstrap.Dependency as Dependency;
 import qualified Bootstrap.Map as M;
 import qualified Bootstrap.Set as S;
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
  encodeCached key object =
    if contextualCache key object
    then Separate.pack
           ((:) "MLF-QUERY-CACHE-2" ((:) key ((:) (Separate.encodeContextualObject object) [])))
    else Separate.pack
           ((:) "MLF-QUERY-CACHE-1"
              ((:) key
                 ((:) (encodeInterface (Separate.objectInterface object))
                    ((:) (encodeObject object) []))));
  sourceQueryKey crateId compilerHash prepared contracts datatypes =
    let { observed = S.fromList compareString
      (append (map fst (Source.groupBindings prepared))
        (append (map fst (Source.groupCandidateBindings prepared))
          (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member))
            (Source.groupOriginal prepared)))) } in
    let { relevant = M.filterWithKey (\name _ -> S.member compareString name observed) contracts } in
    node "MLF-SOURCE-CRATE-QUERY-5"
      ((:) crateId ((:) compilerHash
        ((:) (list (\member -> encodeMember (canonicalMember member)) (Source.groupMembers prepared))
        ((:) (list encodeBinding (Source.groupBindings prepared))
        ((:) (encodeDatatypeContext datatypes)
        ((:) (encodeSourceGroup prepared)
        ((:) (list encodeSourceContract (M.toList relevant)) [])))))));
}
