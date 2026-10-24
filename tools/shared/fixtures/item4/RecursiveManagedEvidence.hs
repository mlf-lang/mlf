{-# LANGUAGE OverloadedStrings #-}
-- Focused merge controls for recursive inference, managed scope and source ABIs.
-- This is a host fixture, not a full native/self-hosting qualification receipt.
module Main where

import Prelude
import Control.Monad (foldM, forM_, unless)
import Data.List (isInfixOf)
import System.Environment (getArgs)
import System.IO (BufferMode(LineBuffering), hSetBuffering, stdout)
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Compiler as Compiler
import qualified Bootstrap.CrateQuery as Query
import qualified Bootstrap.IntSet as IntSet
import qualified Bootstrap.Map as Map
import qualified Bootstrap.Runtime as Runtime
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.Set as Set
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Parser as Parser
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Tests.IndependentCheck as Independent
import qualified Tests.IndependentType as IndependentType
import qualified MLF.Host.Base as Host
import qualified MLF.Primitive as Primitive

expect label result = case result of
  T.Left message -> error (label ++ ": " ++ Host.unpack message)
  T.Right value -> pure value

assert label condition = unless condition (error ("FAIL " ++ label))
pass label = putStrLn ("PASS " ++ label)

-- Check the original and serialized target with both the production checker
-- and the retained independent checker, not only the inferred source scheme.
checkedTarget label expected term = do
  actual <- expect (label ++ " production target") (Check.checkClosed term)
  independent <- expect (label ++ " independent target") (Independent.checkClosed term)
  assert (label ++ " target types")
    (IndependentType.alphaEq actual expected && IndependentType.alphaEq independent expected)
  restored <- expect (label ++ " target parse")
    (Parser.parseTerm "RecursiveManagedEvidence.xmlf" (Pretty.prettyTerm term))
  restoredType <- expect (label ++ " production roundtrip") (Check.checkClosed restored)
  independentType <- expect (label ++ " independent roundtrip") (Independent.checkClosed restored)
  assert (label ++ " roundtrip types")
    (IndependentType.alphaEq restoredType expected && IndependentType.alphaEq independentType expected)
  assert (label ++ " roundtrip erasure") (X.equalErased (X.erase term) (X.erase restored))

header = "-- mlf:syntax shared-haskell-v1\n\
  \{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n\
  \module RecursiveManagedEvidence where\nimport MLF.Primitive\n"

evaluate term = do
  (environment, _) <- expect "runtime preparation" (Runtime.prepare False term)
  expect "runtime evaluation"
    (Runtime.evaluate environment (Runtime.REnv Map.empty) (X.erase term))

stackCase label source present absent = do
  putStrLn ("BEGIN " ++ label)
  compiled <- case Compiler.compile "RecursiveManagedEvidence.hs" (Host.literal (header ++ source)) of
    T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
    T.Right value -> pure value
  putStrLn ("COMPILED " ++ label)
  let term = Compiler.compiledTerm compiled
  checkedTarget label (T.XCon "String" []) term
  putStrLn ("CHECKED " ++ label)
  result <- evaluate term
  case result of
    Runtime.RString value -> do
      let text = Host.unpack value
      assert (label ++ " required frames: " ++ text) (all (`isInfixOf` text) present)
      assert (label ++ " excluded frames: " ++ text) (all (not . (`isInfixOf` text)) absent)
    _ -> error (label ++ ": expected opaque stack text")
  pass label

ordinaryClass = "class Tag a where { tag :: a -> Int }\n\
  \instance Tag Int where { tag x = x }\n"

signedProgram predicates = ordinaryClass ++
  "signed :: forall a. (" ++ predicates ++ ") => Int -> a -> CallStack\n" ++
  "signed n x = if eqInt n 0 then (if eqInt (tag x) 42 then callStack else callStack) else signed (subInt n 1) x\n" ++
  "caller :: HasCallStack => Int -> CallStack\n" ++
  "caller n = signed n (42 :: Int)\n" ++
  "main = textFromChars (prettyCallStack (caller 2))\n"

mixedProgram predicates = ordinaryClass ++
  "signed :: forall a. (" ++ predicates ++ ") => Int -> a -> CallStack\n" ++
  "signed n x = if eqInt n 0 then callStack else unsigned (subInt n 1) x\n" ++
  "unsigned n x = if eqInt (tag x) 42 then signed n x else signed n x\n" ++
  "caller :: HasCallStack => Int -> CallStack\n" ++
  "caller n = signed n (42 :: Int)\n" ++
  "main = textFromChars (prettyCallStack (caller 2))\n"

managedChecks = do
  forM_ [("managed-first", "HasCallStack, Tag a"),
         ("managed-last", "Tag a, HasCallStack")] $ \(order, predicates) -> do
    stackCase ("signed self recursion " ++ order) (signedProgram predicates)
      ["signed,", "caller,"] ["callStack,"]
    stackCase ("mixed signed/unsigned recursion " ++ order) (mixedProgram predicates)
      ["signed,"] ["caller,", "unsigned,", "callStack,"]

int = T.SCon "Int" []
classTag = T.SClassDecl "Tag" [("a", T.Star)] []
  [("tag", T.SArrow (T.STVar "a") int)]
instanceTag = T.SInstanceDecl [] [] "Tag" [int]
  [("tag", T.SLam "x" T.Nothing (T.SVar "x"))]
variable = T.SVar
number = T.SIntLit
apply name arguments = foldl T.SApp (variable name) arguments
lambda names body = foldr (\name -> T.SLam name T.Nothing) body names
subtractOne = T.SApp (T.SApp (T.SPrimitive T.PSubInt) (variable "n")) (number 1)
whenZero yes no = T.SApp
  (T.SApp (T.SApp (T.SPrimitive T.PIfThenElse)
    (T.SApp (T.SApp (T.SPrimitive T.PEqInt) (variable "n")) (number 0))) yes) no
member name body = (name, T.Nothing, body)

-- An explicit qualified SAnn is an expression interface, not permission to
-- promote it to declaration-checking provenance. Both still export their
-- source-issued evidence order, including managed arguments between classes.
explicitCases =
  [ ("coercionOrdinary", T.SAnn, ["Tag"])
  , ("signatureOrdinary", T.SSignature, ["Tag"])
  , ("coercionFirst", T.SAnn, ["MLFHasCallStack", "Tag"])
  , ("signatureFirst", T.SSignature, ["MLFHasCallStack", "Tag"])
  , ("coercionLast", T.SAnn, ["Tag", "MLFHasCallStack"])
  , ("signatureLast", T.SSignature, ["Tag", "MLFHasCallStack"])
  ];

explicitAnnotation classes = T.SAnnotation []
  (T.SForall T.Flexible "a" T.SBottom
    (T.SQualified
      [T.SPredicate name (if name == "MLFHasCallStack" then [] else [T.STVar "a"])
      | name <- classes]
      (T.SArrow (T.STVar "a") int)))

explicitBody = lambda ["x"] (apply "tag" [variable "x"])

explicitMembers = concat
  [[ member name (wrapper explicitBody (explicitAnnotation classes))
   , (Primitive.concatString name "Use", T.Just (T.SAnnotation [] int),
       apply name [number 42])
   ]
  | (name, wrapper, classes) <- explicitCases]

explicitStandaloneChecks = forM_ explicitCases $ \(name, wrapper, classes) -> do
  let label = "standalone explicit qualified interface " ++ Host.unpack name
      expression = T.SLet name (wrapper explicitBody (explicitAnnotation classes))
        (apply name [number 42])
  compiled <- case Compiler.compileProgramWithPrelude T.NoImplicitPrelude
      (T.SClassProgram [] [classTag] [instanceTag] expression) of
    T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
    T.Right value -> pure value
  putStrLn ("COMPILED " ++ label)
  checkedTarget label (T.XCon "Int" []) (Compiler.compiledTerm compiled)
  putStrLn ("CHECKED " ++ label)
  actual <- evaluate (Compiler.compiledTerm compiled)
  assert label (case actual of Runtime.RInteger 42 -> True; _ -> False)
  pass label

located name = T.SCallSite name
  (T.SourceSpan "main" "RecursiveManagedEvidence" "RecursiveManagedEvidence.hs" 5 1 5 12)
  (variable name)
locatedApply name arguments = foldl T.SApp (located name) arguments
stackType = T.SCon "MLFCallStack" []
managedQualifier = T.SPredicate "MLFHasCallStack" []

rawManagedChecks = forM_ [("first", [managedQualifier, T.SPredicate "Tag" [T.STVar "a"]]),
                          ("last", [T.SPredicate "Tag" [T.STVar "a"], managedQualifier])] $
  \(order, predicates) -> forM_ [False, True] $ \mixed -> do
    let label = "raw managed recursion " ++ order ++ if mixed then " mixed" else " signed"
        signature = T.SAnnotation [] (T.SForall T.Flexible "a" T.SBottom
          (T.SQualified predicates (T.SArrow int (T.SArrow (T.STVar "a") stackType))))
        stack = variable "$MLF.Stack.callStack"
        inspectTag = T.SApp (T.SApp (T.SApp (T.SPrimitive T.PIfThenElse)
          (T.SApp (T.SApp (T.SPrimitive T.PEqInt) (apply "tag" [variable "x"])) (number 42))) stack) stack
        signedBody = lambda ["n", "x"] (whenZero (if mixed then stack else inspectTag)
          (locatedApply (if mixed then "unsigned" else "signed") [subtractOne, variable "x"]))
        unsignedBody = lambda ["n", "x"]
          (T.SApp (T.SApp (T.SApp (T.SPrimitive T.PIfThenElse)
            (T.SApp (T.SApp (T.SPrimitive T.PEqInt) (apply "tag" [variable "x"])) (number 42)))
            (locatedApply "signed" [variable "n", variable "x"]))
            (locatedApply "signed" [variable "n", variable "x"]))
        definitions = [("signed", T.CheckRecursive signature, signedBody)] ++
          if mixed then [("unsigned", T.InferRecursive, unsignedBody)] else []
        caller = T.SSignature (lambda ["n"] (locatedApply "signed" [variable "n", number 42]))
          (T.SAnnotation [] (T.SQualified [managedQualifier] (T.SArrow int stackType)))
        result = T.SApp (T.SPrimitive T.PTextFromChars)
          (T.SApp (T.SPrimitive T.PPrettyCallStack) (locatedApply "caller" [number 2]))
        program = T.SClassProgram [] [classTag] [instanceTag]
          (T.SLetRec definitions (T.SLet "caller" caller result))
    putStrLn ("BEGIN " ++ label)
    compiled <- case Compiler.compileProgramWithPrelude T.NoImplicitPrelude program of
      T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
      T.Right value -> pure value
    putStrLn ("COMPILED " ++ label)
    checkedTarget label (T.XCon "String" []) (Compiler.compiledTerm compiled)
    putStrLn ("CHECKED " ++ label)
    actual <- evaluate (Compiler.compiledTerm compiled)
    case actual of
      Runtime.RString value -> do
        let text = Host.unpack value
        assert (label ++ " signed frame: " ++ text) ("signed," `isInfixOf` text)
        assert (label ++ " managed scope: " ++ text)
          (("caller," `isInfixOf` text) == not mixed)
        assert (label ++ " unsigned does not become managed: " ++ text)
          (not ("unsigned," `isInfixOf` text))
      _ -> error (label ++ ": expected stack text")
    pass label

-- User-written nested method qualifications are outside shared-haskell-v1.
-- Exercise the supported managed-method representation directly, as the
-- existing CallStackEvidence managedTargetCompilation fixture does.
copiedScopeChecks = forM_ [("direct", Nothing), ("unsigned", Just T.InferRecursive),
                           ("signed", Just (T.CheckRecursive
                             (T.SAnnotation [] (T.SArrow int stackType))))] $ \(kind, mode) -> do
  let label = "managed method with " ++ kind ++ " helper scope"
      stack = variable "$MLF.Stack.callStack"
      helper = lambda ["n"] (whenZero stack (locatedApply "helper" [subtractOne]))
      method = case mode of
        Nothing -> lambda ["n"] stack
        Just recursiveMode -> T.SLetRec
          [("helper", recursiveMode, T.SSourceDefinition helper)] (variable "helper")
      declaration = T.SClassDecl "Observe" [("a", T.Star)] []
        [("observe", T.SQualified [managedQualifier] (T.SArrow (T.STVar "a") stackType))]
      instanceDecl = T.SInstanceDecl [] [] "Observe" [int] [("observe", method)]
      caller = T.SSignature (lambda ["n"] (locatedApply "observe" [variable "n"]))
        (T.SAnnotation [] (T.SQualified [managedQualifier] (T.SArrow int stackType)))
      result = T.SApp (T.SPrimitive T.PTextFromChars)
        (T.SApp (T.SPrimitive T.PPrettyCallStack) (locatedApply "caller" [number 2]))
      program = T.SClassProgram [] [declaration] [instanceDecl] (T.SLet "caller" caller result)
  putStrLn ("BEGIN " ++ label)
  compiled <- case Compiler.compileProgramWithPrelude T.NoImplicitPrelude program of
    T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
    T.Right value -> pure value
  putStrLn ("COMPILED " ++ label)
  checkedTarget label (T.XCon "String" []) (Compiler.compiledTerm compiled)
  putStrLn ("CHECKED " ++ label)
  actual <- evaluate (Compiler.compiledTerm compiled)
  case actual of
    Runtime.RString value -> do
      let text = Host.unpack value
      case mode of
        Nothing -> assert (label ++ ": " ++ text)
          ("observe," `isInfixOf` text && "caller," `isInfixOf` text)
        Just _ -> assert (label ++ " copied scope is empty: " ++ text) (null text)
    _ -> error (label ++ ": expected stack text")
  pass label

consumedCases =
  [ ("consumedFirst", ["MLFHasCallStack", "Tag"])
  , ("consumedLast", ["Tag", "MLFHasCallStack"])
  ]

consumedBody classes = T.SCallSite "an expression type signature"
  (T.SourceSpan "main" "RecursiveManagedEvidence" "RecursiveManagedEvidence.hs" 9 1 9 40)
  (T.SAnn explicitBody (explicitAnnotation classes))

consumedMembers = concat
  [[ member name (consumedBody classes)
   , (Primitive.concatString name "Use", T.Just (T.SAnnotation [] int),
       apply name [number 42])
   ]
  | (name, classes) <- consumedCases]

consumedStandaloneChecks = forM_ consumedCases $ \(name, classes) -> do
  let located = consumedBody classes
      copied = T.SSourceDefinition located
  assert "located managed expression consumes its explicit interface"
    (null (Classes.sourceDeclaredClasses T.Nothing located))
  assert "copied located expression also consumes its explicit interface"
    (null (Classes.sourceDeclaredClasses T.Nothing copied))
  forM_ [("located", located), ("copied", copied)] $ \(kind, rhs) -> do
    let label = "standalone " ++ kind ++ " managed expression " ++ Host.unpack name
    compiled <- case Compiler.compileProgramWithPrelude T.NoImplicitPrelude
        (T.SClassProgram [] [classTag] [instanceTag]
          (T.SLet name rhs (apply name [number 42]))) of
      T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
      T.Right value -> pure value
    putStrLn ("COMPILED " ++ label)
    checkedTarget label (T.XCon "Int" []) (Compiler.compiledTerm compiled)
    putStrLn ("CHECKED " ++ label)
    actual <- evaluate (Compiler.compiledTerm compiled)
    assert label (case actual of Runtime.RInteger 42 -> True; _ -> False)
    pass label
  copiedPlan <- expect "copied managed-expression source routing"
    (Source.prepareSourcePlan Map.empty [] [classTag] [("tagInt", instanceTag)]
      (Map.fromList Primitive.compareString [(name, IntSet.fromList [0])])
      [IntSet.fromList [0]] [member name copied])
  assert "copied managed expression retains whole-path fallback"
    (case copiedPlan of T.Nothing -> True; _ -> False)
parsedConsumedChecks = forM_ consumedCases $ \(name, classes) -> do
  let predicates = if head classes == "MLFHasCallStack"
        then "HasCallStack, Tag a" else "Tag a, HasCallStack"
      label = "parsed managed expression " ++ Host.unpack name
      source = ordinaryClass ++
        "bound = ((\\x -> tag x) :: forall a. (" ++ predicates ++ ") => a -> Int)\n" ++
        "main = bound (42 :: Int)\n"
  compiled <- case Compiler.compile "RecursiveManagedEvidence.hs" (Host.literal (header ++ source)) of
    T.Left err -> error (label ++ ": " ++ Host.unpack (Compiler.prettyError err))
    T.Right value -> pure value
  putStrLn ("COMPILED " ++ label)
  checkedTarget label (T.XCon "Int" []) (Compiler.compiledTerm compiled)
  putStrLn ("CHECKED " ++ label)
  actual <- evaluate (Compiler.compiledTerm compiled)
  assert label (case actual of Runtime.RInteger 42 -> True; _ -> False)
  pass label

sourceMembers =
  [ member "plain" (lambda ["n"] (whenZero (number 42) (apply "plain" [subtractOne])))
  , member "plainUse" (apply "plain" [number 3])
  , member "left" (lambda ["n"] (whenZero (number 42) (apply "right" [subtractOne])))
  , member "right" (lambda ["n"] (whenZero (number 42) (apply "left" [subtractOne])))
  , member "mutualUse" (apply "left" [number 3])
  , member "qualified" (lambda ["n", "x"]
      (whenZero (apply "tag" [variable "x"]) (apply "qualified" [subtractOne, variable "x"])))
  , member "qualifiedUse" (apply "qualified" [number 2, number 42])
  , member "qualifiedLeft" (lambda ["n", "x"]
      (whenZero (apply "qualifiedRight" [number 0, variable "x"])
        (apply "qualifiedRight" [subtractOne, variable "x"])))
  , member "qualifiedRight" (lambda ["n", "x"]
      (whenZero (apply "tag" [variable "x"])
        (apply "qualifiedLeft" [subtractOne, variable "x"])))
  , member "qualifiedMutualUse" (apply "qualifiedLeft" [number 2, number 42])
  , member "successor" (lambda ["x"] (apply "qualified" [number 1, variable "x"]))
  , member "successorUse" (apply "successor" [number 42])
  ] ++ explicitMembers ++ consumedMembers

lookupContract contracts name = case Map.lookup Primitive.compareString name contracts of
  T.Just contract -> contract
  T.Nothing -> error ("missing source contract: " ++ Host.unpack name)

stripData (T.XWithData _ body) = stripData body
stripData body = body
replaceTail (T.XLet name value body) result = T.XLet name value (replaceTail body result)
replaceTail (T.XLetRec definitions body) result = T.XLetRec definitions (replaceTail body result)
replaceTail (T.XConstructor "()" []) result = result
replaceTail _ _ = error "unexpected checked fragment binding spine"

findBinding wanted (T.XLet name _ body)
  | X.nameHint name == wanted = name
  | otherwise = findBinding wanted body
findBinding wanted (T.XLetRec definitions body) =
  case [name | (name, _, _) <- definitions, X.nameHint name == wanted] of
    [name] -> name
    [] -> findBinding wanted body
    _ -> error "duplicate checked recursive export"
findBinding _ _ = error "missing checked export"

lookupTerm terms name = case lookup name terms of
  Just term -> term
  Nothing -> error ("missing checked predecessor: " ++ Host.unpack name)

closeFragment datatypes terms parameters body =
  let identities = foldl
        (\seen (name, ty) -> Separate.typeIdentities ty
          (Set.insert Std.compareInt (X.nameId name) seen))
        (Separate.termIdentities body Set.empty) parameters
      first = 1 + maximum (0 : Set.toList identities)
      bind (serial, bindings) (name, _) =
        let (next, value) = Separate.freshObject serial
              (stripData (lookupTerm terms (X.nameHint name)))
        in (next, bindings ++ [(name, value)])
      (_, bindings) = foldl bind (first, []) parameters
  in T.XWithData datatypes (foldr (\(name, value) -> T.XLet name value) body bindings)

collect terms object = do
  let (datatypes, term) = case Separate.objectTerm object of
        T.XWithData ds body -> (ds, body)
        body -> ([], body)
      (parameters, core) = Separate.splitParameters term
  new <- mapM (\(name, ty) -> do
    let binder = findBinding name core
        closed = closeFragment datatypes terms parameters (replaceTail core (T.XVarTerm binder))
    checkedTarget ("linked source export " ++ Host.unpack name) ty closed
    pure (name, closed)) (Separate.unitBindings (Separate.objectInterface object))
  pure (terms ++ new)

contractSnapshot contracts =
  [(name, Pretty.prettyType (Source.contractType contract),
    Source.contractClasses contract, Source.contractProtected contract)
  | (name, contract) <- Map.toList contracts]

sourceChecks cache = do
  let scopes = Map.fromList Primitive.compareString
        [(name, IntSet.fromList [0]) | (name, _, _) <- sourceMembers]
  maybePlan <- expect "recursive source plan"
    (Source.prepareSourcePlan Map.empty [] [classTag] [("tagInt", instanceTag)]
      scopes [IntSet.fromList [0]] sourceMembers)
  rawPlan <- case maybePlan of
    T.Just plan -> pure plan
    T.Nothing -> error "ordinary recursive sources unexpectedly require whole-path fallback"
  -- The source scheduler must not silently reinstate old global lowering.
  let plan = case rawPlan of
        Source.SourcePlan a b c d e f g _ i j ->
          Source.SourcePlan a b c d e f g (error "legacy global lowering forced") i j
  (objects, cold, contracts) <- Query.compileSourceGroups "recursive-managed-evidence"
    (Host.literal cache) [] Map.empty plan >>= expect "cold recursive source groups"
  assert "cold source inference covers every group"
    (Query.inferredCount cold == fromIntegral (length (Source.planGroups plan)) && Query.reusedCount cold == 0)
  forM_ ["plain", "left", "right", "plainUse", "mutualUse"] $ \name ->
    assert ("ordinary source ABI: " ++ Host.unpack name)
      (null (Source.contractClasses (lookupContract contracts name)))
  forM_ ["qualified", "qualifiedLeft", "qualifiedRight", "successor"] $ \name -> do
    let contract = lookupContract contracts name
    assert ("qualified source ABI: " ++ Host.unpack name)
      (Source.contractClasses contract == ["Tag"])
    assert ("ordinary qualified source is not managed: " ++ Host.unpack name)
      (not (Source.contractProtected contract))
  forM_ ["qualifiedUse", "qualifiedMutualUse", "successorUse"] $ \name ->
    assert ("ground qualified successor ABI: " ++ Host.unpack name)
      (null (Source.contractClasses (lookupContract contracts name)))
  forM_ [["plain"], ["left", "right"], ["qualified"], ["qualifiedLeft", "qualifiedRight"]] $ \names -> do
    let predecessors = Map.filterWithKey (\name _ -> name `notElem` names) contracts
    prepared <- expect "recursive source preparation" (Source.prepareGroup plan predecessors names)
    assert "recursive groups cannot claim root-compaction authority"
      (case Source.groupAuthority prepared of T.Nothing -> True; _ -> False)
  forM_ explicitCases $ \(name, wrapper, classes) -> do
    let contract = lookupContract contracts name
        original = wrapper explicitBody (explicitAnnotation classes)
        predecessors = Map.filterWithKey (\other _ -> other /= name) contracts
    assert ("explicit qualified evidence order: " ++ Host.unpack name)
      (Source.contractClasses contract == classes)
    assert ("explicit qualified managed protection: " ++ Host.unpack name)
      (Source.contractProtected contract == ("MLFHasCallStack" `elem` classes))
    assert "explicit qualified wrapper is not root-compaction eligible"
      (not (Source.eligibleSource [member name original]))
    prepared <- expect "explicit qualified source preparation"
      (Source.prepareGroup plan predecessors [name])
    assert "explicit qualified source has unchanged-boundary authority"
      (case Source.groupAuthority prepared of T.Nothing -> True; _ -> False)
  forM_ consumedCases $ \(name, _) -> do
    let contract = lookupContract contracts name
    assert ("consumed expression retains only ordinary residual ABI: " ++ Host.unpack name)
      (Source.contractClasses contract == ["Tag"])
    assert ("consumed managed expression preserves protection: " ++ Host.unpack name)
      (Source.contractProtected contract)
  terms <- foldM collect [] objects
  forM_ ["plainUse", "mutualUse", "qualifiedUse", "qualifiedMutualUse", "successorUse"] $ \name -> do
    value <- evaluate (lookupTerm terms name)
    assert ("recursive source runtime: " ++ Host.unpack name)
      (case value of Runtime.RInteger 42 -> True; _ -> False)
  forM_ explicitCases $ \(name, _, _) -> do
    let use = Primitive.concatString name "Use"
    assert ("explicit qualified successor has closed source ABI: " ++ Host.unpack use)
      (null (Source.contractClasses (lookupContract contracts use)))
    value <- evaluate (lookupTerm terms use)
    assert ("explicit qualified successor runtime: " ++ Host.unpack use)
      (case value of Runtime.RInteger 42 -> True; _ -> False)
  forM_ consumedCases $ \(name, _) -> do
    let use = Primitive.concatString name "Use"
    assert ("consumed expression successor has closed source ABI: " ++ Host.unpack use)
      (null (Source.contractClasses (lookupContract contracts use)))
    assert ("consumed expression successor retains protection: " ++ Host.unpack use)
      (Source.contractProtected (lookupContract contracts use))
    value <- evaluate (lookupTerm terms use)
    assert ("consumed expression successor runtime: " ++ Host.unpack use)
      (case value of Runtime.RInteger 42 -> True; _ -> False)
  (warmObjects, warm, warmContracts) <- Query.compileSourceGroups "recursive-managed-evidence"
    (Host.literal cache) [] Map.empty plan >>= expect "warm recursive source groups"
  assert "warm source groups reuse every raw object"
    (Query.inferredCount warm == 0 && Query.reusedCount warm == fromIntegral (length objects))
  assert "cold/warm object identity"
    (map Separate.encodeObject objects == map Separate.encodeObject warmObjects)
  assert "cold/warm ordered source ABI and protection identity"
    (contractSnapshot contracts == contractSnapshot warmContracts)
  pass "source recursive singleton/mutual and qualified successor contracts"

main = do
  hSetBuffering stdout LineBuffering
  arguments <- getArgs
  case arguments of
    ["--raw"] -> rawManagedChecks >> copiedScopeChecks >> explicitStandaloneChecks >> consumedStandaloneChecks
    ["--parsed"] -> managedChecks >> parsedConsumedChecks
    ["--managed"] -> rawManagedChecks >> copiedScopeChecks >> explicitStandaloneChecks >> consumedStandaloneChecks >> managedChecks >> parsedConsumedChecks
    ["--source", cache] -> sourceChecks cache
    [cache] -> rawManagedChecks >> copiedScopeChecks >> explicitStandaloneChecks >> consumedStandaloneChecks >> managedChecks >> parsedConsumedChecks >> sourceChecks cache
    _ -> error "usage: RecursiveManagedEvidence [--raw | --parsed | --managed | --source CACHE | CACHE]"
