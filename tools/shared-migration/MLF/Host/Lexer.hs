module MLF.Host.Lexer (Token(..), scan, virtual) where

import Data.Char (isAlpha, isAlphaNum, isSpace, isDigit, isHexDigit)

-- Positions count Unicode scalars, as Bootstrap.Lexer does. Literal spelling is
-- retained: the converter must not rewrite embedded guest programs.
data Token = Token { spelling :: String, line :: Int, column :: Int,
                     endLine :: Int, endColumn :: Int } deriving (Eq, Show)

virtual :: String -> Token -> Token
virtual s t = Token s (line t) (column t) (line t) (column t)

scan :: FilePath -> String -> Either String ([Token], Token)
scan file = go 1 1
  where
    err l c message = Left (file ++ ":" ++ show l ++ ":" ++ show c ++ ": " ++ message)
    advance l c '\n' = (l+1,1)
    advance l c '\t' = (l,c+8-(c-1) `mod` 8)
    advance l c _ = (l,c+1)
    move l c chars = foldl (\(a,b) ch -> advance a b ch) (l,c) chars
    go l c [] = Right ([],Token "" l c l c)
    go l c input@(ch:rest)
      | isSpace ch = let (a,b)=advance l c ch in go a b rest
      | take 2 input == "--" = let { (comment,tail')=break (=='\n') input; (a,b)=move l c comment } in go a b tail'
      | take 2 input == "{-" = comment 1 l (c+2) (drop 2 input)
      | ch == '"' = do
          (literal,tail') <- quoted l c ['"'] rest
          emit l c literal tail'
      | isAlpha ch || ch == '_' || ch == '\'' =
          let (word,tail')=span (\x -> isAlphaNum x || x=='_' || x=='\'') input
          in emit l c word tail'
      | isDigit ch = let (word,tail')=number input in emit l c word tail'
      | ch `elem` ":!#$%&*+./<=>?@\\^|-~" =
          let (word,tail')=span (`elem` ":!#$%&*+./<=>?@\\^|-~") input
          in emit l c word tail'
      | otherwise = emit l c [ch] rest
    emit l c word rest = let (a,b)=move l c word in do
      (tokens,finish) <- go a b rest
      Right (Token word l c a b:tokens,finish)
    comment _ l c [] = err l c "unterminated comment"
    comment depth l c input
      | take 2 input == "{-" = comment (depth+1) l (c+2) (drop 2 input)
      | take 2 input == "-}" = if depth==1 then go l (c+2) (drop 2 input)
                              else comment (depth-1) l (c+2) (drop 2 input)
    comment depth l c (ch:rest) = let (a,b)=advance l c ch in comment depth a b rest
    quoted l c _ [] = err l c "unterminated string"
    quoted _ _ rev ('"':rest) = Right (reverse ('"':rev),rest)
    quoted l c rev ('\\':rest) = case rest of
      [] -> err l c "unterminated string escape"
      x:xs | isSpace x -> let (gap,tail')=span isSpace rest in case tail' of
        '\\':ys -> quoted l c (reverse ('\\':gap++"\\")++rev) ys
        _ -> err l c "string gap must end with backslash"
      x:xs -> quoted l c (x:'\\':rev) xs
    quoted l c rev (x:xs)
      | fromEnum x <= 26 = err l c "unescaped control character in string"
      | otherwise = quoted l c (x:rev) xs
    number input
      | take 2 input `elem` ["0x","0X"] = let (a,b)=span isHexDigit (drop 2 input) in (take 2 input++a,b)
      | take 2 input `elem` ["0o","0O"] = let (a,b)=span (`elem` "01234567") (drop 2 input) in (take 2 input++a,b)
      | otherwise = let (digits,rest)=span isDigit input
                        (fraction,tail')=case rest of
                          '.':x:xs | isDigit x -> let (a,b)=span isDigit (x:xs) in ('.':a,b)
                          _ -> ("",rest)
                    in case tail' of
                      e:xs | e `elem` "eE" ->
                        let (sign,ys)=case xs of { a:as | a `elem` "+-" -> ([a],as); _ -> ("",xs) }
                            (exponent,zs)=span isDigit ys
                        in if null exponent then (digits++fraction,tail') else (digits++fraction++[e]++sign++exponent,zs)
                      _ -> (digits++fraction,tail')
