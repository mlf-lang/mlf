{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude hiding (Either(..), Maybe(..))
import Bootstrap.Types
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Compiler as Compiler
import qualified Bootstrap.CompilerCore as Core
import qualified MLF.BuiltinPreludeData as Builtin
import qualified Bootstrap.BuiltinPreludeContext as Context
import qualified MLF.PreparedCompiler as Prepared
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.LLVM as LLVM
import qualified Bootstrap.X.Type as Type
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Standalone as Standalone
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Map as M
import qualified MLF.Primitive as P
import System.Environment (getArgs)
import System.Exit (exitFailure)
import Data.Char (isDigit)
import qualified System.IO as IO

fatal message = IO.hPutStrLn IO.stderr (P.textToChars message) >> exitFailure
require value = case value of Left message -> fatal message; Right answer -> pure answer
compileRequire value = case value of Left error -> fatal (Compiler.prettyError error); Right answer -> pure answer
prepared = Context.checkCompilerPrelude Builtin.builtin

declarations value = case value of XWithData ds _ -> ds; _ -> []
ordinaryDictionaries program = do
  normalized <- require (Standalone.normalize ImplicitPrelude program)
  case normalized of
    Nothing -> pure M.empty
    Just (imports,source,names) -> do
      canonical <- require (Classes.canonicalSourceProgram imports source)
      (_,dictionaries) <- require (Classes.lowerClassesWithImports imports canonical)
      pure (M.map (Modules.displayNames names) dictionaries)
layoutName dictionaries name = case M.lookup P.compareString name dictionaries of
  Nothing -> name
  Just cls -> "DictionaryOf " P.++ cls
layoutType dictionaries ty = case ty of
  XArrow a b -> XArrow (layoutType dictionaries a) (layoutType dictionaries b)
  XCon name xs -> XCon (layoutName dictionaries name) (map (layoutType dictionaries) xs)
  XApply a b -> XApply (layoutType dictionaries a) (layoutType dictionaries b)
  XForall a bound body -> XForall a (layoutType dictionaries bound) (layoutType dictionaries body)
  _ -> ty
layoutField dictionaries value = case value of
  Parameter n -> Parameter n
  Function a b -> Function (layoutField dictionaries a) (layoutField dictionaries b)
  Applied n xs -> Applied (layoutName dictionaries n) (map (layoutField dictionaries) xs)
  Application a b -> Application (layoutField dictionaries a) (layoutField dictionaries b)
  Quantified n k body -> Quantified n k (layoutField dictionaries body)
layoutDeclaration dictionaries declaration =
  let original = Data.datatypeName declaration
      dictionary = case M.lookup P.compareString original dictionaries of Nothing -> False; Just _ -> True
      constructors = [ConstructorDecl (if dictionary then "DictionaryConstructor" else name)
        (map (layoutField dictionaries) fields) | ConstructorDecl name fields <- Data.datatypeConstructors declaration]
  in case declaration of
    DataDecl _ parameters _ -> DataDecl (layoutName dictionaries original) parameters constructors
    DataDeclK _ parameters _ -> DataDeclK (layoutName dictionaries original) parameters constructors
singleEqAmbiguity message =
  let value = P.textToChars message
      prefix = "Resolution: no instance or given constraint for MLF.Primitive.Eq a"
      suffix = "; ambiguous uses need a type annotation"
      middle = take (length value - length prefix - length suffix) (drop (length prefix) value)
  in take (length prefix) value == prefix && drop (length value - length suffix) value == suffix &&
       not (null middle) && all isDigit middle
compareRoot program ordinary candidate = case (ordinary,candidate) of
  (Left first,Left second) ->
    if P.eqString (Compiler.prettyError first) (Compiler.prettyError second)
    then putStrLn "PASS equal diagnostic"
    else if singleEqAmbiguity (Compiler.prettyError first) && singleEqAmbiguity (Compiler.prettyError second)
      then putStrLn "PASS alpha-equivalent ambiguity diagnostic"
      else fatal "prepared prototype changed diagnostic"
  (Right first,Right second) -> do
    beforeNames <- ordinaryDictionaries program
    let checked = Prepared.checkedTerm second
        afterNames = if Prepared.reused second then Prepared.dictionaryIdentities second else beforeNames
        beforeData = map (P.textToChars . Data.prettyDeclaration . layoutDeclaration beforeNames) (declarations (Core.compiledTerm first))
        afterData = map (P.textToChars . Data.prettyDeclaration . layoutDeclaration afterNames) (declarations (Checked.term checked))
    if Type.alphaEq (layoutType beforeNames (Core.inferredType first)) (layoutType afterNames (Checked.typeOf checked))
      then pure () else fatal "prepared prototype changed inferred target scheme"
    if beforeData == afterData then pure () else do
      mapM_ print (take 8 [(index,a,b) | (index,(a,b)) <- zip [0 :: Int ..] (zip beforeData afterData), a /= b])
      print (length beforeData,length afterData)
      fatal "prepared prototype changed datatype identity/order/layout"
    putStrLn (if Prepared.reused second then "PASS prepared whole-root scheme and layouts" else "PASS explicit original fallback")
  (Left first,Right _) -> fatal ("prepared prototype accepted rejected source: " P.++ Compiler.prettyError first)
  (Right _,Left second) -> fatal ("prepared prototype rejected accepted source: " P.++ Compiler.prettyError second)

main = do
  mapM_ (\handle -> IO.hSetEncoding handle IO.utf8) [IO.stdin,IO.stdout,IO.stderr]
  arguments <- getArgs
  case arguments of
    ["--prepared-context"] -> do
      context <- require prepared
      print (length (M.toList (Context.contracts context)))
    [operation, path] -> do
      bytes <- if path == "-" then getContents else readFile path
      source <- require (Parser.parseModule (P.textFromChars path) (P.textFromChars bytes))
      if Compiler.standalone source then pure () else fatal "prepared prototype accepts unnamed standalone roots only"
      program <- require (Parser.standaloneProgram source)
      if operation == "--ordinary-emit-llvm-gc" then do
        compiled <- compileRequire (Compiler.compileProgramWithPrelude ImplicitPrelude program)
        require (LLVM.emitCheckedChunks False (Core.checkedTerm compiled)) >>= mapM_ (putStr . P.textToChars)
      else do
       let outcome = Prepared.compileProgramWithPrelude ImplicitPrelude program
       if operation `elem` ["--compare", "--compare-direct"]
         then compareRoot program (Compiler.compileProgramWithPrelude ImplicitPrelude program) outcome
         else do
           result <- compileRequire outcome
           if Prepared.reused result then pure () else fatal ("prepared prototype fallback: " P.++ "ordinary source route")
           let checked = Prepared.checkedTerm result
           case operation of
             "--emit-llvm" -> require (LLVM.emitCheckedChunks False checked) >>= mapM_ (putStr . P.textToChars)
             "--emit-llvm-gc" -> require (LLVM.emitCheckedChunks False checked) >>= mapM_ (putStr . P.textToChars)
             "--direct-emit-llvm-gc" -> require (LLVM.emitCheckedChunks False checked) >>= mapM_ (putStr . P.textToChars)
             "--direct-check" -> putStrLn (P.textToChars (Pretty.prettyType (Checked.typeOf checked)))
             "--check" -> putStrLn (P.textToChars (Pretty.prettyType (Checked.typeOf checked)))
             "--checked" -> putStrLn (P.textToChars (Pretty.prettyTerm (Checked.term checked)))
             _ -> fatal "expected --emit-llvm[-gc], --check, --checked, --compare or --contracts"
    _ -> fatal "expected OPERATION SOURCE"
