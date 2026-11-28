-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.NameEncoding where {
  import MLF.Primitive;
  import Bootstrap.Types;
  -- Versioned, injective identifier components. The result has only ASCII
  -- letters/digits; underscore separates whole components. z introduces a
  -- lowercase scalar hex escape terminated by z; a literal z is doubled.
  compactNameCode code =
    (code >= 48 && code <= 57) || (code >= 65 && code <= 90) ||
    (code >= 97 && code < 122);
  compactNameHex code = if code < 16 then stringFromCode
    (if code < 10 then 48 + code else 87 + code)
    else compactNameHex (unsignedShiftRInt code 4) ++ compactNameHex (andInt code 15);
  compactNameChunks text start position =
    if position == stringLength text then [stringSlice text start (position - start)]
    -- Produce a list cell after a bounded ASCII run. Native O0 evaluation
    -- need not tail-call the scan; never traverse an arbitrary name before
    -- giving the consuming concat loop its next finite fragment.
    else if position - start == 256 then
      (:) (stringSlice text start 256) (compactNameChunks text position position)
    else let { code = stringCodeAt text position } in
      if compactNameCode code then compactNameChunks text start (position + 1)
      else (:) (stringSlice text start (position - start))
        ((:) (if code == 122 then "zz" else if code == 58 then "z3az" else "z" ++ compactNameHex code ++ "z")
          (compactNameChunks text (position + 1) (position + 1)));
  compactName text = concatStringList (compactNameChunks text 0 0);
}
