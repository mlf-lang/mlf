-- | Checked xMLF to native LLVM functions. Type computations are erased only
-- after the independent target checker accepts the complete term.
module MLF.LLVM (emitLLVM, emitLLVMIO, emitLLVMForGC, emitLLVMIOForGC) where

import Control.Monad (when)
import Data.Bifunctor (first)
import qualified Data.Map.Strict as Map
import qualified MLF.Data as D
import qualified MLF.LLVM.Codegen as Codegen
import qualified MLF.LLVM.Optimize as Optimize
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

-- | Emit a module with mlf_entry and main. Link with runtime/mlf_runtime.c
-- and GMP. IO entries execute their action; pure entries evaluate to weak
-- head normal form and discard the result without implicitly printing it.
emitLLVM :: X.Term -> Either String String
emitLLVM = emitEntry False False

emitLLVMIO :: X.Term -> Either String String
emitLLVMIO = emitEntry False True

-- | Emit the compact layout for the BDWGC runtime allocation profile.
emitLLVMForGC :: X.Term -> Either String String
emitLLVMForGC = emitEntry True False

emitLLVMIOForGC :: X.Term -> Either String String
emitLLVMIOForGC = emitEntry True True

emitEntry :: Bool -> Bool -> X.Term -> Either String String
emitEntry compact requireIO term = do
  ty <- first ("LLVM target verification failed: " ++) (Check.checkClosed term)
  let declarations = case term of X.WithData ds _ -> ds; _ -> []
      constructors = Map.fromList (("Unit",(0,0)) :
        [(D.constructorName c,(i,length (D.constructorFields c))) |
          (i,c) <- zip [1..] (concatMap D.datatypeConstructors declarations)])
      ioType (T.Forall _ _ body) = ioType body
      ioType (T.Con "IO" [_]) = True
      ioType _ = False
  when (requireIO && not (ioType ty)) (Left "program must have type IO a to run")
  let generate = if compact then Codegen.generateForGC else Codegen.generate
      abi = if compact then "mlf_require_compact_gc_abi" else "mlf_require_standard_abi"
  (entry,code) <- generate constructors (Optimize.optimize (X.erase term))
  pure $ unlines (["; Generated from independently checked xMLF.",
    "source_filename = \"emlf\"", ""] ++ code ++
    [ "declare void @" ++ abi ++ "()"
    , "define ptr @mlf_entry() {"
    , "  call void @" ++ abi ++ "()"
    , "  %root = call ptr " ++ entry ++ "(ptr null, ptr null)"
    , "  ret ptr %root", "}"
    , "define i32 @main(i32 %argc, ptr %argv) {"
    , "  call void @mlf_set_args(i32 %argc, ptr %argv)"
    , "  %root = call ptr @mlf_entry()"
    , "  %status = call i32 @mlf_run(ptr %root, i64 " ++ (if ioType ty then "1" else "0") ++ ")"
    , "  ret i32 %status", "}"
    ])
