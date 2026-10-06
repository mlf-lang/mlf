(** Definitions *)
(** We use De Bruijn indices to represent binders.
    - free variables have names
    - bound variables use De Bruijn indices
*)
open XEnv

(** Types *)
type typ =
  | TConst of const_type
  | TVar of TVar.var
  | TArrow of typ * typ               (** sigma -> sigma *)
  | TBound of TVar.binder * typ * typ (** ∀(alpha>=sigma) sigma *)
  | TBot

and const_type = [ `Int | `Unit | `Bool ]

let eq_typ : typ -> typ -> bool = (=)
(* With De Bruijn indices, equivalence is just structural equality *)

(** Term traversal operators : map_*, shift_*, subst_*...

    For the three kinds of XMLF terms (types, type computations and
    expressions), we have a generic traversal operator "map_<term>" :
    map_typ, map_tycomp, map_exp. This operator is parametrized by
    "handlers", wich are called on variables in the term. Handlers can
    act differently on different kind of variables (expression
    variables, type variables, type variables in the Hyp type
    computation).
    Handlers are only called on variables outside the current
    context : for example, calling a handler on (λ(x:⊥) x) won't
    change x, as it is a bound variable local to the expression.

    The other traversal functions are handlers provided for use with
    the map_* functions :
      - shift_* handlers will shift the De Bruijn indices of variables
        of a given offset
      - subst_* handlers will substitute terms for the variable just
        outside scope; substituted terms are shifted to match the
        local scopes in the term

    Expression handlers also carry type computation handlers and
    type handlers, wich they call on the types or type computations
    wich are subterms of the given expression.

    each map_* function (map_typ, map_exp..) is actually
    a specialisation of a corresponding map_*_ function (map_typ_,
    map_exp_), wich is parametrized on the depth of the current
    context. map_typ should be called when at the root of a term, but
    map_typ_ must be called with the appropriate context depth if one
    want to open a subterm. For example, map_exp calls map_tycomp_
    when it finds a type computations deep inside an expression.


    Delicate example of use of the open/handler pairs :

    - reduction rule (let x = a2 in a1 —→ a₁{x ← a₂})
      it is actually a reduction in two steps :
         let x = a2 in a1
      —→ let x = a2 in a1{x <- a2}  
         (* subst on a1; a2, entering a scope, must be opened *)
      —→ a1{x <- a2}
         (* a1, leaving a scope, must be closed *)

    `Let (x, a2, a1) ->
      let inner_a2 = map (shift (Var.open x)) a2 in
      let subst_result = map (subst inner_a2) a1 in
      map (shift (Var.close x)) subst_result

    Note that the substitution is done on `a1`, and not on the whole
    `let..in a1` : subst_.. act on the *outer* variable, and `x` is
    the outer variable of a1, but not of `let..in a1`.

    This quite subtle interaction between scopes and substitutions is
    encapsuled in the destruct_* functions wich do exactly this.
 *)

let map_typ_ handler ~scope sigma =
  let rec map_ scope = function
    (* map transparently *)
  | TBot -> TBot
  | TConst const -> TConst const
  | TArrow (sigma, tau) -> TArrow (map_ scope sigma, map_ scope tau)
  | TVar (`F x) -> TVar (`F x)
  (* variable case *)
  | TVar (`B v) -> handler ~scope v
  (* binder case *)
  | TBound (alpha, sigma, tau) ->
      TBound (alpha,
              map_ scope sigma,
              map_ (TVar.open_s alpha scope) tau) in
  map_ scope sigma
let map_typ handler = map_typ_ handler ~scope:TVar.zero_s

let id_typ ~scope v = ignore scope; TVar (`B v)

let shift_typ offset ~scope v =
  TVar (`B (TVar.shift offset ~scope v))

let subst_typ sigma ~scope v =
  if not (TVar.is_hole v ~scope)
  then TVar (`B v)
  else map_typ (shift_typ scope) sigma

