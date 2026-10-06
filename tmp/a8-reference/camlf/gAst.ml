open AST
open Locations
open TypingErrors

type typevar = ETypeConstructors.typevar
module TypeVarMap = ETypeConstructors.TypeVarMap

(** Given all the bloat in AST (tuples and what not), we will begin by
    designing a small source language, designed for translation to gMLF.

    It is roughly a subset of AST.typing_expr, but has additional
    information on variables : both gMLF and xMLF translation will
    want to know wether a variable is lambda-bound (unified) or
    let-bound (instancied). *)
(** Case `VAL is used for free variables that should have been bound
   to a previous toplevel phrase. *)
type 'a bound_aware_expr_ =
    [ `Let of value loc * 'c * 'c
    | `Value of [ `LAM | `LET of 'a loc | `VAL of 'a option] * value ]
      (* Capital names help distinguish them from main AST names.. *)
constraint 'c = 'a loc

type constants_expr =
  [ `Ct of AST.value * EType.constant_monotype ]

type 'a expr_ =
    [ 'a minimal_expr_
    | constants_expr
    | 'a desugared_expr_
    | 'a bound_aware_expr_ ]
type expr = expr expr_

let global_env = ValueMap.empty

let desugar =
  let rec desugar env : typing_expr loc -> expr loc =
    fun e ->
      let e' = match e.obj with
      (* keep the bloat away ! *)
      | `Uple _ | `Constr _ -> assert false
            (* just mapping *)
      | `Ct _ | `CoerceCt _ | `BuiltinCt _ as const -> const
      | `App(a1, a2) -> `App(desugar env a1, desugar env a2)
      | `TyAbs(abs, a) -> `TyAbs(abs, desugar env a)
      | `TyApp(a, sigma) -> `TyApp(desugar env a, sigma)
      | `SomeTy(q, e) -> `SomeTy(q, desugar env e)
            (* binder cases *)
      | `Abs(v, a) -> `Abs(v, desugar (ValueMap.add v.obj `LAM env) a)
      | `Let(`NonRec, (`Unconstrained v, a1), a2) ->
          let a1 = desugar env a1 in
          let a2 = desugar (ValueMap.add v.obj (`LET a1) env) a2 in
	  `Let(v, a1, a2)
            (* value case *)
      | `Value v ->
	  begin
	    try `Value (ValueMap.find v env, v)
            with Not_found -> `Value (`VAL None, v)
          end in
      with_loc e e' in
  desugar ValueMap.empty

let rec resugar : expr loc -> typing_expr loc =
  fun e ->
    { e with obj = match e.obj with
        | `Ct _ | `CoerceCt _ | `BuiltinCt _ as const -> const
        | `App(a1, a2) -> `App(resugar a1, resugar a2)
        | `TyApp (a, sigma) -> `TyApp (resugar a, sigma)
        | `SomeTy (q, e) -> `SomeTy (q, resugar e)
            (* binder cases *)
        | `Abs(v, a) -> `Abs(v, resugar a)
        | `TyAbs (alpha, a) -> `TyAbs(alpha, resugar a)
        | `Let (v, a1, a2) ->
            `Let(`NonRec, (`Unconstrained v, resugar a1), resugar a2)
              (* value case *)
        | `Value (_, v) -> `Value v }

let prefix_bound_env env q1 q2 =
  let check_abs env {obj=(alpha1, _)} {obj=(alpha2, _)} =
    EType.bound_env env alpha1 alpha2 in
  List.fold_left2 check_abs env q1 q2

let coercion_alpha_equiv env (q1, {obj=t1}) (q2, {obj=t2}) =
  List.length q1 = List.length q2
  && let env = prefix_bound_env env q1 q2 in
     EType.alpha_equiv ~env t1 t2

let alpha_equiv : expr loc -> expr loc -> bool =
  let rec check env a1 a2 = match (a1.obj : expr), (a2.obj : expr) with
    | `App (b1, b1'), `App (b2, b2') -> check env b1 b2 && check env b1' b2'
    | `App (_, _), _ | _, `App (_, _) -> false

    | `TyApp (a1, {obj=sigma1}), `TyApp (a2, {obj=sigma2}) ->
        check env a1 a2 && EType.alpha_equiv ~env:(snd env) sigma1 sigma2
    | `TyApp _, _ | _, `TyApp _ -> false

    | `Value (_, v1), `Value (_, v2) ->
        (try ValueMap.find v1 (fst env) = v2
         with Not_found -> v1 = v2) (* free vars must be equal *)
    | `Value _, _ | _, `Value _ -> false

    | `Ct (v1, t1), `Ct (v2, t2) -> equal_ct (v1, t1) (v2, t2)
    | `Ct (_, _), _ | _, `Ct (_, _) -> false

    | `Abs (v1, a1), `Abs(v2, a2) ->
        let env_e, env_t = env in
        let env' = (ValueMap.add v1.obj v2.obj env_e), env_t in
        check env' a1 a2
    | `Abs (_, _), _ | _, `Abs (_, _) -> false

    | `TyAbs ({obj=(alpha1, bound1)}, a1),
      `TyAbs ({obj=(alpha2, bound2)}, a2) ->
        let env_e, env_t = env in
        let env' = env_e, EType.bound_env env_t alpha1 alpha2 in
        check env' a1 a2 &&
        (match bound1, bound2 with
        | `Kind k1, `Kind k2 -> k1 = k2
        | `Bound (l1, t1), `Bound (l2, t2) ->
            l1 = l2 && EType.alpha_equiv ~env:env_t t1 t2
        | `Kind _, `Bound _ | `Bound _, `Kind _ -> false)
    | `TyAbs (_, _), _ | _, `TyAbs (_, _) -> false

    | `SomeTy (q1, e1), `SomeTy (q2, e2) ->
        let env_e, env_t = env in
        List.length q1 = List.length q2
        && check (env_e, prefix_bound_env env_t q1 q2) e1 e2
    | `SomeTy _, _ | _, `SomeTy _ -> false

    | `Let (v1, a1, a1'), `Let (v2, a2, a2') ->
        check env a1 a2
        &&
          let env_e, env_t = env in
          let env' = (ValueMap.add v1.obj v2.obj env_e), env_t in
          check env' a1' a2'
    | `Let(_, _, _), _ | _, `Let(_, _, _) -> false

    | `CoerceCt {obj=c1}, `CoerceCt {obj=c2} ->
        coercion_alpha_equiv (snd env) c1 c2
    | `CoerceCt _, _ | _, `CoerceCt _ -> false

    | `BuiltinCt _, _ ->
        assert false in
  let env_e : AST.value ValueMap.t = ValueMap.empty in
  let env_t : typevar TypeVarMap.t = TypeVarMap.empty in
  check (env_e, env_t)

let source_alpha_equiv a b =
  let desugar a = desugar (AST.desugar a) in
  alpha_equiv (desugar a) (desugar b)
