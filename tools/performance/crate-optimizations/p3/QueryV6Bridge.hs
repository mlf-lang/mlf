{-# LANGUAGE OverloadedStrings #-}
module QueryV6Bridge (module Q, sourceQueryKeyWithContext, projectEmptyQuery, validateBridge) where
import Prelude
import Control.Exception (SomeException, evaluate, try)
import Control.Monad (forM_, unless)
import Bootstrap.CrateQuery as Q hiding (sourceQueryKeyWithContext)
import qualified Bootstrap.CrateQuery as Current
import qualified MLF.Primitive as P

-- Only the historical P3 empty-group controls use this bridge. Preserve every
-- field byte; change the explicit version and remove its provably empty table.
-- Nonempty source groups are rejected, not normalized. The separate maintained
-- QueryEncoding fixture independently expands and checks actual pooled scopes.
pack = concatMap (\s -> show (length s) ++ ":" ++ s)
unpack "" = []
unpack input = case break (== ':') input of
  (digits, ':' : rest) | not (null digits) && all (\c -> c >= '0' && c <= '9') digits ->
    let count = read digits :: Int
        (field, tail) = splitAt count rest
    in if count >= 0 && show count == digits && length field == count
       then field : unpack tail else error "noncanonical query bridge frame"
  _ -> error "invalid query bridge frame"

projectEmptyQuery :: P.String -> P.String
projectEmptyQuery input = P.textFromChars $ case unpack (P.textToChars input) of
  ["MLF-SOURCE-CRATE-QUERY-6", crate, compiler, "", bindings, context, source, contracts, ""] ->
    case unpack source of
      "prepared-source-group" : "" : _ ->
        pack ["MLF-SOURCE-CRATE-QUERY-5", crate, compiler, "", bindings, context, source, contracts]
      _ -> error "query bridge requires an empty original source group"
  _ -> error "query bridge requires v6 with empty lowered group and scope table"

sourceQueryKeyWithContext crate compiler prepared contracts context =
  projectEmptyQuery (Current.sourceQueryKeyWithContext crate compiler prepared contracts context)

validateBridge :: IO ()
validateBridge = do
  let input = "24:MLF-SOURCE-CRATE-QUERY-61:c1:p0:0:2:α😀36:21:prepared-source-group0:8:metadata0:0:"
      expected = "24:MLF-SOURCE-CRATE-QUERY-51:c1:p0:0:2:α😀36:21:prepared-source-group0:8:metadata0:"
      fields = unpack input
      replace index value = pack (take index fields ++ [value] ++ drop (index+1) fields)
  unless (P.textToChars (projectEmptyQuery (P.textFromChars input)) == expected)
    (error "query bridge changed literal Unicode fields")
  forM_ [expected, replace 3 "member", replace 8 "scope",
         replace 6 (pack ["prepared-source-group", "member"]), "0" ++ input, init input] $ \bad -> do
    result <- try (evaluate (P.stringLength (projectEmptyQuery (P.textFromChars bad))))
      :: IO (Either SomeException P.Int)
    case result of
      Left _ -> pure ()
      Right _ -> error "query bridge admitted an unsupported input"