(* binder(α,σ) → σ{α←τ} *)
let destruct_typ alpha ~body tau =
  let sigma = body in
  let inner_tau = map_typ (shift_typ (TVar.open_ alpha)) tau in
  let subst_result = map_typ (subst_typ inner_tau) sigma in
  map_typ (shift_typ (TVar.close_ alpha)) subst_result
  (* TODO optimize
     map_typ 
       (comp_typ_handler
         (close_typ alpha)
         (subst_typ (map_typ (open_typ alpha) tau))) sigma

     subst_typ (map_typ (open_typ alpha) tau)
     =?=
     (fun ~scope ->
       subst_typ (open_typ a2) ~scope:(TVar.open_s alpha scope))
  *)

let rec ftv_typ = function
  | TBot | TConst _ | TVar (`B _) -> []
  | TVar (`F k) -> [k]
  | TArrow (sigma, tau) | TBound(_, sigma, tau) ->
      ftv_typ sigma @ ftv_typ tau

let rec size_typ = function
  | TBot | TVar _ | TConst _ -> 0
  | TArrow (sigma, tau) | TBound (_, sigma, tau) ->
      1 + size_typ sigma + size_typ tau

(** Type computations *)
type tycomp =
  | Refl
  | Bot of typ
  | Hyp of TVar.var
  | Inner of tycomp
  | Outer of TVar.binder * tycomp
  | Elim
  | Intro
  | Trans of tycomp * tycomp

(** A common use of type computations,
   similar to System_F type application *)
let ty_app sigma = Trans(Inner (Bot sigma), Elim)

(** There are three different ways to "open" a type computation with a
    type variable :

    - If you want to replace all (α◃) by another *type computation*,
    use map_tycomp; map_tycomp does not recurse inside types, for
    example : [(Λ(α≥σ) a)[∀(≥φ)] —→ Λ(α≥σ) a{α◃ ← φ;α◃}]

    - If you want to replace all (α) by another *type expression*, use
    map_typ_in_tycomp, wich recurse inside types. There should never
    be a (α◃) in your expression (as (σ◃) would be meaningless), and
    map_typ_in_tycomp will raise an exception if it encounters some.

    - If you want to replace all (α) by (β), another *type variable*,
    use map_tvar_in_tycomp. This is useful when you want to open
    a type abstraction into the type context, replacing the 0-bound
    variables with a fresh free variable. This operation will affect
    both types (α) and type computations (α◃).
*)

let map_tycomp_ (typ_handler, hyp_handler) ~scope phi =
  let rec map_ scope = function
    (* map transparently *)
    | (Refl | Intro | Elim) as phi -> phi
    | Inner phi -> Inner (map_ scope phi)
    | Trans (phi, khi) -> Trans (map_ scope phi, map_ scope khi)
    | Bot sigma -> Bot (map_typ_ typ_handler ~scope sigma)
    | Hyp (`F alpha) -> Hyp (`F alpha)
    (* var case *)
    | Hyp (`B v) -> hyp_handler ~scope v
    (* binder case *)
    | Outer (alpha, phi) ->
	Outer (alpha, map_ (TVar.open_s alpha scope) phi) in
  map_ scope phi
let map_tycomp handler = map_tycomp_ handler ~scope:TVar.zero_s

let id_tycomp ~scope v =
  ignore scope; Hyp (`B v)

let shift_tycomp offset =
  let typ_handler = shift_typ offset in
  let hyp_handler ~scope v =
    Hyp (`B (TVar.shift offset ~scope v)) in
  (typ_handler, hyp_handler)

let subst_tycomp phi =
  let hyp_handler ~scope v =
    if not (TVar.is_hole v ~scope)
    then Hyp (`B v)
    else map_tycomp (shift_tycomp scope) phi in
  (id_typ, hyp_handler)

