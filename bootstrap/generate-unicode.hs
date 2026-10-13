import Data.Char
main = do
  putStrLn "module Bootstrap.Unicode where"
  putStrLn "-- Generated from the seed compiler's Data.Char Unicode tables."
  putStrLn "-- Each string stores inclusive interval endpoints as Unicode scalars."
  putStrLn "unicodeMember : Int -> String -> Int -> Int -> Bool"
  putStrLn "unicodeMember c ranges lo hi = if lo >= hi then false else"
  putStrLn "  let mid = (lo + hi) / 2 in"
  putStrLn "  let begin = stringCodeAt ranges (2 * mid) in"
  putStrLn "  let end = stringCodeAt ranges (2 * mid + 1) in"
  putStrLn "  if c < begin then unicodeMember c ranges lo mid else"
  putStrLn "  if c <= end then true else unicodeMember c ranges (mid + 1) hi"
  mapM_ emit [("isAlpha",isAlpha),("isAlphaNum",isAlphaNum),("isUpper",isUpper),("isLower",isLower),("isSpace",isSpace)]
  where
    emit (n,f) = do
      let rs = ranges f
      putStrLn (n ++ " : Int -> Bool")
      putStrLn (n ++ " c = if c < 128 then " ++ ascii n ++ " else unicodeMember c " ++ n ++ "Ranges 0 " ++ show (length rs))
      putStrLn (n ++ "Ranges : String")
      putStrLn (n ++ "Ranges = \"" ++ concatMap (\(a,b) -> "\\" ++ show a ++ "\\&\\" ++ show b ++ "\\&") rs ++ "\"")
    ascii "isAlpha" = "((c >= 65 && c <= 90) || (c >= 97 && c <= 122))"
    ascii "isAlphaNum" = "((c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122))"
    ascii "isUpper" = "(c >= 65 && c <= 90)"
    ascii "isLower" = "(c >= 97 && c <= 122)"
    ascii "isSpace" = "(c == 32 || (c >= 9 && c <= 13))"
    ascii _ = "false"
    ranges f = foldr step [] $ filter (f . chr) [0..0x10ffff]
    step a ((b,c):rest) | a+1 == b = (a,c):rest
    step a rest = (a,a):rest
