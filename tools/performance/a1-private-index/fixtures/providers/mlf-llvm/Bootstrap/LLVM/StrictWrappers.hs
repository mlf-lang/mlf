-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.StrictWrappers where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.LLVM.Optimize as O;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.StrictFields as F;
  -- A single-constructor unary datatype can share its field's representation
  -- only when every construction stores an already evaluated field. Ordinary
  -- lazy wrappers, partial applications, and escaping constructors are excluded.
  -- This is a whole-program erased optimization after independent checking;
  -- source types, module interfaces, and canonical-pointer proofs stay intact.
  single :: DataDecl -> [] String;
  single declaration =
    case case declaration of {
           DataDecl n ps cs -> cs;
           DataDeclK n ps cs -> cs
         } of {
      (:) (ConstructorDecl c ((:) field [])) [] -> (:) c [];
      _ -> []
    };
  candidates :: [] DataDecl -> Map String ((,) Int Int) -> XErased -> Set String;
  candidates declarations constructors expression =
    let {
      facts = F.inferEvaluated (M.map L.snd constructors) (A.analyze expression) expression
    } in
    S.fromList compareString
      (L.filter
         (\c ->
            case M.lookup compareString c facts of {
              Just ((:) True []) -> True;
              _ -> False
            })
         (L.concatMap single declarations));
  sequence :: XErased -> XErased -> XErased;
  sequence first second = XEApp (XEApp (XEPrimitive PSeq) first) second;
  bindForced :: Maybe XName -> XErased -> XErased -> XErased;
  bindForced optional value body =
    case optional of {
      Nothing -> sequence value body;
      Just name -> XELet name value (sequence (XEVar name) body)
    };
  unaryCase :: Set String -> [] XErasedAlternative -> Bool;
  unaryCase wrappers alternatives =
    L.any
      (\alternative ->
         case alternative of {
           XErasedAlternative (XConstructorPattern c ((:) field [])) body ->
             S.member compareString c wrappers;
           _ -> False
         })
      alternatives;
  select :: Set String -> XErased -> [] XErasedAlternative -> Maybe XErased;
  select wrappers subject alternatives =
    case alternatives of {
      [] -> Nothing;
      (:) (XErasedAlternative pattern body) rest ->
        case pattern of {
          XConstructorPattern c ((:) field []) ->
            if S.member compareString c wrappers
            then Just (bindForced field subject body)
            else select wrappers subject rest;
          XDefaultPattern optional -> Just (bindForced optional subject body);
          _ -> select wrappers subject rest
        }
    };
  rewrite :: Set String -> XErased -> O.Fresh XErased;
  rewrite wrappers expression =
    do {
      normalized <- O.children (rewrite wrappers) expression;
      O.freshPure
        (case normalized of {
           XEApp (XEConstructor c) field ->
             if S.member compareString c wrappers then field else normalized;
           XECase subject alternatives ->
             if unaryCase wrappers alternatives
             then L.fromMaybe normalized (select wrappers subject alternatives)
             else normalized;
           _ -> normalized
         })
    };
  optimize :: [] DataDecl -> Map String ((,) Int Int) -> XErased -> XErased;
  optimize declarations constructors expression =
    let {
      wrappers = candidates declarations constructors expression
    } in
    if S.null wrappers
    then expression
    else L.fst (O.runFresh (rewrite wrappers expression) (O.maxIdentity expression + 1))
}