let subst_typ_in_tycomp sigma =
  let typ_handler = subst_typ sigma in
  let hyp_handler ~scope v =
    (* (α◃){α ← σ} is meaningless : fail in that case*)
    assert (not (TVar.is_hole v ~scope));
    Hyp (`B v) in
  (typ_handler, hyp_handler)

let rec size_tycomp = function
  | Refl | Elim | Intro | Hyp _ -> 0
  | Bot sigma -> 1 + size_typ sigma
  | Inner phi | Outer (_, phi) -> 1 + size_tycomp phi
  | Trans (phi, khi) -> 1 + size_tycomp phi + size_tycomp khi

(* binder(α,φ) → φ{α←τ} *)
let destruct_tycomp alpha ~body tau =
  let phi = body in
  let inner_tau = map_typ (shift_typ (TVar.open_ alpha)) tau in
  let subst_result = map_tycomp (subst_typ_in_tycomp inner_tau) phi in
  map_tycomp (shift_tycomp (TVar.close_ alpha)) subst_result
  (* TODO optimize *)

(** Expressions *)
(** Open (derecursified) expression type : useful for error reporting.
   We will present a typing error as a type-expression, (typ _exp) :
   an expression were subterms have been replaced by the corresponding
   types. *)
type 'exp _exp =
  [ `Var of EVar.var
  | `Builtin of builtin * typ
  | `Lam of EVar.binder * typ * 'exp      (** λ(x:σ) a *)
  | `App of 'exp * 'exp                   (** a a *)
  | `TyAbs of TVar.binder * typ * 'exp    (** Λ(α≥σ) a *)
  | `TyComp of 'exp * tycomp              (** a[φ] *)
  | `Let of EVar.binder * 'exp * 'exp ]   (** let x = a in a *)

