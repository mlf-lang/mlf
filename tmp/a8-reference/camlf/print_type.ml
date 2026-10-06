open ETypeConstructors
open EType
open GType
open Format

let level_var = 0
let level_constr = 2
let level_uple = 4
let level_arrow = 6
let level_app = 8
let level_all = 10

let print_level : _ expanded_polytype_ -> _ = function
  | `Var _
  | `Bottom -> level_var
  | `Constr (`Arrow, _) -> level_arrow
  | `Constr ((`Int | `Bool | `Unit), _) -> level_var
  | `Constr ((`Uple _ | `User _ | `PConstr _), _) ->
    failwith "unsupported types"
  | `Abstraction _ -> level_var (* fully parenthesed *)
  | `Apply _ -> level_app
  | `Forall _ | `Lambda _ -> level_all

let string_of_fr = function
    | EType.Flex -> Symbol.geq ()
    | EType.Rigid -> Symbol.eq ()
let string_of_ie = function
    | EType.Implicit -> ""
    | EType.Explicit -> "!" 

let string_of_binding_flags (fr, ie) =
  string_of_ie ie ^ string_of_fr fr

let rec print_type ?(verbatim=false) out (t : AST.type_expr) = 
  let rec print out (t : AST.type_expr) =
    match t with
    | `Var v ->
        fprintf out "%s" (typevar_s v)
    | `Bottom ->
        (* should not occur for normalized types *)
        fprintf out "%s" (Symbol.bot ~verbatim ())
    | `Forall ((v, bound), `Abstraction(v', t2)) when `Var v = v' ->
      fprintf out "^%a" print (`Forall ((v, bound), t2))
    | `Forall (abstraction, t2) ->
        fprintf out "%a.@;@[%a@]"
          (print_tyabs ~verbatim) abstraction print t2
    | `Lambda ((v, `Kind k), t) ->
        fprintf out "lam (%s : @[%a@])@;.@;@[%a@]"
          (typevar_s v)
          (ETypeKinds.print_kind ~verbatim) k
          print t
    | `Apply (f, x) -> fprintf out "%a %s %a"
        (print' (level_app + 1)) f
        "@"
        (print' level_app) x
    | `Abstraction (a, b) ->
        fprintf out "A(%a,@[%a@])" print a print b
    | `Constr (const, arg) ->
      let binary = function
        | [t1;t2] -> (t1, t2)
        | _ -> failwith "binary" in
      begin match const with
        | `Arrow ->
          let t1, t2 = binary arg in
          fprintf out "@[%a@] %s@;@[%a@]"
            (print' level_arrow) t1
            (Symbol.arrow ~verbatim ())
            (print' (level_arrow + 1)) t2
        | (`Int | `Unit | `Bool) as unary ->
          assert (arg = []);
          fprintf out "%s"
            (match unary with
              | `Int -> "int"
              | `Unit -> "unit"
              | `Bool -> "bool")
        | `PConstr _ | `Uple _ | `User _ ->
          failwith "unsupported"
      end
  and print' level out t =
    if print_level t >= level then 
      fprintf out "(%a)" print t
    else print out t
  in
  fprintf out "@[%a@]" print t

and print_tyabs ?(verbatim=false) out = function
    | (v, `Bound ((Flex, ie), `Bottom)) ->
        fprintf out "%s%s" (typevar_s v) (string_of_ie ie)
    | (v, `Bound (flags, t1)) ->
        fprintf out "(%s %s @[%a@])"
          (typevar_s v)
          (string_of_binding_flags flags)
          (print_type ~verbatim) t1
    | (v, `Kind K.Star) ->
        fprintf out "%s" (typevar_s v)
    | (v, `Kind k) ->
        fprintf out "(%s : @[%a@])"
          (typevar_s v)
          (ETypeKinds.print_kind ~verbatim) k

(** Build a table of nodes that should have their own quantification,
    mapping them to unique names; non-named nodes will be inlined in
    the type expression. This is done by using the inlining convention
    of constructors, eg. a (→) node will not 'name' its left-child if
    it is flexibly bound.
    
    It accepts as input a set of roots, and will visit all nodes below
    these roots. It only accepts type graphs, not constraint graphs:
    the roots must not be (G) nodes.
*)
let name_nodes roots =
  assert (List.for_all (fun t -> not (gen_node t)) roots);
  let table = Table.create 10 in
  let namer = Utils.namer() in
  let name t =
    if not (Table.mem table t)
    then Table.add table t (s_typevar (namer (id t))) in

  let seen t =
    if not (inert t) then name t in

  let unseen visit t =
    let t = U.repr t in

    (* if the flag is as requested, inline, otherwise name *)
    let request fl t' =
      if inert t'
         || (fl = fst (flags t') && eqrepr (bound t') t)
      then ()
      else name t' in
    begin
      (** Default is inlining. We cancel it when needed *)
      List.iter visit (edges t);
      match (node t).constr, edges t with
        | Bot _, [] ->
          name t
        | Gen _, _ -> 
          assert false (* should not occur *)
        | Arrow, [ t1; t2 ] ->
          request Rigid t1;
          request Flexible t2
        | Apply (_, _), [ t1; t2 ] ->
          request Rigid t1;
          request Rigid t2
        | Lambda (_, _), [t1; _] ->
          name t1
        | Forall _, [ t1; _ ] ->
          (* we have to make a test because the Forall might have been
             applied away *)
          if eqrepr (bound t1) t then name t1
        | Constant (Int | Unit | Bool), [] -> ()
        | Constant _, _ -> assert false
        | _, _ ->
          assert false (* not implemented *)
    end in
  List.iter (dps ~seen unseen) roots;

  fun t -> Table.find_option table t
;;

let compute_inv_bind_edges t0 =
  let table = Table.create 10 in
  let add_inv t =
    if not (undef_binder t) then
      Table.add_elem table (bound t) t in
  top_down ~status:(fresh_status()) add_inv t0;
  (* reverse the lists to get the right order *)
  Table.iter (fun n li -> Table.replace table n (List.rev li)) table;
  table

module TypeVarMap = ETypeConstructors.TypeVarMap
type context = free_var_bound TypeVarMap.t
and free_var_bound =
    (* bool : is the node instantiable? *)
    AST.type_expr EType.bound * bool

(* Compute a type expression for a node, returning all subexpressions
   for each node in the subgraph structurally under it. This will
   allow for fine error message where subparts of a type can easily be
   displayed in isolation.

   Note that the subexpressions returned are relative to the printing
   of the main node. For example, if the global expression begines
   with ∀(α≥σ)..., then asking for the subexpression corresponding to
   the node representing σ will just output 'α', as the subexpression
   is named. Only inlined nodes will have their structure returned.
   
   The type expressions generated may be in a open context, that is
   use free variables corresponding to named nodes bound outside the
   subgraph. We need to return those free variables, so that
   additional information can be displayed about their binding
   context. *)
let open_type_expr name t0 : context * AST.type_expr Table.t =
  (* as explained, we return expressions relative to their inlining
     status and name in the global expression. We therefore use two
     tables:     
     - transparent_exprs : always the full type structure (σ in the
     example)
     - opaque_exprs : the structure for the inlined nodes, the name
     otherwise (α)

     In the end we will only return opaque_exprs, but
     transparent_exprs is useful for internal processing.
  *)
  let transparent_exprs = Table.create 10 in
  let opaque_exprs = Table.create 10 in

  (* free variables *)
  let free_vars = ref TypeVarMap.empty in

  (* build the ∀ bound for a given binding edge, unless it's inlined *)
  let bound_expr binding s = match name binding with
    | None -> s
    | Some var ->
      let bound =
        match kind binding with
          | K.Star -> 
            let flags =
              syntactic_binding_of_graphic_binding (flags binding) in
            let bound = Table.find transparent_exprs binding in
            `Bound (flags, bound)
          | higher_kind ->
            assert (bot_node binding);
            `Kind higher_kind in
      `Forall ((var, bound), s) in

  (* build all the bindings of a node, using a reverse binding edges
     table; returns a function that, when passed a type expression,
     add the bindings on top of it *)
  let inv_bind_edges = compute_inv_bind_edges t0 in
  let all_bounds t =
    let all binding s =
      match constr t with
        (* (λ)-var bindings must be handled specifically as their
           explicitely bound node shouldn't trigger a ∀ quantifier
           output *)
        | Lambda (k, _) when eqrepr binding (fst (below_lambda t)) ->
          let alpha = match name binding with
            | None -> 
              (* (λ)-var nodes are always named *)
              assert false 
            | Some var -> var in
          `Lambda ((alpha, `Kind k), s)
        | _ -> 
          bound_expr binding s in
    let inv_edges = Table.find_list inv_bind_edges t in
    let bindings = List.rev (List.sort compare_blevel inv_edges) in
    fun expr ->
      List.fold_right all bindings expr
  in

  (* build the structural part of the type expression for a given node,
     assuming the expressions for lower nodes are already built. *)
  let structure_expr t =
    match constr t, List.map (Table.find opaque_exprs) (edges t) with
      (* arity 2 *)
      | Arrow, [e1; e2] ->
        `Constr (`Arrow, [e1; e2])
      | Forall _, [e1; e2] ->
        `Abstraction (e1, e2)
      | Apply (_, _), [e1; e2] ->
        `Apply (e1, e2)
      | Lambda (_, _), [_; e2] ->
        (* lambdas are skipped as they were handled in the
           bindings part *)
        e2
      | (Forall _ | Lambda (_, _ ) | Arrow | Apply (_, _)), _ ->
        failwith "arity error (expected 2)"

      (* arity 0 *)
      | Bot _, [] -> `Bottom
      | Constant Int, [] -> `Constr (`Int, [])
      | Constant Unit, [] -> `Constr (`Unit, [])
      | Constant Bool, [] -> `Constr (`Bool, [])
      | (Bot _ | Constant (Int | Unit | Bool)), (_::_) ->
        failwith "arity error (expected 0)"

      (* impossible case : no (G) node inside type graphs *)
      | Gen (_, _), _ ->
        assert false
  in

  (* add a given free variable to the context *)
  let inline t = (name t = None) in
  let add_free_variable t =
    match binder t with
      | Root | Undef ->
        assert (inline t)
      | Bound (flags, _ancestor_node) ->
        let labels = syntactic_binding_of_graphic_binding flags in
        let expr = Table.find transparent_exprs t in
        let abstraction = `Bound (labels, expr) in
        match name t with
          | None -> ()
          | Some alpha ->
            if not (TypeVarMap.mem alpha !free_vars) then
              free_vars :=
                TypeVarMap.add alpha (abstraction, instantiable t) !free_vars
  in

  (* compute the table bottom-up, adding free variables as we go *)
  let () =
    let interior = in_interior t0 in
    let make_type_expr t =
      let structure = structure_expr t in
      let bindings = all_bounds t in
      let expr = bindings structure in
      Table.add transparent_exprs t expr;
      let opaque_expr = match name t with
        | None -> expr
        | Some v -> `Var v in
      Table.add opaque_exprs t opaque_expr;
      if not (interior t) then
        add_free_variable t;
    in
    GType.dps
      ~status:(GType.fresh_status())
      ~acyclic:false
      (fun visit t ->
        List.iter visit (edges t);
        make_type_expr t)
      t0
  in
  
  !free_vars, opaque_exprs
;;

let closed_type_expr t0 =
  let name = name_nodes [t0] in
  let free_vars, type_exprs = open_type_expr name t0 in
  if not (TypeVarMap.is_empty free_vars) then
    failwith "closed_type_expr was given a non-closed subgraph";
  match name t0 with
    | None -> Table.find type_exprs t0
    | Some v -> `Var v

(** [inline root t] is true iff the subtype corresponding to [t] is
    inlined in the representation of the subtype correpsonding to
    [root]. *)
let inline toplevel =
  let name = name_nodes [toplevel] in
  let inline t =
    let t = U.repr t in name t = None in
  inline

let print_type_expr ?name ppf tg =
  begin match name with
    | None -> ()
    | Some v ->
      Format.fprintf ppf "val %s : " (AST.value_s v)
  end;
  print_type ppf (closed_type_expr tg);
  Format.pp_print_newline ppf ()
