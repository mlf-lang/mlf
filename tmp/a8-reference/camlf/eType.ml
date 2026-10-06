open ETypeConstructors

type syntactic_binding_labels = flexibility_label * expliciteness_label
and flexibility_label = Flex | Rigid
and expliciteness_label = Explicit | Implicit

(** MLF monotypes *)
type mono_var = [`Var of typevar]
type ('a, 'b) sconstr = [`Constr of 'b * 'a list]
type 'a monotype_ = [ mono_var | ('a monotype_, 'a) sconstr ]
type constant_monotype =
    (constant_monotype, init_ct_typeconstr) sconstr

(* We need to split the two abstractions (α≥σ) and (α:κ)
   because, while Λ takes both, λ only accepts kinds. *)
type kind =
  [ `Kind of ETypeKinds.kind ]
type 'a bound =
  [ `Bound of syntactic_binding_labels * 'a ]

type 'a type_abstraction_ =
  typevar * [ kind | 'a bound ]

type 'a bound_abstraction_ =
  typevar * 'a bound
type 'a kind_abstraction_ = 
  typevar * kind

type 'a forall =
  [ `Forall of 'a type_abstraction_ * 'a ]
type 'a abstraction =
  [ `Abstraction of 'a * 'a ]
type 'a lambda =
  [ `Lambda of 'a kind_abstraction_ * 'a ]
type 'a app =
  [ `Apply of 'a * 'a ]

(** The unconstrained, standard MLF types *)

(* polymorphic constructs, independently of monomorphic features *)
type 'a constructs = [
  | `Bottom
  | 'a forall
  | 'a abstraction
  | 'a lambda
  | 'a app
]

type 'a polytype_ = [
  | 'a polytype_ constructs
  | 'a monotype_
] 

(* Polytypes in which the usual monotypes can also be polytypes *)
type 'a expanded_polytype_ = [
  | 'a expanded_polytype_ constructs
  | mono_var
  | ('a expanded_polytype_, 'a) sconstr
]

let rec ftv' : _ expanded_polytype_ -> _ = function
  | `Var v -> TypeVarSet.singleton v
  | `Bottom -> TypeVarSet.empty
  | `Constr (_, ls) ->
      List.fold_left
        (fun s t -> TypeVarSet.union s (ftv' t))
        TypeVarSet.empty ls
  | `Abstraction (a, b)
  | `Apply (a, b) ->
      TypeVarSet.union (ftv' a) (ftv' b)
  | `Forall ((v, `Kind _), ret)
  | `Lambda ((v, `Kind _), ret) ->
      TypeVarSet.remove v (ftv' ret)
  | `Forall ((v, `Bound (_, bound)), ret) ->
      TypeVarSet.union (TypeVarSet.remove v (ftv' ret)) (ftv' bound)

(* All the types variables (included the bound ones) of a type *)
let rec atv : _ expanded_polytype_ -> _ = function
  | `Var v -> TypeVarSet.singleton v
  | `Bottom -> TypeVarSet.empty
  | `Constr (_, ls) ->
      List.fold_left
        (fun s t -> TypeVarSet.union s (atv t))
        TypeVarSet.empty ls
  | `Abstraction (a, b)
  | `Apply (a, b) ->
      TypeVarSet.union (atv a) (atv b)
  | `Forall ((v, `Kind _), ret)
  | `Lambda ((v, `Kind _), ret) ->
      TypeVarSet.add v (atv ret)
  | `Forall ((v, `Bound (_, bound)), ret) ->
      TypeVarSet.add v (TypeVarSet.union (atv ret) (atv bound))

let ftv t = ftv' (t : 'a polytype_ :> 'a expanded_polytype_)

let bound_env env alpha alpha' =
  TypeVarMap.add alpha alpha' env

let alpha_equiv
    ?(constr_equiv : 'a -> 'a -> bool = (=))
    ?(env = TypeVarMap.empty)
    : 'a expanded_polytype_ -> 'a expanded_polytype_ -> bool =
  fun t1 t2 ->
    let rec check env t1 t2 = match (t1 : 'a expanded_polytype_), t2 with
      | `Var v1, `Var v2 ->
          (try TypeVarMap.find v1 env = v2
           with Not_found -> v1 = v2) (* free vars must be equal *)
      | `Var _, _ | _, `Var _ -> false

      | `Bottom, `Bottom -> true
      | `Bottom, _ | _, `Bottom -> false

      | `Constr (c, s), `Constr (c', s') ->
          constr_equiv c c'
          && List.length s = List.length s'
          && not (List.mem false (List.map2 (check env) s s'))
      | `Constr _, _ | _, `Constr _ -> false

      | `Apply (a, b), `Apply (a', b')
      | `Abstraction (a, b), `Abstraction (a', b') ->
        check env a a' && check env b b'
      | `Apply _, _ | _, `Apply _
      | `Abstraction _, _ | _, `Abstraction _ -> false

      | `Forall ((alpha, `Kind k), sigma),
        `Forall ((alpha', `Kind k'), sigma')
      | `Lambda ((alpha, `Kind k), sigma),
        `Lambda ((alpha', `Kind k'), sigma') ->
          k = k' && check (bound_env env alpha alpha') sigma sigma'
      | `Forall ((alpha, `Bound (label, sigma)), tau),
        `Forall ((alpha', `Bound (label', sigma')), tau') ->
          label = label'
          && check env sigma sigma'
          && check (bound_env env alpha alpha') tau tau'
      | `Forall _, _ | _, `Forall _
      | `Lambda _, _ (* | _, `Lambda _ *) -> false
    in
    check env t1 t2

let arrow t1 t2  : [> _ monotype_] = `Constr (`Arrow, [t1 ; t2])
let var v : [> mono_var] = `Var (s_typevar v)

let var_n n =
  assert (n > 0);
  s_typevar (
    if n <= 26 then
      String.make 1 (char_of_int (97-1+n))
    else
      "a" ^ (string_of_int (n-26))
  )


(* Variance informations *)
type variance = Covariant | Contravariant | Invariant

let compatible_variance var lbl =
  (var = Covariant && lbl = Flex) || (var = Contravariant && lbl = Rigid)

let variance_arrow = [Contravariant ; Covariant]
let rec variance_uple = Covariant :: variance_uple
let rec unknown_variance = Invariant :: unknown_variance


(* All bounds collected in a prefix *)
type 'a prefix = 'a bound_abstraction_ list


(* Variables not already present in a type *)
let fresh_var avoid =
  let c = Utils.counter 0 in
  let rec new_var () =
    let s = var_n (c()) in
    if TypeVarSet.mem s avoid then
      new_var ()
    else
      s
  in new_var


module KnownconstrTypes = struct
  type monotype = typeconstr monotype_
  type polytype = typeconstr polytype_
  type expanded_polytype = typeconstr expanded_polytype_
  type type_abstraction = expanded_polytype type_abstraction_
  type bound_abstraction = expanded_polytype bound_abstraction_
end

module UnknownconstrTypes = struct
  type monotype = unresolved_typeconstr monotype_
  type polytype = unresolved_typeconstr polytype_
  type expanded_polytype = unresolved_typeconstr expanded_polytype_
  type type_abstraction = expanded_polytype type_abstraction_
  type bound_abstraction = expanded_polytype bound_abstraction_
end

open KnownconstrTypes

let rec really_monomorphic_monotype : monotype -> bool = function
  | `Var _ -> false
  | `Constr ((#init_ct_typeconstr | `Arrow | `Uple _), l) ->
      (* Builtin types are inductive types, not aliases *)
      List.for_all really_monomorphic_monotype l
  | `Constr (`User c, l) ->
      c.typeconstr_is_poly = false &&
      List.for_all really_monomorphic_monotype l

let rec polymorphic_type : polytype -> bool = function
  | #monotype as t -> not (really_monomorphic_monotype t)
  | #polytype -> true


(* unexpand transform an expanded type into a monotype : in some
   formal presentations of MLF, type constructors may accept only
   variables as parameters. Unexpand transforms (σ → τ) into
   ∀(α=σ).∀(β≥τ). α → β. To choose the correct flexibility, we
   consider the type constructor variance. All added bindings are
   implicit.
*)
let unexpand (t : expanded_polytype) =
  let new_var = fresh_var (atv t) in

  let rec unexpand : expanded_polytype -> polytype = function
    | `Var _ | `Bottom as c -> c
    | `Constr (c, l) -> unexpand_constr c l
    | `Apply (f, x) -> `Apply (unexpand f, unexpand x)
    | `Abstraction (a, b) ->
        `Abstraction (unexpand a, unexpand b)
    | `Forall ((v, `Bound (l, t)), t') ->
        `Forall ((v, `Bound (l, unexpand t)), unexpand t')
    | `Forall ((v, `Kind k), t) ->
        `Forall ((v, `Kind k), unexpand t)
    | `Lambda ((v, `Kind k), t) ->
        `Lambda ((v, `Kind k), unexpand t)
  and unexpand_constr c l =
    let variances = match c with
      | `Arrow -> variance_arrow
      | `Uple _ -> variance_uple
      | _ -> unknown_variance
    in
    let b, m = unexpand_monotype_list variances l in
    rebind (`Constr (c, m)) b
  and unexpand_monotype_list variances l : _ prefix * _ = match l, variances with
    | [], _ -> [], []
    | p :: q, v :: qv ->
        let b, m = unexpand_monotype v p in
        let lb, lm = unexpand_monotype_list qv q in
        b @ lb, m :: lm
    | _ :: _, [] -> assert false
  and unexpand_monotype variance : expanded_polytype -> _ prefix * monotype = function
    | `Var _ as v -> [], v
    | `Constr (c, l) ->
        (match unexpand_constr c l, typeconstr_is_poly c with
           | #monotype_ as m, false -> [], m
           | #polytype_ as p, _ -> poly_to_mono variance p)
    | `Bottom  -> poly_to_mono variance `Bottom
    | (`Forall _ | `Lambda _ | `Apply _ | `Abstraction _) as b ->
        let b' = unexpand b in
        poly_to_mono variance b'
  and poly_to_mono variance poly =
    let v = new_var () in
    let lbl = if variance = Covariant then Flex else Rigid in
    (* added bounds are implicit *)
    [v, `Bound ((lbl, Implicit), poly)], `Var v
  and rebind tau = function
    | [] -> tau
    | bound :: q ->
        rebind (`Forall ((bound :> _ type_abstraction_), tau)) q
  in
  unexpand t