and builtin =
  [ `Unit
  | `Int of int
  | `Bool of bool
  | `EqInt
  | `If
  | `Fix
  | `Arith_op of [`Plus | `Minus] ]

(** Closed expression type (the one you expect) *)
type exp = exp _exp

(** Type-Expressions *)
type typexp = typ _exp

let map_exp_ (typ_handler, tycomp_handler, handler) ~escope ~tscope a =
  let rec map_ (escope : EVar.scope) (tscope : TVar.scope) : exp -> exp =
    let _open a = map_ escope tscope a in
    let _eopen x a =
      map_ (EVar.open_s x escope) tscope a in
    let _topen alpha a =
      map_ escope (TVar.open_s alpha tscope) a in
    let _map_typ sigma =
      map_typ_ typ_handler ~scope:tscope sigma in
    let _map_tycomp phi =
      map_tycomp_ (typ_handler, tycomp_handler) ~scope:tscope phi in
    function
    (* map transparently *)
    | `Builtin b -> `Builtin b
    | `Var (`F x) -> `Var (`F x)
    | `App(a1, a2) -> `App(_open a1, _open a2)
    | `TyComp(a, phi) -> `TyComp(_open a, _map_tycomp phi)
    (* variable case *)
    | `Var (`B v) -> handler ~escope ~tscope v
    (* binder cases *)
    | `TyAbs(alpha, sigma, a) -> `TyAbs(alpha, _map_typ sigma, _topen alpha a)
    | `Lam(x, sigma, a) -> `Lam(x, _map_typ sigma, _eopen x a)
    | `Let (x, a, a') -> `Let(x, _open a, _eopen x a') in
  map_ escope tscope a
let map_exp handler = map_exp_ handler ~escope:EVar.zero_s ~tscope:TVar.zero_s

let id_exp ~escope ~tscope v = ignore (escope, tscope); `Var (`B v)

let app2 (f, g) x = (f x, g x)
let app3 (f, g, h) x = (f x, g x, h x)

let tvar_handler (typ_handler, tycomp_handler) =
  (typ_handler, tycomp_handler, id_exp)

let evar_handler handler =
  (id_typ, id_tycomp, handler)

let shift_exp ~eoffset ~toffset =
  let typ_handler, tycomp_handler = shift_tycomp toffset in
  let exp_handler ~escope ~tscope v =
    ignore tscope;
    `Var (`B (EVar.shift eoffset ~scope:escope v)) in
  (typ_handler, tycomp_handler, exp_handler)

let shift_e_exp ~offset =
  shift_exp ~eoffset:offset ~toffset:TVar.zero_s
let shift_t_exp ~offset =
  shift_exp ~eoffset:EVar.zero_s ~toffset:offset

let subst_exp a =
  let handler ~escope ~tscope v =
    if not (EVar.is_hole v ~scope:escope)
    then `Var (`B v)
    else
      map_exp (shift_exp ~eoffset:escope ~toffset:tscope) a in
  evar_handler handler

let subst_tycomp_in_exp phi =
  tvar_handler (subst_tycomp phi)

let subst_typ_in_exp sigma =
  tvar_handler (subst_typ_in_tycomp sigma)

let _size_exp size : _ _exp -> int = function
  | `Var _ | `Builtin _ -> 0
  | `TyComp (a, phi) -> 1 + size a + size_tycomp phi
  | `Lam (_, sigma, a) | `TyAbs (_, sigma, a) -> 1 + size_typ sigma + size a
  | `App (a, b) | `Let (_, a, b) -> 1 + size a + size b

let rec size_exp exp = _size_exp size_exp exp

(* binder(α, body) -> body{α←σ} *)
let destruct_t_exp alpha ~body sigma =
  let inner_sigma = map_typ (shift_typ (TVar.open_ alpha)) sigma in
  let subst_result = map_exp (subst_typ_in_exp inner_sigma) body in
  map_exp (shift_t_exp (TVar.close_ alpha)) subst_result
  (* TODO optimize *)

(* binder(x, body) -> body{x←term} *)
let destruct_e_exp x ~body term =
  let inner_term = map_exp (shift_e_exp (EVar.open_ x)) term in
  let subst_result = map_exp (subst_exp inner_term) body in
  map_exp (shift_e_exp (EVar.close_ x)) subst_result
  (* TODO optimize *)


(** A DSL for writing De Bruijn terms "the classical way" :

    let x, alpha = ebind (), tbind () in
    let sigma = tbound alpha tbot (tarrow (tvar alpha) (tvar alpha)) in
    lam x sigma (app (evar x) (evar x)) *)
module DSL : sig
  type tvar
  type evar

  type typ'
  type tycomp'
  type exp'

  val to_typ : typ' -> typ
  val to_tycomp : tycomp' -> tycomp
  val to_exp : exp' -> exp

  val of_typ : typ -> typ'
  val of_tycomp : tycomp -> tycomp'
  val of_exp : exp -> exp'

  val tbind : unit -> tvar
  val tvar : tvar -> typ'
  val ftvar : string -> typ'
  val tarrow : typ' -> typ' -> typ'
  val tbound : tvar -> typ' -> typ' -> typ'
  val tbot : typ'
  val tconst : const_type -> typ'

  val refl : tycomp'
  val bot : typ' -> tycomp'
  val hyp : tvar -> tycomp'
  val inner : tycomp' -> tycomp'
  val outer : tvar -> tycomp' -> tycomp'
  val elim : tycomp'
  val intro : tycomp'
  val trans : tycomp' -> tycomp' -> tycomp'
  val tyapp : typ' -> tycomp'

  val ebind : unit -> evar
  val evar : evar -> exp'
  val fevar : string -> exp'
  val lam : evar -> typ' -> exp' -> exp'
  val app : exp' -> exp' -> exp'
  val tyabs : tvar -> typ' -> exp' -> exp'
  val tycomp : exp' -> tycomp' -> exp'
  val let_ : evar -> exp' -> exp' -> exp'
  val builtin : builtin -> typ -> exp'

  val to_exp_debug : exp' -> exp

  (* binders, HOAS style *)
  val tbound_h : typ' -> (typ' -> typ') -> typ'
  val outer_h : (typ' -> tycomp') -> tycomp'
  val lam_h : typ' -> (exp' -> exp') -> exp'
  val tyabs_h : typ' -> (typ' -> exp') -> exp'
  val let_h : exp' -> (exp' -> exp') -> exp'
end = struct
  module MakeIndex (Var : VarS) : sig
    type index
    type indexing = index -> Var.bound_var
    val index : unit -> index
    val bind : index -> Var.binder
    val open_ : index -> indexing -> indexing
  end = struct
    type index = int
    type indexing = index -> Var.bound_var

    let fresh =
      let counter = ref 0 in
      fun () ->
        incr counter; !counter

    let index = fresh
    let bind _ = Var.bind
    let open_ target indexing =
      fun var ->
        if var = target then Var.zero
        else
          let diff = Var.open_ (bind target) in
          Var.shift diff ~scope:Var.zero_s (indexing var)
  end

  module TTerm = MakeIndex(TVar)
  module ETerm = MakeIndex(EVar)

  type tvar = TTerm.index
  let tbind () = TTerm.index ()

  type evar = ETerm.index
  let ebind () = ETerm.index ()

  type typ' = TTerm.indexing -> typ
  type tycomp' = TTerm.indexing -> tycomp
  type exp' = TTerm.indexing -> ETerm.indexing -> exp

  let tvar alpha = fun idx -> TVar (`B (idx alpha))
  let evar x = fun _tidx eidx -> `Var (`B (eidx x))

  let to_typ sigma = sigma (fun _ -> raise Not_found)
  let to_tycomp phi = phi (fun _ -> raise Not_found)
  let to_exp a = a (fun _ -> raise Not_found) (fun _ -> raise Not_found)

  let of_typ sigma = fun _idx -> sigma
  let of_tycomp phi = fun _idx -> phi
  let of_exp a = fun _tidx _eidx -> a

  let ftvar alpha = fun _idx -> TVar (`F (TVar.fvar alpha))
  let tbot = fun _idx -> TBot
  let tconst const = fun _idx -> TConst const
  let tarrow sigma tau = fun idx -> TArrow (sigma idx, tau idx)
  let tbound alpha sigma tau = fun idx ->
    TBound (TTerm.bind alpha, sigma idx, tau (TTerm.open_ alpha idx))

  let refl = fun _idx -> Refl
  let bot sigma = fun idx -> Bot (sigma idx)
  let hyp alpha = fun idx -> Hyp (`B (idx alpha))
  let inner phi = fun idx -> Inner (phi idx)
  let outer alpha phi = fun idx ->
    Outer (TTerm.bind alpha, phi (TTerm.open_ alpha idx))
  let elim = fun _idx -> Elim
  let intro = fun _idx -> Intro
  let trans phi khi = fun idx -> Trans (phi idx, khi idx)

  let tyapp sigma = fun idx -> ty_app (sigma idx)

  let fevar x = fun _tidx _eidx -> `Var (`F (EVar.fvar x))
  let lam x sigma a = fun tidx eidx ->
    `Lam (ETerm.bind x, sigma tidx, a tidx (ETerm.open_ x eidx))
  let app a1 a2 = fun tidx eidx -> `App(a1 tidx eidx, a2 tidx eidx)
  let tyabs alpha sigma a = fun tidx eidx ->
    `TyAbs (TTerm.bind alpha, sigma tidx, a (TTerm.open_ alpha tidx) eidx)
  let tycomp a phi = fun tidx eidx -> `TyComp (a tidx eidx, phi tidx)
  let let_ x a a' = fun tidx eidx ->
    `Let (ETerm.bind x, a tidx eidx, a' tidx (ETerm.open_ x eidx))
  let builtin b ty = fun _tidx _eidx -> `Builtin (b, ty)

  let to_exp_debug =
    let module Escape = struct
      exception Var of tvar
      let rec to_exp exp' =
        try exp' (fun v -> raise (Var v)) (fun _ -> raise Not_found)
        with Var v ->
          prerr_endline "escape !";
          to_exp (tyabs v tbot exp')
    end in
    Escape.to_exp


  let hoas binder new_var exp_of_var =
    fun f ->
      let v = new_var () in
      binder v (f (exp_of_var v))
      
  let bounded_hoas binder v ev =
    fun bound ->
      hoas (fun v -> binder v bound) v ev
        
  let tbound_h = bounded_hoas tbound tbind tvar
      
  let outer_h = hoas outer tbind tvar
      
  let lam_h = bounded_hoas lam ebind evar
  let tyabs_h = bounded_hoas tyabs tbind tvar
  let let_h = bounded_hoas let_ ebind evar    
end
