open XAst
module TVar = XEnv.TVar
module EVar = XEnv.EVar

let rec apply_tycomp = function
  | (TBound (alpha, sigma, sigma'), Elim) ->
      destruct_typ alpha ~body:sigma' sigma
  | (sigma, Intro) ->
      let alpha = TVar.bind in
      let shifted_sigma = map_typ (shift_typ (TVar.open_ alpha)) sigma in
      TBound(alpha, TBot, shifted_sigma)
  | (sigma, Trans(phi1, phi2)) ->
      apply_tycomp (apply_tycomp (sigma, phi1), phi2)
  | (TBound (alpha, sigma, sigma'), Inner phi) ->
      TBound(alpha, apply_tycomp (sigma, phi), sigma')
  | (TBound (alpha, sigma, sigma'), Outer(_, phi)) ->
      TBound (alpha, sigma, apply_tycomp (sigma', phi))
  | (_sigma, Hyp alpha) -> TVar alpha
  | (TBot, Bot sigma) -> sigma
  | (sigma, Refl) -> sigma
  | (sigma, phi) ->
      raise (XTyper.Tycomp_error (XEnv.empty, phi, sigma))

exception No_reduction

let reduce_beta : XAst.exp -> XAst.exp = function
  | `App(`Lam (x, _, a1), a2)
  | `Let (x, a2, a1) ->
      destruct_e_exp x ~body:a1 a2
        (* (λ(x:σ) a₁) a₂    —→ a₁{x ← a₂}
           let x = a2 in a1  —→ a₁{x ← a₂} *)
  | _ -> raise No_reduction

let reduce_lambda : XAst.exp -> XAst.exp = function
  | `TyComp(a, Refl) -> a
      (* a[ε] —→ a *)

  | `TyComp(a, Trans(phi, phi')) ->
      `TyComp(`TyComp(a, phi), phi')
      (* a[φ;φ'] —→ a[φ][φ'] *)

  | `TyComp(a, Intro) ->
      let alpha = TVar.bind in
      `TyAbs(alpha, TBot, map_exp (shift_t_exp (TVar.open_ alpha)) a)
      (* a[⅋] —→ Λ(α≥⊥) a   (α ∉ ftv(a)) *)

  | `TyComp(`TyAbs(alpha, sigma, a), Elim) ->
      let body = map_exp (subst_tycomp_in_exp Refl) a in
      destruct_t_exp alpha ~body sigma
      (* (Λ(α≥σ) a)[&] —→ a{α◃ ← ε}{α ← σ} *)

  | `TyComp(`TyAbs(alpha, sigma, a), Inner phi) ->
      let sigma_phi =
        (* As sigma is not in the alpha scope, phi needn't be opened *)
        try apply_tycomp (sigma, phi)
        with XTyper.Tycomp_error _ -> raise No_reduction in
      let inner_phi =
	map_tycomp (shift_tycomp (TVar.open_ alpha)) phi in
      let a' =
        map_exp
	  (subst_tycomp_in_exp (Trans(inner_phi, Hyp (`B TVar.zero))))
          a in
      `TyAbs(alpha, sigma_phi, a')
      (* (Λ(α≥σ) a)[∀(≥φ)] —→ Λ(α≥σ[φ]) a{α◃ ← φ;α◃} *)

  | `TyComp(`TyAbs(alpha, sigma, a), Outer (_, phi)) ->
      `TyAbs(alpha, sigma, `TyComp(a, phi))

      (* (Λ(α≥σ) a)[∀(α≥)φ] —→ Λ(α≥σ) a[φ] *)

  | `TyComp(`Builtin (b, ty), phi) ->
      `Builtin(b, apply_tycomp (ty, phi))
        
      (* c{κ}[φ] —→ c{κ[φ]} *)

  | _ -> raise No_reduction

let reduce_builtin : XAst.exp -> XAst.exp = function
  | `App (`App 
            (`Builtin (`Arith_op op, _),
             `Builtin (`Int a, _)), `Builtin (`Int b, _)) ->
    let eval_op = function
      | `Plus -> (+)
      | `Minus -> (-) in
    `Builtin (`Int (eval_op op a b), TConst `Int)
  | `App (`App 
            (`Builtin (`EqInt, _),
             `Builtin (`Int a, _)), `Builtin (`Int b, _)) ->
    `Builtin (`Bool (a = b), TConst `Bool)
  | `App (`Builtin (`If, _), `Builtin (`Bool b, _)) ->
      let module X = XAst.DSL in
      (* << Λ(α≥⊥).λ(x:α).λ(y:α). $if b then <<x>> else <<y>>$ >> *)
      X.to_exp
        (X.tyabs_h X.tbot (fun alpha ->
          X.lam_h alpha (fun x ->
            X.lam_h alpha (fun y ->
              if b then x else y))))
  | _ -> raise No_reduction

(* this reduction rule is separated from the other reduce_builtin as
   it is potentially non-terminating *)
(* fix f x  —→ f (fix f) x *)
let reduce_fix : XAst.exp -> XAst.exp = function
  | `App (`App (`Builtin (`Fix, _), f) as fix_f, x) ->
      `App (`App (f, fix_f), x)
  | _ -> raise No_reduction

let rec reduce_context reduce : XAst.exp -> XAst.exp =
  let deep x = reduce_context reduce x in
  fun e ->
    try reduce e
    with No_reduction ->
      match e with
      | `TyComp(e, phi) -> `TyComp(deep e, phi)
      | `Lam(x, sigma, e) -> `Lam(x, sigma, deep e)
      | `TyAbs(alpha, sigma, e) -> `TyAbs(alpha, sigma, deep e)
      | `App(e, e') ->
          begin
            try `App(deep e, e')
            with No_reduction -> `App (e, deep e')
          end
      | `Let(x, e, e') ->
          begin
            try `Let(x, deep e, e')
            with No_reduction -> `Let (x, e, deep e')
          end
      | `Var _ | `Builtin _ -> raise No_reduction

let reduce_step =
  let (++) f g = fun x ->
    try reduce_context f x
    with No_reduction -> reduce_context g x in
  reduce_lambda ++ reduce_beta ++ reduce_builtin ++ reduce_fix

let try_reduce reduce x =
  try Some (reduce x)
  with No_reduction -> None

let rec reduce ?(log=fun _ -> ()) a =
  log a;
  match try_reduce reduce_step a with
    | Some a -> reduce ~log a
    | None -> a


let verbose_reducer ?(type_check=false) exp =
  let module P = XPrint.P in
  let first_line = ref true in
  let log_buf = Buffer.create 10 in
  Buffer.add_string log_buf "Reducing :\n";
  let log exp =
    let prefix =
      P.cat
        (if !first_line
         then (first_line := false; P.space)
         else P.string (Symbol.reduces_to ())) P.space in
    let result = XPrint.exp XEnv.empty exp in
    let log_msg =
      (XPrint.doc
         (P.cat prefix
            (P.nest 2
               (if not type_check then result
                else
                  let typ =
                    XPrint.typ XEnv.empty
                      (XTyper.type_eval XEnv.empty exp) in
                  List.fold_right P.cat
                    [result; P.break1; P.colon; P.space; typ]
                    P.empty)))) in
    Buffer.add_string log_buf log_msg;
    Buffer.add_char log_buf '\n' in
  let result =
    try reduce ~log exp
    with exn ->
      (* TODO use proper error reporting *)
      Printf.eprintf "Error during reduction. Log :\n%s\n"
        (Buffer.contents log_buf);
      raise exn in
  result, Some (Buffer.contents log_buf)
