module StateTypes (stateTypeTests, checkedStateSource) where

import Control.Monad (forM_, unless)
import qualified MLF.Compiler as C
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Parser as Parser
import qualified MLF.X.Pretty as Pretty
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import StateCases

checkedStateSource :: String -> IO C.Compilation
checkedStateSource source = do
  result <- either (fail . show) pure (C.compile "<ST fixture>" source)
  target <- either fail pure (Parser.parseTerm "<ST target>" (Pretty.prettyTerm (C.compiledTerm result)))
  ty <- either fail pure (Check.checkClosed target)
  unless (T.alphaEq ty (C.inferredType result)) (fail "ST target roundtrip changed type")
  unless (X.erase target == X.erase (C.compiledTerm result)) (fail "ST target roundtrip changed erasure")
  pure result

stateTypeTests :: [(String,IO ())]
stateTypeTests =
  [("ST source type: " ++ label, if accepted then do
      result <- checkedStateSource source
      forM_ expectedType $ \expected ->
        unless (C.sourceType result == expected) (fail ("expected " ++ expected ++ ", got " ++ C.sourceType result))
    else case C.compile "<ST rejection>" source of
      Left err -> unless (C.phase err == C.Inference) (fail ("expected a type inference rejection: " ++ show err))
      Right result -> fail ("accepted escaping or ill-typed state: " ++ C.sourceType result))
    | (label,accepted,source,expectedType) <- stateTypeCases] ++
  [("ST target type: " ++ label, do
      -- Parse failure never counts as a successful type rejection.
      term <- either fail pure (Parser.parseTerm "<ST direct target>" source)
      case (accepted,Check.checkClosed term) of
        (True,Right _) -> pure ()
        (False,Left _) -> pure ()
        (True,Left err) -> fail err
        (False,Right ty) -> fail ("accepted invalid target: " ++ Pretty.prettyType ty))
    | (label,accepted,source) <- stateTargetCases] ++
  [("ST primitive ABI is appended and action construction stays lazy", do
      let rows = [(P.GetExecutablePath,64,"getExecutablePath",0,False),
                  (P.GetContents,65,"getContents",0,False),
                  (P.STReturn,66,"stReturn",1,False),(P.STBind,67,"stBind",2,False),
                  (P.RunST,68,"runST",1,True),(P.NewSTArray,69,"newSTArray",2,False),
                  (P.ReadSTArray,70,"readSTArray",2,False),(P.WriteSTArray,71,"writeSTArray",3,False),
                  (P.LengthSTArray,72,"lengthSTArray",1,False)]
      forM_ rows $ \(primitive,code,name,arity,strict) ->
        unless (fromEnum primitive == code && P.primitiveName primitive == name &&
                P.primitiveArity primitive == arity && P.primitiveStrict primitive == strict)
          (fail ("incorrect state primitive metadata: " ++ show primitive)))
  , ("ST primitives work with implicit prelude disabled", do
      result <- either (fail . show) pure (C.compileWithPrelude C.NoImplicitPrelude "<no prelude ST>"
        "runST (stBind (newSTArray 1 7) (\\a -> readSTArray a 0))")
      unless (T.alphaEq (C.inferredType result) (T.Con "Int" [])) (fail (C.sourceType result)))
  ]
