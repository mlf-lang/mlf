{-# LANGUAGE OverloadedStrings #-}
-- Isolated opt-in harness. Never selected as the default compiler.
module Main where
import Prelude hiding (Either(..),Maybe(..))
import Bootstrap.Types
import qualified MLF.Primitive as P
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Compiler as Compiler
import qualified Bootstrap.CompilerCore as Core
import qualified Bootstrap.Standalone as New
import qualified Bootstrap.StandaloneReference as Old
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.InstalledPreludeWholeRoot as Installed
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.LLVM as LLVM
import System.Environment(getArgs)
import System.Directory(createDirectory,doesPathExist)
import System.FilePath((</>))
import Control.Exception(evaluate)
import qualified System.IO as IO
text=P.textFromChars
untext=P.textToChars
require value=case value of Left error->fail(untext error);Right answer->pure answer
compileRequire value=case value of Left error->fail(untext(Compiler.prettyError error));Right answer->pure answer
mode "implicit"=pure ImplicitPrelude
mode "no-prelude"=pure NoImplicitPrelude
mode _=fail "unknown Prelude mode"
parsed sourcePath bytes=do
 root<-require(Parser.parseModule(text sourcePath)bytes)
 if Compiler.standalone root then pure() else fail "whole-root prototype accepts only original unnamed standalone roots"
 program<-require(Parser.standaloneProgram root)
 pure(root,program)
sameNormalized a b=case(a,b)of
 (Left x,Left y)->P.eqString x y
 (Right Nothing,Right Nothing)->True
 (Right(Just(is,p,ns)),Right(Just(js,q,ms)))->
   map untext(S.toList is)==map untext(S.toList js) && Equality.eqSProgram p q &&
   [(untext x,untext y)|(x,y)<-M.toList ns]==[(untext x,untext y)|(x,y)<-M.toList ms]
 _->False
fresh out=do
 exists<-doesPathExist out
 if exists then fail "fresh output directory required" else createDirectory out
writeChecked out checked=do
 writeUtf8File(out</>"target-type.txt")(untext(Pretty.prettyType(Checked.typeOf checked))++"\n")
 writeUtf8File(out</>"checked.xmlf")(untext(Pretty.prettyTerm(Checked.term checked))++"\n")
writeUtf8File path contents=IO.withFile path IO.WriteMode (\handle->do
 IO.hSetEncoding handle IO.utf8
 IO.hPutStr handle contents)
main=do
 mapM_ (\handle->IO.hSetEncoding handle IO.utf8) [IO.stdin,IO.stdout,IO.stderr]
 args<-getArgs
 case args of
  ["install",out]->do
   fresh out
   (metadata,object)<-require Installed.snapshot
   writeUtf8File(out</>"unit.mlfci")(untext metadata)
   writeUtf8File(out</>"unit.mlfco")(untext object)
  ["factor",which,path]->do
   m<-mode which;bytes<-getContents;_<-evaluate(length bytes);(_,program)<-parsed path(text bytes)
   if and [sameNormalized(Old.normalizeWithScope whole m program)(New.normalizeWithScope whole m program)|whole<-[False,True]]
    then putStrLn "FACTOR-PROJECTION-EQUAL" else fail "normalize factoring changed source result"
  ["original-check",which,path,out]->do
   m<-mode which;bytes<-getContents;_<-evaluate(length bytes);(root,_)<-parsed path(text bytes)
   compiled<-compileRequire(Compiler.compileStandalone m root)
   fresh out;writeChecked out(Core.checkedTerm compiled)
  ["emit-installed-llvm",which,expected,path]->do
   m<-mode which;bytes<-getContents;_<-evaluate(length bytes)
   fields<-require(Separate.unpack(text bytes))
   case fields of
    [actual,metadata,object,source]->do
     -- Exact externally authenticated bytes, same restore and whole-root path.
     context<-require(Installed.restoreVerified(text expected)actual metadata object)
     (_,program)<-parsed path source
     outcome<-compileRequire(Installed.compileInstalledRoot context m program)
     if Installed.reused outcome then pure()
      else fail ("installed LLVM-only route refused OriginalFallback: "++untext(Installed.routeReason outcome))
     chunks<-require(LLVM.emitCheckedChunks False(Installed.checkedTerm outcome))
     -- LLVM only: no checked pretty-term/type/map/route proof serialization.
     mapM_ (putStr . untext) chunks
    _->fail "expected authenticated descriptor identity, metadata, object and exact source bytes"
  [operation,which,expected,path,out] | operation=="consume-check" || operation=="consume-llvm" ->do
   m<-mode which;bytes<-getContents;_<-evaluate(length bytes)
   fields<-require(Separate.unpack(text bytes))
   case fields of
    [actual,metadata,object,source]->do
     -- Supervisor has verified descriptor and these exact byte streams before
     -- launching this process; no filesystem artifact re-read occurs here.
     context<-require(Installed.restoreVerified(text expected)actual metadata object)
     (_,program)<-parsed path source
     outcome<-compileRequire(Installed.compileInstalledRoot context m program)
     fresh out
     writeUtf8File(out</>"route.txt")(if Installed.reused outcome then "InstalledRoot\n" else "OriginalFallback\n")
     writeUtf8File(out</>"route-reason.txt")(untext(Installed.routeReason outcome)++"\n")
     writeChecked out(Installed.checkedTerm outcome)
     writeUtf8File(out</>"root-target-type.txt")(untext(Pretty.prettyType(Core.inferredType(Installed.rawRootCompilation outcome)))++"\n")
     writeUtf8File(out</>"actual-lowering-map.pack")(untext(Separate.pack[Separate.pack[x,y]|(x,y)<-M.toList(Installed.rootDictionaryMap outcome)]))
     if operation=="consume-llvm" then do
      chunks<-require(LLVM.emitCheckedChunks False(Installed.checkedTerm outcome))
      writeUtf8File(out</>"program.ll")(concatMap untext chunks)
     else pure()
    _->fail "expected authenticated descriptor identity, metadata, object and exact source bytes"
  _->fail "isolated installed whole-root harness: install/factor/original-check/consume-check/consume-llvm"
