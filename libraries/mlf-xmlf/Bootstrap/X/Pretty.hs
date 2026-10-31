-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Pretty where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Primitive as P;
  import Bootstrap.Kind;
  variable (XTyVar n) = if (n < 0) then ("z" ++ (if n == (-9223372036854775808) then "9223372036854775808" else showInt (0 - n))) else ("a" ++ showInt n);
  name (XName i hint) = (hint ++ ("_" ++ showInt i));
  parenthesize condition s = if condition then ("(" ++ (s ++ ")")) else s;
  prettyType :: XType -> String;
  prettyType t = typeAt 0 t;
  typeAt :: Int -> XType -> String;
  typeAt p t =
    case t of {
      XVar a -> variable a;
      XBot -> "bot";
      XBotKind k -> ("bot[" ++ (prettyKind k ++ "]"));
      XArrow a b -> parenthesize (p > 1) (typeAt 2 a ++ (" -> " ++ typeAt 1 b));
      XCon c [] -> c;
      XCon c ts -> parenthesize (p > 2) (L.intercalate " " ((:) c (L.map (typeAt 3) ts)));
      XApply f a -> parenthesize (p > 2) (typeAt 2 f ++ (" " ++ typeAt 3 a));
      XForall a XBot b -> parenthesize (p > 0) ("forall " ++ (variable a ++ (". " ++ typeAt 0 b)));
      XForall a bound b ->
        parenthesize (p > 0)
          ("forall (" ++ (variable a ++ (" >= " ++ (typeAt 0 bound ++ ("). " ++ typeAt 0 b)))))
    };
  prettyComputation :: XComputation -> String;
  prettyComputation p =
    case p of {
      XRefl -> "id";
      XBottom t -> ("bot(" ++ (prettyType t ++ ")"));
      XHyp a -> ("hyp(" ++ (variable a ++ ")"));
      XInner q -> ("inner(" ++ (prettyComputation q ++ ")"));
      XOuter a q -> ("outer(" ++ (variable a ++ (", " ++ (prettyComputation q ++ ")"))));
      XElim -> "elim";
      XIntro a -> ("intro(" ++ (variable a ++ ")"));
      XIntroKind a k -> ("intro(" ++ (variable a ++ (" : " ++ (prettyKind k ++ ")"))));
      XThen a b -> (prettyComputation a ++ ("; " ++ prettyComputation b))
    };
  prettyTerm :: XTerm -> String;
  prettyTerm t = termAt 0 t;
  termAt :: Int -> XTerm -> String;
  termAt p t =
    case t of {
      XVarTerm n -> name n;
      XAbs n ty b ->
        parenthesize (p > 0)
          ("\\(" ++ (name n ++ (" : " ++ (prettyType ty ++ (") -> " ++ termAt 0 b)))));
      XApp f a -> parenthesize (p > 1) (termAt 1 f ++ (" " ++ termAt 2 a));
      XTypeAbs a bound b ->
        parenthesize (p > 0)
          ("/\\(" ++ (variable a ++ (" >= " ++ (prettyType bound ++ (") -> " ++ termAt 0 b)))));
      XTypeApp a phi -> (termAt 2 a ++ ("[" ++ (prettyComputation phi ++ "]")));
      XLet n a b ->
        parenthesize (p > 0)
          ("let " ++ (name n ++ (" = " ++ (termAt 0 a ++ (" in " ++ termAt 0 b)))));
      XLetRec ds b ->
        parenthesize (p > 0)
          ("letrec { " ++
           (L.intercalate "; " (L.map prettyBinding ds) ++ (" } in " ++ termAt 0 b)));
      XIntTerm n -> showInt n;
      XDoubleTerm n -> prettyDouble n;
      XBoolTerm b -> if b then "true" else "false";
      XStringTerm s -> prettyString s;
      XPrimitive primitive ts ->
        ("primitive " ++
         (P.primitiveName primitive ++ ("(" ++ (L.intercalate ", " (L.map prettyType ts) ++ ")"))));
      XConstructor c ts ->
        ("construct " ++ (c ++ ("(" ++ (L.intercalate ", " (L.map prettyType ts) ++ ")"))));
      XCase a result bs ->
        parenthesize (p > 0)
          ("case " ++
           (termAt 0 a ++
            (" return " ++
             (prettyType result ++
              (" of { " ++ (L.intercalate "; " (L.map prettyAlternative bs) ++ " }"))))));
      XWithData ds b ->
        (L.intercalate "" (L.map (\d -> (D.prettyDeclaration d ++ "\n")) ds) ++ termAt 0 b)
    };
  prettyBinding :: (,,) XName XType XTerm -> String;
  prettyBinding ((,,) n ty a) = (name n ++ (" : " ++ (prettyType ty ++ (" = " ++ termAt 0 a))));
  prettyAlternative :: XAlternative -> String;
  prettyAlternative (XAlternative pat b) = (prettyPattern pat ++ (" -> " ++ termAt 0 b));
  prettyPattern :: XPattern -> String;
  prettyPattern (XConstructorPattern c ns) = L.intercalate " " ((:) c (L.map maybeName ns));
  prettyPattern (XDefaultPattern n) = maybeName n;
  maybeName Nothing = "_";
  maybeName (Just n) = name n;
  -- Exact canonical chunks for consumers that compose text summaries.
  -- The ordinary formatting functions above remain independent byte oracles.
  nameChunks (XName identity hint) rest = (:) hint ((:) "_" ((:) (showInt identity) rest));
  maybeNameChunks Nothing rest = (:) "_" rest;
  maybeNameChunks (Just value) rest = nameChunks value rest;
  parenthesized :: Bool -> ([] String -> [] String) -> [] String -> [] String;
  parenthesized condition body rest =
    if condition then (:) "(" (body ((:) ")" rest)) else body rest;
  separated :: forall a. String -> (a -> [] String -> [] String) -> [] a -> [] String -> [] String;
  separated separator render values rest = case values of {
    [] -> rest;
    (:) first remaining -> render first (separatedTail separator render remaining rest)
  };
  separatedTail :: forall a. String -> (a -> [] String -> [] String) -> [] a -> [] String -> [] String;
  separatedTail separator render values rest = case values of {
    [] -> rest;
    (:) first remaining -> (:) separator (render first (separatedTail separator render remaining rest))
  };
  typeChunks :: Int -> XType -> [] String -> [] String;
  typeChunks p t rest = case t of {
    XVar a -> (:) (variable a) rest;
    XBot -> (:) "bot" rest;
    XBotKind k -> (:) "bot[" ((:) (prettyKind k) ((:) "]" rest));
    XArrow a b -> parenthesized (p > 1) (\tail -> typeChunks 2 a ((:) " -> " (typeChunks 1 b tail))) rest;
    XCon c [] -> (:) c rest;
    XCon c ts -> parenthesized (p > 2) (\tail -> (:) c (separatedTail " " (typeChunks 3) ts tail)) rest;
    XApply f a -> parenthesized (p > 2) (\tail -> typeChunks 2 f ((:) " " (typeChunks 3 a tail))) rest;
    XForall a XBot b -> parenthesized (p > 0) (\tail -> (:) "forall " ((:) (variable a) ((:) ". " (typeChunks 0 b tail)))) rest;
    XForall a bound b -> parenthesized (p > 0) (\tail -> (:) "forall (" ((:) (variable a) ((:) " >= " (typeChunks 0 bound ((:) "). " (typeChunks 0 b tail)))))) rest
  };
  computationChunks :: XComputation -> [] String -> [] String;
  computationChunks p rest = case p of {
    XRefl -> (:) "id" rest;
    XBottom t -> (:) "bot(" (typeChunks 0 t ((:) ")" rest));
    XHyp a -> (:) "hyp(" ((:) (variable a) ((:) ")" rest));
    XInner q -> (:) "inner(" (computationChunks q ((:) ")" rest));
    XOuter a q -> (:) "outer(" ((:) (variable a) ((:) ", " (computationChunks q ((:) ")" rest))));
    XElim -> (:) "elim" rest;
    XIntro a -> (:) "intro(" ((:) (variable a) ((:) ")" rest));
    XIntroKind a k -> (:) "intro(" ((:) (variable a) ((:) " : " ((:) (prettyKind k) ((:) ")" rest))));
    XThen a b -> computationChunks a ((:) "; " (computationChunks b rest))
  };
  termChunks :: Int -> XTerm -> [] String -> [] String;
  termChunks p t rest = case t of {
    XVarTerm n -> nameChunks n rest;
    XAbs n ty b -> parenthesized (p > 0) (\tail -> (:) "\\(" (nameChunks n ((:) " : " (typeChunks 0 ty ((:) ") -> " (termChunks 0 b tail)))))) rest;
    XApp f a -> parenthesized (p > 1) (\tail -> termChunks 1 f ((:) " " (termChunks 2 a tail))) rest;
    XTypeAbs a bound b -> parenthesized (p > 0) (\tail -> (:) "/\\(" ((:) (variable a) ((:) " >= " (typeChunks 0 bound ((:) ") -> " (termChunks 0 b tail)))))) rest;
    XTypeApp a phi -> termChunks 2 a ((:) "[" (computationChunks phi ((:) "]" rest)));
    XLet n a b -> parenthesized (p > 0) (\tail -> (:) "let " (nameChunks n ((:) " = " (termChunks 0 a ((:) " in " (termChunks 0 b tail)))))) rest;
    XLetRec ds b -> parenthesized (p > 0) (\tail -> (:) "letrec { " (separated "; " bindingChunks ds ((:) " } in " (termChunks 0 b tail)))) rest;
    XIntTerm n -> (:) (showInt n) rest;
    XDoubleTerm n -> (:) (prettyDouble n) rest;
    XBoolTerm b -> (:) (if b then "true" else "false") rest;
    XStringTerm s -> (:) (prettyString s) rest;
    XPrimitive primitive ts -> (:) "primitive " ((:) (P.primitiveName primitive) ((:) "(" (separated ", " (typeChunks 0) ts ((:) ")" rest))));
    XConstructor c ts -> (:) "construct " ((:) c ((:) "(" (separated ", " (typeChunks 0) ts ((:) ")" rest))));
    XCase a result bs -> parenthesized (p > 0) (\tail -> (:) "case " (termChunks 0 a ((:) " return " (typeChunks 0 result ((:) " of { " (separated "; " alternativeChunks bs ((:) " }" tail))))))) rest;
    XWithData ds b -> L.foldr (\d tail -> (:) (D.prettyDeclaration d) ((:) "\n" tail)) (termChunks 0 b rest) ds
  };
  bindingChunks :: (,,) XName XType XTerm -> [] String -> [] String;
  bindingChunks ((,,) n ty a) rest = nameChunks n ((:) " : " (typeChunks 0 ty ((:) " = " (termChunks 0 a rest))));
  alternativeChunks :: XAlternative -> [] String -> [] String;
  alternativeChunks (XAlternative pat b) rest = patternChunks pat ((:) " -> " (termChunks 0 b rest));
  patternChunks :: XPattern -> [] String -> [] String;
  patternChunks pattern rest = case pattern of {
    XConstructorPattern c ns -> (:) c (separatedTail " " (\n tail -> maybeNameChunks n tail) ns rest);
    XDefaultPattern n -> maybeNameChunks n rest
  };
  prettyString :: String -> String;
  prettyString s = ("\"" ++ (escapeFrom s 0 ++ "\""));
  escapeFrom :: String -> Int -> String;
  escapeFrom s i =
    if (i >= stringLength s) then "" else (escapeScalar (stringCodeAt s i) ++ escapeFrom s (i + 1));
  escapeScalar :: Int -> String;
  escapeScalar c =
    if (c == 34)
    then "\\\""
    else if (c == 92)
         then "\\\\"
         else if (c == 10)
              then "\\n"
              else if (c == 13)
                   then "\\r"
                   else if (c == 9)
                        then "\\t"
                        else if ((c < 32) || (c == 127))
                             then ("\\" ++ (showInt c ++ "\\&"))
                             else stringFromCode c;
  -- Emit the exact finite dyadic value as decimal, preserving even subnormals
  -- and negative zero without relying on the host's formatting convention.
  prettyDouble :: Double -> String;
  prettyDouble x =
    let {
      bits = doubleToBits x
    } in
    let {
      negative = (bits < 0)
    } in
    let {
      magnitude = andInt bits 9223372036854775807
    } in
    let {
      exponent = quotInt magnitude 4503599627370496
    } in
    let {
      fraction = remInt magnitude 4503599627370496
    } in
    let {
      mantissa = if (exponent == 0) then fraction else (fraction + 4503599627370496)
    } in
    let {
      power = if (exponent == 0) then (0 - 1074) else (exponent - 1075)
    } in
    if (exponent == 2047)
    then if (fraction == 0) then ((if negative then "-" else "") ++ "Infinity") else "NaN"
    else ((if negative then "-" else "") ++ decimalDyadic mantissa power);
  powerInt :: Int -> Int -> Int;
  powerInt base exponent =
    if (exponent == 0)
    then 1
    else let {
           half = powerInt base (quotInt exponent 2)
         } in
         ((half * half) * (if (remInt exponent 2 == 0) then 1 else base));
  -- Exact decimal formatting needs unbounded intermediate powers even though
  -- the source literal and its IEEE bit pattern have a fixed 64-bit width.
  powerInteger :: Integer -> Int -> Integer;
  powerInteger base exponent =
    if exponent == 0 then intToInteger 1
    else let { half = powerInteger base (quotInt exponent 2) } in
      mulInteger (mulInteger half half)
        (if remInt exponent 2 == 0 then intToInteger 1 else base);
  decimalDyadic :: Int -> Int -> String;
  decimalDyadic mantissa power =
    if (mantissa == 0)
    then "0.0"
    else if (power >= 0)
         then (showInteger (mulInteger (intToInteger mantissa) (powerInteger (intToInteger 2) power)) ++ ".0")
         else let {
                places = (0 - power)
              } in
              let {
                digits = showInteger (mulInteger (intToInteger mantissa) (powerInteger (intToInteger 5) places))
              } in
              let {
                count = stringLength digits
              } in
              if (count > places)
              then (stringSlice digits 0 (count - places) ++
                    ("." ++ stringSlice digits (count - places) places))
              else ("0." ++ (zeroes (places - count) ++ digits));
  zeroes :: Int -> String;
  zeroes n = if (n <= 0) then "" else ("0" ++ zeroes (n - 1))
}
