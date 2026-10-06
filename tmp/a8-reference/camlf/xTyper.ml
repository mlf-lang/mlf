open XAst

type env = (typ, typ) XEnv.t

exception Type_error of env * typexp
exception Tycomp_error of env * tycomp * typ

(* evar_eval and tvar_eval access a binding in the environment, using
   ..._scope_diff and a 'shift' operation to reindex in the current
   context the out-of-scope indices *)
let evar_eval env (x : XEnv.EVar.var) : XAst.typ =
  let sigma = XEnv.find_evar x env in
  let offset = XEnv.evar_scope_diff x env in
  map_typ (shift_typ offset) sigma

let tvar_eval env (alpha : XEnv.TVar.var) =
  let sigma = XEnv.find_tvar alpha env in
  let offset = XEnv.tvar_scope_diff alpha env in
  map_typ (shift_typ offset) sigma


let rec type_eval ?(verbose=false) (env : env) (exp : exp) =
  let fail error =
    if verbose then
      Printf.eprintf "Type error:\n%s\n%!"
        (XPrint.doc ~offset:2 (XPrint.type_nonsequent env error));
    raise (Type_error (env, error)) in
  let type_eval = type_eval ~verbose in
  let tycomp_eval = tycomp_eval ~verbose in
  let result = match exp with
    | `Builtin (_b, ty) -> ty
    (* ——————–
       c{κ} : κ *)

    | `Var x ->
        begin
          try evar_eval env x
          with Not_found -> fail (`Var x)
        end

    (*   x:σ ∈ Γ
       ——————————
       Γ ⊢ x : σ *)

    | `Lam (x, sigma, a) ->
        let sigma' = type_eval (XEnv.add_evar x sigma env) a in
        TArrow(sigma, sigma')

    (*      Γ, x:σ ⊢ a : σ'
       ———————————————————————
       Γ ⊢ (λ(x:σ) a) : σ → σ' *)

    | `App (a1, a2) ->
        begin
	  match type_eval env a1, type_eval env a2 with
	    | TArrow(sigma, sigma1), sigma2 when eq_typ sigma sigma2 ->
	        sigma1
	    | s1, s2 -> fail (`App (s1, s2))
        end

    (* Γ ⊢ a1 : σ₂ → σ₁   Γ ⊢ a₂ : σ₂
       ——————————————————————————————
               Γ ⊢ a1 a2 : σ₁         *)

    | `TyAbs (alpha, sigma', a) ->
        let sigma = type_eval (XEnv.add_tvar alpha sigma' env) a in
        TBound (alpha, sigma', sigma)

    (* Γ, α ≥ σ' ⊢ a : σ    α ∉ ftv(Γ)
       ———————————————————————————————
         Γ ⊢ Λ(α>=σ') a : ∀(α>=σ') σ    *)

    | `TyComp (a, phi) ->
        let sigma = type_eval env a in
        let sigma' = tycomp_eval env (sigma, phi) in
        sigma'

    (* Γ ⊢ a : σ    Γ ⊢ φ : σ ≥ σ'
       ———————————————————————————
              Γ ⊢ a[φ] : σ'        *)

    | `Let (x, a, a') ->
        let sigma = type_eval env a in
        let sigma' = type_eval (XEnv.add_evar x sigma env) a' in
        sigma'

    (* Γ ⊢ a : σ    Γ, x:σ ⊢ a' : σ'
       ————————————————————————————
        Γ ⊢ (let x = a in a') : σ'  *)
  in
  result


and tycomp_eval ?(verbose=false) env (sigma, phi) =
  let fail (sigma, phi) =
    if verbose then
      Printf.eprintf "Tycomp error:\n%s\n%!"
        (XPrint.doc ~offset:2 (XPrint.tycomp_nonsequent env phi sigma));
    raise (Tycomp_error (env, phi, sigma)) in
  let (<=) _sigma sigma' = sigma' in
  let tycomp_eval = tycomp_eval ~verbose in
  let result = match (sigma, phi) with
    | (sigma, Refl) -> sigma <= sigma

    (* —————————————
       Γ ⊢ ε : σ ≤ σ *)

    | (sigma1, Trans (phi1, phi2)) ->
        let sigma2 = tycomp_eval env (sigma1, phi1) in
        let sigma3 = tycomp_eval env (sigma2, phi2) in
        sigma1 <= sigma3

    (* Γ ⊢ φ₁ : σ₁ ≤ σ₂     Γ ⊢ φ₂ : σ₂ ≤ σ₃
       —————————————————————————————————————
             Γ ⊢ φ₁;φ₂ : σ₁ ≤ σ₃             *)

    | (TBot, Bot sigma) -> TBot <= sigma
    | (sigma', Bot sigma) -> fail (sigma', Bot sigma)

    (* ——————————————
       Γ ⊢ ▹σ : ⊥ ≤ σ *)

    | (sigma, Hyp alpha) ->
        begin
	  try
            let sigma' = tvar_eval env alpha in
	    if eq_typ sigma sigma'
	    then sigma <= TVar alpha
	    else fail (sigma, Hyp alpha)
	  with Not_found -> fail (sigma, Hyp alpha)
        end

    (*     α≥σ ∈ Γ
       ——————————————
       Γ ⊢ α◃ : σ ≤ α *)

    | (TBound (alpha, sigma1, sigma), Inner phi) ->
        let sigma2 = tycomp_eval env (sigma1, phi) in
        TBound (alpha, sigma1, sigma) <= TBound (alpha, sigma2, sigma)
    | (sigma, Inner phi) -> fail (sigma, Inner phi)

    (*          Γ ⊢ φ : σ₁ ≤ σ₂
       —————————————————————————————————
       Γ ⊢ ∀(≥φ): ∀(α≥σ₁) σ ≤ ∀(α≥σ₂) σ *)

    | (TBound (alpha, sigma, sigma1), Outer (_alpha', phi)) ->
        let sigma2 = tycomp_eval (XEnv.add_tvar alpha sigma env) (sigma1, phi) in
        TBound (alpha, sigma, sigma1) <= TBound (alpha, sigma, sigma2)
    | (sigma, Outer (alpha, phi)) -> fail (sigma, Outer (alpha, phi))

    (*      Γ, α ≥ σ ⊢ φ : σ₁ ≤ σ₂
       ——————————————————————————————————
       Γ ⊢ ∀(α≥)φ : ∀(α≥σ) σ₁ ≤ ∀(α≥σ) σ2 *)

    | (TBound (alpha, sigma, sigma'), Elim) ->
        sigma' <= destruct_typ alpha ~body:sigma' sigma
    | (sigma, Elim) -> fail (sigma, Elim)

    (* —————————————————————————————
       Γ ⊢ & : ∀(α≥σ) σ' ≤ σ'{α ← σ} *)

    | (sigma, Intro) ->
        let alpha = XEnv.TVar.bind in
        let shifted_sigma =
          map_typ (shift_typ (XEnv.TVar.open_ alpha)) sigma in
        sigma <= TBound(alpha, TBot, shifted_sigma)

    (*      α ∉ ftv(σ)
       ————————————————————
       Γ ⊢ ⅋ : σ ≤ ∀(α≥⊥) σ *)
  in
  result


let verbose_typer env exp =
  let module P = XPrint.P in
  let header = "Typing" in
  let typ = type_eval env exp in
  let msg =
    (XPrint.doc
       (P.join [P.string header; P.space;
                P.nest (String.length header)
                  (XPrint.type_sequent env exp typ)])) in
  typ, Some msg
