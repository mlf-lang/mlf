{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Map as M
import qualified MLF.Host.Base as B
ls = foldr T.Cons T.Nil
rv = T.Right
act p args = rv (R.RAction p (ls args))
prim p args = R.primitiveResult D.emptyDataEnv p (ls args)
empty = prim T.PEmptyCallStack []
push f s = prim T.PPushCallStack [f,s]
pretty s = prim T.PPrettyCallStack [s]
str s = rv (R.RString (B.literal s))
num n = rv (R.RInteger n)
frame display el = rv (R.RConstructor "MLFStackFrame" (ls [display,str "pkg",str "Mod",str "file.hs",num 10,num 2,el,num 9]))
stack = push (frame (str "inner") (num 12)) (push (frame (str "outer") (num 12)) empty)
header = "CallStack (from HasCallStack):"
render c = case R.runtimeCharsText c of T.Left _ -> Nothing; T.Right t -> Just (B.unpack t)
takeChars 0 _ = Just ""
takeChars n (T.Right (R.RConstructor ":" (T.Cons (T.Right (R.RChar c)) (T.Cons rest T.Nil)))) = fmap ((toEnum (fromInteger c)):) (takeChars (n-1) rest)
takeChars _ (T.Right (R.RConstructor "[]" _)) = Just ""
takeChars _ _ = Nothing
assert label ok = if ok then putStrLn ("PASS "++label) else error ("FAIL "++label)
isLeft (T.Left _) = True
isLeft _ = False
msg s = rv (R.runtimeTextChars (B.literal s) 0)
err s = prim T.PUserError [msg s]
failWith s stk = act T.PIOErrorWithStack [err s,stk]
raise s = failWith s empty
ret = rv (R.RPrimitive T.PIOReturn T.Nil)
catch a h = act T.PCatchIOError [a,h]
k action = rv (R.RClosure (R.RLocal (T.XName 1 "saved") action (R.REnv M.empty)) (T.XName 2 "ignored") (T.XEVar (T.XName 1 "saved")))
run = R.runAction T.Nil D.emptyDataEnv
isErr (T.Right (T.Right (R.RIOError _))) = True
isErr _ = False
failureText (T.Left s) = Just (B.unpack s)
failureText _ = Nothing
main = do
  let unicode = rv (R.RConstructor "MLFStackFrame" (ls [str "函数λ😀",str "包",str "模",str "源.hs",num 7,num 8,num 9,num 10]))
  assert "unicode-frame-fields" (render (pretty (push unicode empty))==Just (header++"\n  函数λ😀, called at 源.hs:7:8 in 包:模"))
  let surrogate = rv (R.RConstructor ":" (ls [rv (R.RChar 55296),rv (R.RConstructor "[]" T.Nil)]))
  result <- run (act T.PIOErrorWithStack [prim T.PUserError [surrogate],empty])
  assert "empty-stack-uncaught-surrogate" (failureText result==Just "user error (\\55296)")
  assert "empty-pretty" (render (pretty empty)==Just "")
  assert "newest-first-pretty" (render (pretty stack)==Just (header++"\n  inner, called at file.hs:10:2 in pkg:Mod\n  outer, called at file.hs:10:2 in pkg:Mod"))
  let badFields=rv (R.RConstructor "MLFStackFrame" (ls (replicate 8 (T.Left "field bottom"))))
  let bad=pretty (push badFields empty)
  assert "header-before-fields" (takeChars (length header) bad==Just header)
  assert "indent-before-name" (takeChars (length header+3) bad==Just (header++"\n  "))
  assert "name-demand-fails" (takeChars (length header+4) bad==Nothing)
  assert "push-forces-frame" (isLeft (push (T.Left "frame bottom") empty))
  assert "push-forces-stack" (isLeft (push badFields (T.Left "stack bottom")))
  let badEnd=pretty (push (frame (str "f") (T.Left "bad end coordinate")) empty)
  let prefix=header++"\n  f, called at "
  assert "location-not-demanded-before-file" (takeChars (length prefix) badEnd==Just prefix)
  assert "location-demands-end-coordinate" (takeChars (length prefix+1) badEnd==Nothing)
  assert "coordinate-overflow-rejected" (render (pretty (push (frame (str "f") (num 9223372036854775808)) empty))==Nothing)
  let delayed=R.runtimePrimitive D.emptyDataEnv T.PIOErrorWithStack (ls [T.Left "error bottom",T.Left "stack bottom"])
  assert "stacked-action-deferred" $ case delayed of T.Right (R.RAction _ _) -> True; _ -> False
  result <- run (catch (act T.PIOErrorWithStack [rv (R.RIOError (T.Left "message bottom")),T.Left "stack bottom"]) ret)
  assert "ignored-catch-keeps-message-stack-lazy" (isErr result)
  result <- run (failWith "message" (push (frame (str "fail") (num 12)) empty))
  assert "uncaught-source-stack" (failureText result==Just "user error (message)\n\nHasCallStack backtrace:\n  fail, called at file.hs:10:2 in pkg:Mod")
  result <- run (catch (catch (raise "a") (k (raise "b"))) (k (raise "c")))
  assert "completed-inner-handler-context-discarded" (failureText result==Just "user error (c)\n\nWhile handling user error (b)")
  result <- run (catch (raise "a") (k (catch (raise "b") (k (raise "c")))))
  assert "active-handler-context-outer-first" (failureText result==Just "user error (c)\n\nWhile handling user error (a)\n\nWhile handling user error (b)")
  result <- run (catch (raise "a") ret)
  case result of
    T.Right value -> do
      again <- run (act T.PIOError [value])
      assert "caught-ioerror-has-no-context" (failureText again==Just "user error (a)")
    _ -> error "failed catch"
  result <- run (catch (T.Left "pure panic") (k (raise "caught")))
  assert "panic-not-caught" (failureText result==Just "pure panic")
  putStrLn "INTERPRETER STACK: 19 checks passed"
