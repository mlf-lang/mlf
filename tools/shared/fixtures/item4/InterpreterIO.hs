{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Data as D
import qualified MLF.Host.Base as B

ls = foldr T.Cons T.Nil
rv = T.Right
act p args = rv (R.RAction p (ls args))
prim p args = R.primitiveResult D.emptyDataEnv p (ls args)
msg = rv (R.runtimeTextChars "bad λ😀" 0)
err = prim T.PUserError [msg]
raise = act T.PIOError [err]
ret = rv (R.RPrimitive T.PIOReturn T.Nil)
rethrow = rv (R.RPrimitive T.PIOError T.Nil)
catch a h = act T.PCatchIOError [a,h]
run = R.runAction T.Nil D.emptyDataEnv
assert label ok = if ok then putStrLn ("PASS "++label) else error ("FAIL "++label)
isErr (T.Right (T.Right (R.RIOError _))) = True
isErr _ = False
isFatal (T.Left _) = True
isFatal _ = False
step st p args = R.runActionState T.Nil D.emptyDataEnv st (act p args)
value (T.Right (T.Pair st (R.RIOSuccess v))) = (st,v)
value _ = error "unexpected action result"
intResult n (T.Right (T.Pair _ (R.RIOSuccess (T.Right (R.RInteger m))))) = n==m
intResult _ _ = False
main = do
  assert "char-surrogate-valid" $ case prim T.PCharFromCode [rv (R.RInteger 55296)] of T.Right (R.RChar 55296) -> True; _ -> False
  assert "char-invalid-negative" $ isFatal (prim T.PCharFromCode [rv (R.RInteger (-1))])
  assert "char-invalid-high" $ isFatal (prim T.PCharFromCode [rv (R.RInteger 1114112)])
  assert "unicode-roundtrip" $ case prim T.PTextFromChars [prim T.PTextToChars [rv (R.RString "aλ😀")]] of T.Right (R.RString s) -> B.unpack s=="aλ😀"; _ -> False
  let surrogate = rv (R.RConstructor ":" (ls [rv (R.RChar 55296), rv (R.RConstructor "[]" T.Nil)]))
  assert "text-rejects-surrogate" $ isFatal (prim T.PTextFromChars [surrogate])
  assert "error-message-surrogate-lossless" $ case prim T.PIOErrorString [prim T.PUserError [surrogate]] of T.Right (R.RConstructor _ (T.Cons (T.Right (R.RChar 55296)) _)) -> True; _ -> False
  r <- run (catch raise ret); assert "catch-user-error" (isErr r)
  r <- run (catch (act T.PIOBind [raise,T.Left "continuation forced"]) ret); assert "failure-left-zero" (isErr r)
  r <- run (catch (catch raise rethrow) ret); assert "handler-failure-outer-catch" (isErr r)
  r <- run (catch (T.Left "pure panic") ret); assert "pure-panic-not-caught" (isFatal r)
  r <- run (catch (act T.PIOReturn [T.Left "deferred pure panic"]) ret)
  assert "returned-bottom-not-io-error" $ case r of T.Right (T.Left _) -> True; _ -> False
  r <- run (act T.PIOError [prim T.PUserError [surrogate]])
  assert "uncaught-surrogate-escaped" $ case r of T.Left s -> B.unpack s=="user error (\\55296)"; _ -> False
  r <- step R.rAsyncEmpty T.PAsyncScopeNew [rv (R.RInteger 4),rv (R.RInteger 4)]
  let (s1,scope)=value r
  r <- step s1 T.PAsyncEnqueue [scope,raise]
  let (s2,_)=value r
  r <- step s2 T.PAsyncEnqueue [scope,act T.PIOReturn [rv (R.RInteger 42)]]
  let (s3,_)=value r
  r <- R.runActionState T.Nil D.emptyDataEnv s3 (catch (act T.PAsyncStep [scope]) ret)
  let (s4,recovered)=value r
  assert "async-error-caught" $ case recovered of T.Right (R.RIOError _) -> True; _ -> False
  r <- step s4 T.PAsyncStep [scope]
  assert "async-busy-cleared-queue-retained" (intResult 0 r)
  let (s5,_)=value r
  r <- step s5 T.PAsyncStep [scope]
  assert "async-queue-drained" (intResult 1 r)
  assert "empty-text-roundtrip" $ case prim T.PTextFromChars [prim T.PTextToChars [rv (R.RString "")]] of T.Right (R.RString s) -> B.unpack s==""; _ -> False
  assert "char-code-surrogate" $ case prim T.PCharCode [rv (R.RChar 55296)] of T.Right (R.RInteger 55296) -> True; _ -> False
  assert "failure-action-construction-deferred" $ case R.runtimePrimitive D.emptyDataEnv T.PIOError (ls [T.Left "unused error argument"]) of T.Right (R.RAction _ _) -> True; _ -> False
  r <- run (catch (act T.PIOError [rv (R.RIOError (T.Left "unused error message"))]) ret)
  assert "catch-does-not-demand-error-message" (isErr r)
  r <- R.perform T.Nil D.emptyDataEnv T.PCatchIOError (ls [raise,ret])
  assert "perform-entry-uses-typed-channel" (isErr r)
  putStrLn "INTERPRETER ITEM4: 20 checks passed"
