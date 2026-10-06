open ETypeConstructors
open EType
open Format

let string_of_fr = function
    | EType.Flex -> ">"
    | EType.Rigid -> "="
let string_of_ie = function
    | EType.Implicit -> ""
    | EType.Explicit -> "!" 

let string_of_binding_flags (fr, ie) =
  string_of_ie ie ^ string_of_fr fr

let print_binding_flags ppf flags =
  fprintf ppf "%s" (string_of_binding_flags flags)

let level_var = 0
let level_constr = 2
let level_uple = 4
let level_apply = 6
let level_arrow = 8
let level_poly = 10

let level : _ expanded_polytype_ -> int = function
  | `Var _ | `Bottom -> level_var
  | `Constr (`Arrow, _) -> level_arrow
  | `Constr (`Uple _, _) -> level_uple
  | `Abstraction _ -> level_var
  | `Apply _ -> level_apply
  | `Constr _ -> level_constr
  | `Forall _ | `Lambda _ -> level_poly

let sides : _ expanded_polytype_ -> (bool * bool) = function
  | `Var _ | `Bottom | `Abstraction _ -> (false, false)
  | `Constr ((`Arrow | `Uple _), _) -> (true, true)
  | `Apply _ -> true, true
  | `Constr _ -> false, true
  | `Forall _ | `Lambda _ -> (false, true)

let print_tvar ppf v =
  let v = typevar_s v in
  assert (String.length v > 0);
  if v.[0] = '#' then (* Nameless variable, created at parsing type *)
    fprintf ppf "_"
  else
    fprintf ppf "'%s" v

let rec print_type ppf : _ expanded_polytype_ -> _ = function
  | `Var v -> print_tvar ppf v

  | `Constr (`Uple n, l) ->
      assert (n >= 2);
      Utils.print_list (print_type' `Closed) " * " ppf l

  | `Constr (`Arrow, [t1;t2]) ->
      fprintf ppf "%a %s %a"
        (print_type' (`Left level_arrow)) t1
        (string_of_typeconstr `Arrow)
        (print_type' (`Right (level_arrow + 1))) t2

  | `Constr (`Arrow, _) -> assert false

  | `Constr (c, []) ->
      fprintf ppf "%s" (string_of_typeconstr c)

  | `Constr (c, [t]) ->
    let par = if !Options.minimize_parentheses  then 1 else 0 in
      fprintf ppf "%a %s"
        (print_type' (`Left (level_constr + par))) t
        (string_of_typeconstr c)

  | `Constr (c, l) ->
      fprintf ppf "(%a) %s"
        (Utils.print_list (print_type' `Closed) ", ") l
        (string_of_typeconstr c)

  | `Bottom -> fprintf ppf "_"

  | `Abstraction (a, b) ->
      let print x = print_type' `Closed x in
      fprintf ppf "A(%a, %a)" print a print b

  | `Apply (f, x) -> fprintf ppf
      "%a %s %a"
      (print_type' (`Left (level_apply + 1))) f
      "@"
      (print_type' (`Right level_apply)) x

  | `Forall (bound, t) ->
      fprintf ppf "%a. %a"
        print_tyabs bound
        (print_type' (`Right level_poly)) t
  | `Lambda (bound, t) ->
      fprintf ppf "lam %a . %a"
        print_tyabs (bound :> _ EType.type_abstraction_)
        (print_type' (`Right level_poly)) t

and print_type' lvl ppf t =
  let left, right = sides t in
  let protect = fprintf ppf "(%a)" print_type in
  let bare = fprintf ppf "%a" print_type in
  match lvl with
    | `Left lvl ->
      (if level t >= lvl && right then protect else bare) t
    | `Right lvl ->
      (if level t >= lvl && left then protect else bare) t
    | `Closed -> bare t

and print_tyabs ppf : _ type_abstraction_ -> _ = function
  | (v, `Bound ((Flex, ie), `Bottom)) ->
      fprintf ppf "%a%s" print_tvar v (string_of_ie ie)
  | (v, `Bound (flags, t)) ->
    fprintf ppf "(%a %a %a)"
        print_tvar v
        print_binding_flags flags
        print_type t
  | (v, `Kind ETypeKinds.Star) ->
    print_tvar ppf v
  | (v, `Kind k) ->
      fprintf ppf "(%a : %a)"
        print_tvar v
        (ETypeKinds.print_kind ~verbatim:true) k

(* Split a polytype into a prefix and the type at the end *)
let rec split : _ polytype_ -> _ prefix * _ = function
  | `Forall ((_, #bound) as abs, t) ->
      let bounds, t = split t in
      abs :: bounds, t
  | t -> [], t

(* Find a variable in a prefix. Return the bound, the remainder of
   the prefix (without the bound) and the prefix after *)
let rec split_q v : _ prefix -> _ = function
  | [] -> raise Not_found
  | (v', `Bound (l, t)) as abs :: q ->
      if v = v' then
        (l, t), q, q
      else
        let b', q', qa = split_q v q in
        b', abs :: q', qa

(* Does a type variable occur in a polytype ? We check for the case of
   the variable being (re)bound inside the type *)
