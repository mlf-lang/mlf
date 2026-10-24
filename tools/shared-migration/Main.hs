module Main where
import Control.Monad (forM,forM_,unless)
import qualified Data.Map.Strict as M
import Data.List (intercalate,sort)
import Data.Graph (SCC(..), stronglyConnComp)
import System.Environment (getArgs)
import System.Exit (die)
import System.Directory (createDirectoryIfMissing)
import System.FilePath (takeDirectory)
import MLF.Host.Parser
import MLF.Host.Lexer
import MLF.Host.Syntax
import Migrate

main = do
  args <- getArgs
  case args of
    [manifest,primitiveFile,reportDir] -> run manifest primitiveFile reportDir
    _ -> die "usage: migrate-shared SOURCE_TARGET_MODULE_TSV PRIMITIVE_NAMES REPORT_DIRECTORY"
run manifest primitiveFile reportDir = do
  jobs <- lines <$> readFile manifest
  primitives <- lines <$> readFile primitiveFile
  parsed <- forM jobs $ \job -> case tabs job of
    [source,target,name] -> do
      input <- readFile source
      ast <- either die pure (parseModule source input)
      (tokens,_) <- either die pure (scan source input)
      pure (source,target,name,input,tokens,ast)
    _ -> die "manifest expects source<TAB>target<TAB>module"
  let modules=[Module name ex im ds | (_,_,name,_,_,Module _ ex im ds)<-parsed]
      names=[name | (_,_,name,_,_,_)<-parsed]
      graph=[(name,name,[n | Import _ n _ _ <- im,n `notElem` ["Prelude","MLF.Primitive"]]) | (_,_,name,_,_,Module _ _ im _)<-parsed]
  forM_ graph $ \(name,_,dependencies) -> unless (all (`elem` names) dependencies) (die ("inventory is not closed: "++name++" imports "++show (filter (`notElem` names) dependencies)))
  forM_ (stronglyConnComp graph) $ \component -> case component of
    AcyclicSCC _ -> pure ()
    CyclicSCC ns -> die ("cyclic shared implementation import graph: "++show ns)
  createDirectoryIfMissing True reportDir
  summaries <- forM parsed $ \(source,target,name,input,tokens,ast) -> do
    (output,stats,newAST) <- either (die.((source++": ")++)) pure (migrateModule modules primitives tokens input source name ast)
    reparsed <- either (die . (("roundtrip "++target++": ")++)) pure (parseModule target output)
    unless (sameAST newAST reparsed) $ do
      writeFile "/tmp/mlf-migration-expected-ast" (astShape newAST)
      writeFile "/tmp/mlf-migration-actual-ast" (astShape reparsed)
      die ("AST printer roundtrip changed structure: "++target)
    unless (null (stringPatterns reparsed)) (die ("string pattern remains: "++target))
    let oldStrings=counts (stringsIn ast)
        newStrings=counts (stringsIn reparsed)
    unless (all (\(s,n) -> M.findWithDefault 0 s newStrings >= n) (M.toList oldStrings)) (die ("expression string literal lost or changed: "++source))
    let allOld=counts (stringsIn ast++stringPatterns ast)
    unless (all (`M.member` allOld) (M.keys newStrings)) (die ("new or changed string literal: "++target))
    createDirectoryIfMissing True (takeDirectory target)
    writeFile target output
    writeFile (reportDir++"/"++name++".scope.tsv") (report stats++"\n")
    writeFile (reportDir++"/"++name++".literals.tsv") (concat [show n++"\t"++show (M.findWithDefault 0 s newStrings)++"\t"++s++"\n" | (s,n)<-M.toList oldStrings])
    pure (intercalate "\t" [source,target,name,"string_patterns="++show (length (stringPatterns ast)),"expression_strings="++show (length (stringsIn ast)),"annotation_tokens="++show (length (filter ((==":").spelling) tokens)),"legacy_boolean_tokens="++show (length (filter ((`elem` ["true","false"]).spelling) tokens)),reportTSV stats])
  writeFile (reportDir++"/counts.tsv") (unlines summaries)
  putStrLn ("Migrated and reparsed "++show (length parsed)++" modules; expression string spellings retained byte-for-byte.")
counts xs=M.fromListWith (+) [(x,1::Int)|x<-xs]
tabs s=case break (=='\t') s of { (x,[]) -> [x]; (x,_:rest) -> x:tabs rest }
