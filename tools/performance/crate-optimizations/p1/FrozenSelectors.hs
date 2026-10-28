-- Frozen test oracle: exact original definitions, not regenerated from candidate.
-- Only representation datatypes come from Bootstrap.Module. No candidate
-- selector, visibility, identity, lookup, or interface helper is called.
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenSelectors where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Module (ModuleSpace(..), Role(..), Entity(..), Interface(..));
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.Lexer as Lexer;
  owner (Entity name _ _) = name;
  spelling (Entity _ name _) = name;
  role (Entity _ _ category) = category;
  space entity =
    case role entity of {
      Datatype -> Types;
      Class -> Types;
      BuiltinType -> Types;
      ManagedConstraint -> Types;
      _ -> Terms
    };
  spaceCode :: ModuleSpace -> Int;
  spaceCode Terms = 0;
  spaceCode Types = 1;
  compareSpace a b = compareInt (spaceCode a) (spaceCode b);
  compareKey a b = comparePair compareSpace compareString a b;
  roleCode :: Role -> Int;
  roleCode Value = 0;
  roleCode Datatype = 1;
  roleCode Class = 2;
  roleCode (Constructor _) = 3;
  roleCode (Method _) = 4;
  roleCode BuiltinType = 5;
  roleCode (Primitive _) = 6;
  roleCode (Boolean _) = 7;
  roleCode ManagedConstraint = 8;
  compareRole a b =
    let {
      first = compareInt (roleCode a) (roleCode b)
    } in
    if (first /= 0)
    then first
    else case a of {
           Constructor name ->
             case b of {
               Constructor other -> compareString name other;
               _ -> 0
             };
           Method name ->
             case b of {
               Method other -> compareString name other;
               _ -> 0
             };
           Primitive p ->
             case b of {
               Primitive q -> P.comparePrimitive p q;
               _ -> 0
             };
           Boolean x ->
             case b of {
               Boolean y -> compareInt (if x then 1 else 0) (if y then 1 else 0);
               _ -> 0
             };
           _ -> 0
         };
  compareEntity a b =
    let {
      ownerOrder = compareString (owner a) (owner b)
    } in
    let {
      name = compareString (spelling a) (spelling b)
    } in
    if (ownerOrder /= 0)
    then ownerOrder
    else if (name /= 0) then name else compareRole (role a) (role b);
  isRole category entity = (compareRole category (role entity) == 0);
  parent entity =
    case role entity of {
      Constructor name -> Just ((,) (owner entity) name);
      Method name -> Just ((,) (owner entity) name);
      Boolean _ -> Just ((,) "Prelude" "Bool");
      _ -> Nothing
    };
  emptyInterface = Interface M.empty;
  interface entities =
    Interface
      (M.fromListWith compareKey (Set.union compareEntity)
         (map (\entity -> (,) ((,) (space entity) (spelling entity)) (Set.singleton entity))
            entities));
  interfaceMap (Interface entries) = entries;
  interfaceEntries (Interface entries) = M.toList entries;
  union (Interface a) (Interface b) =
    Interface (M.unionWith compareKey (Set.union compareEntity) a b);
  lookupEntities namespace name (Interface entries) =
    M.findWithDefault compareKey Set.empty ((,) namespace name) entries;
  visible (Interface entries) = Set.unions compareEntity (M.elems entries);

  sourceReference name = if Lexer.textStartsAt name 0 "$MLF.Source." then stringSlice name 12 (stringLength name - 12) else name;
  label entity = (owner entity ++ ("." ++ spelling entity));
  lookupEntity namespace name env =
    case Set.toList (lookupEntities namespace (sourceReference name) env) of {
      [] -> Left ("name is not in scope: " ++ name);
      (:) entity [] -> Right entity;
      entities ->
        Left ("ambiguous name " ++ (name ++ (": " ++ intercalate ", " (map label entities))))
    };
  isConstructor entity =
    case role entity of {
      Constructor _ -> True;
      Boolean _ -> True;
      _ -> False
    };
  selectItem :: Bool -> Interface -> Export -> Either String Interface;
  selectItem hiding env item =
    case item of {
      ExportValue name ->
        do {
          entity <- lookupEntity Terms name env;
          Right (interface ((:) entity []))
        };
      ExportType name Abstract ->
        if hiding
        then do {
               let {
                 matches =
                   Set.union compareEntity (lookupEntities Types name env)
                     (Set.filter isConstructor (lookupEntities Terms name env))
               };
               when (Set.null matches) (Left ("name is not exported: " ++ name));
               Right (interface (Set.toList matches))
             }
        else selectType env name Abstract;
      ExportType name members -> selectType env name members;
      ExportModule _ -> Left "module re-exports are only allowed in export lists"
    };
  selectType env name members =
    do {
      ty <- lookupEntity Types name env;
      let {
        children =
          filter
            (\entity ->
               eqMaybe (eqPair eqString eqString) (parent entity)
                 (Just ((,) (owner ty) (spelling ty))))
            (Set.toList (visible env))
      };
      chosen <-
        case members of {
          Abstract -> Right [];
          AllMembers -> Right children;
          Members names ->
            mapM
              (\child ->
                 case filter (\entity -> eqString child (spelling entity)) children of {
                   (:) entity [] -> Right entity;
                   _ -> Left (child ++ (" is not a visible member of " ++ name))
                 })
              names
        };
      Right (interface ((:) ty chosen))
    };

  partialSelectItem hiding env item =
    case item of {
      ExportModule _ -> emptyInterface;
      ExportValue name -> interface (Set.toList (lookupEntities Terms name env));
      ExportType name Abstract ->
        if hiding
        then interface
               (Set.toList
                  (Set.union compareEntity (lookupEntities Types name env)
                     (Set.filter isConstructor (lookupEntities Terms name env))))
        else interface (Set.toList (lookupEntities Types name env));
      ExportType name members ->
        let {
          types = lookupEntities Types name env
        } in
        let {
          parents = map (\entity -> (,) (owner entity) (spelling entity)) (Set.toList types)
        } in
        let {
          children =
            filter
              (\entity ->
                 case parent entity of {
                   Nothing -> False;
                   Just identity -> elem (eqPair eqString eqString) identity parents
                 })
              (Set.toList (visible env))
        } in
        let {
          chosen =
            case members of {
              Abstract -> [];
              AllMembers -> children;
              Members names -> filter (\entity -> elem eqString (spelling entity) names) children
            }
        } in
        interface (append (Set.toList types) chosen)
    };

}