let rec occur var : _ polytype_ -> bool = function
  | `Var var' -> var = var'
  | `Bottom -> false
  | `Constr (_, ls) -> List.exists (occur var) (ls :> _ polytype_ list)
  | `Abstraction (a, b) | `Apply (a, b) ->
      occur var a || occur var b
  | `Forall ((var', `Kind _), s) | `Lambda ((var', `Kind _), s) ->
      var <> var' && occur var s
  | `Forall ((var', `Bound (_, bound)), s) ->
      occur var bound || (var <> var' && occur var s)

(* Nb of occurrences of a variable into a monotype *)
let rec nb_occur v : _ monotype_ -> int = function
  | `Var v' -> if v = v' then 1 else 0
  | `Constr (_, l) -> List.fold_left (fun c t -> c + nb_occur v t) 0 l


(* Inline the variables into the arguments of a constructor, provided
   the variance information are respected. The variable is inlined
   if it occurs exactly once in the prefix and the arguments of the
   constructor. Note that we suppose that the variable does not appear
   more than once in the prefix. The variance argument can be longer
   than the constructor arguments (we use this as a small optmization
   using infinite recursive lists). Bottom nodes are not inline, in
   order to avoid difficult to read types such as _|_ -> _|_
*)
let rec inline_list q (l : 'a monotype_ list) variance =
  let (>::) e (l, q) = (e :: l, q) in
  let rec aux q = function
    | [], _ -> [], q
    | (t :: tl), (var :: qvar) ->
        let default = ref ((t :> _ polytype_) , q) in
        (match t with
           | `Var v ->
               (try
                  let (lbl, t), q', qa = split_q v q in
                  if t <> `Bottom &&
                    compatible_variance var (fst lbl) &&
                    List.for_all (fun (_, `Bound (_, t)) -> occur v t = false) qa &&
                    List.fold_left (fun c t -> c + nb_occur v t) 0 l = 1
                  then
                    default := (t, q')
                with Not_found -> ())
           | `Constr _ -> ()
        );
        let t, q = !default in
        t >:: aux q (tl, qvar)
    | _, [] -> assert false
  in aux q (l, variance)


(* Expansion of polytypes inside the monotypes part. We first
   collect all the relevant bounds and expand them *)
let rec inline : _ polytype_ -> _ expanded_polytype_ = function
  | `Bottom | `Var _ | `Constr (_, _) as t ->
      (t : _ polytype_ :> _ expanded_polytype_)
  | `Lambda (abs, t) ->
      `Lambda (abs, inline t)
  | `Apply (f, x) -> `Apply (inline f, inline x)
  | `Abstraction (a, b) -> `Abstraction (inline a, inline b)
  | `Forall _ as t ->
      let bounds, t = split t in
      (* let bounds = List.stable_sort sort_prefix_aux bounds in

        (* Dead code : I suspect that this sort_prefix_aux was just
           a cosmetic reordering of the prefix to place explicit bounds
           before rigid bounds when possible. The code was very partial
           (it only considered the (≥⊥) and (=⊥) cases to avoid
           variables dependencies) and totally hackish (sort_prefix_aux
           was only a preorder), so I choose to disable it instead of
           extending it to Implicit/Explicit handling. *)
      *)
      inline_aux bounds t

(* Inline polytypes into constructors specifically. This function
   should not be called on bot or a variable if the types are normalized *)
and inline_aux q : _ -> _ expanded_polytype_ = function
  | `Bottom | `Var _ | `Forall _ -> assert false
  | `Constr (`Arrow, l) ->
      inline_in_constr `Arrow q l variance_arrow
  | `Constr (`Uple n, l) ->
      inline_in_constr (`Uple n) q l variance_uple
  | `Constr (c, l) ->
      inline_in_constr c q l unknown_variance
  | `Lambda (abs, t) ->
      rebind (`Lambda (abs, inline t)) q
  | `Apply (f, x) -> 
      rebind (`Apply (inline f, inline x)) q
  | `Abstraction (a, b) ->
    rebind (`Abstraction (inline a, inline b)) q

(* Auxiliary function for inline in constructors *)
and inline_in_constr (c : 'a) (q : 'a polytype_ prefix) l variance =
  let l', q' = inline_list q l variance in
  let t = `Constr (c, List.map inline l') in
  rebind t q'

(* Rebinding of the variables of the prefix that have not been inlined *)
and rebind (t : _ expanded_polytype_) q =
  let rec aux t = function
    | [] -> t
    | (v, `Bound (l, tb)) :: q ->
        let t' = `Forall ((v, `Bound (l, inline tb)), t) in
        aux t' q
  in aux t (List.rev q)


module Env =
  Map.Make (struct type t = typevar let compare = compare end);;

let alpha_convert t =
  let new_var = fresh_var (ftv' t) in
  let rec convert env : _ expanded_polytype_ -> _ expanded_polytype_ =
    function
    | `Bottom -> `Bottom
    | `Var v -> `Var (try Env.find v env with Not_found -> v)
    | `Constr (c, l) -> `Constr (c, List.map (convert env) l)
    | `Apply (f, x) -> `Apply (convert env f, convert env x)
    | `Abstraction (a, b) -> `Abstraction (convert env a, convert env b)
    | `Forall ((v, `Kind k), t) ->
        let v' = new_var () in
        `Forall ((v, `Kind k), convert (Env.add v v' env) t)
    | `Lambda ((v, `Kind k), t) ->
        let v' = new_var () in
        `Lambda ((v, `Kind k), convert (Env.add v v' env) t)
    | `Forall ((v, `Bound (l, tb)), t) ->
        let v' = new_var () in
        `Forall ((v', `Bound (l, convert env tb)), convert (Env.add v v' env) t)
  in
  convert Env.empty t


let print_polytype_aux alpha ppf t =
  let t = if !Options.inline_types then
    inline t (* Printing of types after expansion *)
  else
    (t : _ polytype_ :> _ expanded_polytype_) (* Non-inlined printing of types *)
  in
  let t = if alpha then alpha_convert t else t in
  print_type ppf t

let print_polytype ppf = print_polytype_aux true ppf
let print_polytype_no_alpha ppf = print_polytype_aux false ppf
