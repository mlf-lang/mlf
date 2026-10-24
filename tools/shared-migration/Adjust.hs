module Main where

import Control.Monad (forM,unless)
import Data.List (intercalate,sort,sortOn,isPrefixOf)
import System.Environment (getArgs)
import System.Exit (die)
import System.Directory (createDirectoryIfMissing)
import System.FilePath (takeDirectory)
import MLF.Host.Parser
import MLF.Host.Lexer
import MLF.Host.Syntax
import Hierarchy
import Migrate (sameAST, stringsIn, renderDeclaration)

-- Unlike the initial pretty-printer migration, this post-cutover operation
-- preserves every byte outside the exact pragma and legacy instance spans.
main = do
  args <- getArgs
  case args of
    [manifest,report] -> do
      jobs <- lines <$> readFile manifest
      rows <- forM jobs $ \job -> case tabs job of
        [source,target,name] -> do
          input <- readFile source
          ast@(Module _ _ _ ds) <- either die pure (parseModule source input)
          (tokens,_) <- either die pure (scan source input)
          expected <- either die pure (standardHierarchy (map spelling tokens) ast)
          changes <- forM [d | d@(Instance _ _ _ "Monad" _ ms) <- ds, any isBind ms] $ \d@(Instance t _ _ _ _ _) -> do
            replacements <- either die pure (standardInstance (map spelling tokens) d)
            let start=offset input (line t,column t)
                following=dropWhile (\x -> (line x,column x)<(line t,column t)) tokens
                brace=dropWhile ((/="{").spelling) following
            close <- either die pure (closing 0 brace)
            let end=offset input (endLine close,endColumn close)
                body=intercalate ";\n  " (map (indentTail.renderDeclaration) replacements)
            pure (start,end,body)
          let output=removeExtension (foldr replace input (sortOn (\(a,_,_)->a) changes))
          actual <- either die pure (parseModule target output)
          unless (sameAST expected actual) (die ("adjustment AST mismatch: "++source))
          unless (sort (stringsIn ast)==sort (stringsIn actual)) (die ("adjustment string spelling/multiplicity changed: "++source))
          createDirectoryIfMissing True (takeDirectory target)
          writeFile target output
          pure (intercalate "\t" [name,show (length changes),show (length (stringsIn ast))])
        _ -> die "manifest expects source<TAB>target<TAB>module"
      writeFile report (unlines rows)
      putStrLn ("Adjusted and reparsed "++show (length rows)++" modules; exact expression-string multiset retained.")
    _ -> die "usage: adjust-shared SOURCE_TARGET_MODULE_TSV REPORT_TSV"
isBind (Equation _ "bind" _ _ _) = True
isBind _ = False
closing _ [] = Left "unclosed instance braces"
closing depth (t:ts) = case spelling t of
  "{" -> closing (depth+1) ts
  "}" | depth==1 -> Right t
      | otherwise -> closing (depth-1) ts
  _ -> closing depth ts
replace (start,end,body) source = take start source++body++drop end source
indentTail = intercalate "\n  " . lines
removeExtension = go 0 where
  go _ []=[]
  go n source | n>=4 = source
  go n source | ", RebindableSyntax" `isPrefixOf` source = drop (length ", RebindableSyntax") source
  go n (ch:rest) = ch:go (if ch=='\n' then n+1 else n) rest
offset source target = go 0 (1,1) source where
  go n position rest | position==target = n
  go n (l,c) (ch:rest) = go (n+1) (case ch of {'\n'->(l+1,1);'\t'->(l,c+8-(c-1) `mod` 8);_->(l,c+1)}) rest
  go _ _ []=error "source position past EOF"
tabs s=case break (=='\t') s of { (x,[]) -> [x]; (x,_:rest) -> x:tabs rest }
