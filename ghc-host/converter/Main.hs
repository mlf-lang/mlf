module Main where

import System.Environment (getArgs)
import System.Exit (die)
import MLF.Host.Parser
import MLF.Host.Emit
import Control.Monad (forM, forM_)

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["--batch",manifest] -> do
      entries <- lines <$> readFile manifest
      jobs <- forM entries $ \entry -> case splitTabs entry of
        [source,target,name] -> do
          input <- readFile source
          ast <- either die pure (parseModule source input)
          pure (source,target,name,ast)
        _ -> die "batch manifest expects SOURCE<TAB>OUTPUT<TAB>MODULE per line"
      let modules=[ast | (_,_,_,ast) <- jobs]
      forM_ jobs $ \(source,target,name,ast) -> either die (writeFile target) (emitModule modules source (Just name) ast)
    [source,target] -> convert source target Nothing
    [source,target,name] -> convert source target (Just name)
    _ -> die "usage: mlf-to-haskell INPUT OUTPUT [MODULE]"
  where convert source target name = do
          input <- readFile source
          either die (writeFile target) (parseModule source input >>= emitModule [] source name)
        splitTabs s = case break (=='\t') s of
          (x,[]) -> [x]
          (x,_:rest) -> x:splitTabs rest
