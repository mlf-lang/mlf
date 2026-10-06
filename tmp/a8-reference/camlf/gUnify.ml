(** Unification on types and graphic types *)

open GType

module U = Union_find;;

module TypeVarMap = ETypeConstructors.TypeVarMap

module Errors = struct
  type meaning = { 
    meaning : GMeaning.constraint_meaning;
    context : Print_type.context;
    name : gtype -> TypeVarMap.key option;
    type_exprs : AST.type_expr NodeTable.t;
    ta : gtype * ginfo;
    tb : gtype * ginfo;
  }

  let print_context ppf context =
    Format.fprintf ppf "In context:\n%!";
    TypeVarMap.iter
      (fun alpha (`Bound (flags, expr), inst) ->
        Format.fprintf ppf "  %c%a"
          (if inst then '+' else '-')
          (Print_type.print_tyabs ?verbatim:None) (alpha, `Bound (flags, expr));
        Format.fprintf ppf "\n")
      context;
    Format.fprintf ppf "%!"

  let report_meaning_in_context ppf = function
    | Some m ->
      GMeaning.print_meaning ppf m.meaning;
      let print = Print_type.print_type ?verbatim:None in
      if not (TypeVarMap.is_empty m.context) then
        print_context ppf m.context;
      Format.fprintf ppf "Unification error between:\n%!  ";
      print ppf (NodeTable.find m.type_exprs (snd m.ta));
      Format.fprintf ppf "\n%!";
      Format.fprintf ppf "and:\n%!  ";
      print ppf (NodeTable.find m.type_exprs (snd m.tb));
      Format.fprintf ppf "\n%!";
    | None -> ()

  type error = 
    | Flag
    | Cycle of gtype
    | Grafted
    | Cobound of gtype
    | Bound of gtype * gtype
    | Unify of gtype
    | Kind of gtype * K.kind * K.kind

  type unif_error = meaning option * error * gtype
  exception UnifError of unif_error

  let unif_error meaning exn g = raise (UnifError (meaning, exn, g))

  let print_unif_error type_exprs ppf (err, t) =
    let print ppf t =
      match type_exprs with
        | None ->
          (* fall back to graph printing *)
          let buf = Buffer.create 100 in
          GPrint.print_gtype ~acyclic:false buf t;
          Format.fprintf ppf "%s%!" (Buffer.contents buf)
        | Some table ->
          if not (NodeTable.mem table (U.info t)) then
            Format.fprintf ppf "<undefined>"
          else
            Print_type.print_type ppf (NodeTable.find table (U.info t)) in
    begin match err with
    | Cycle t' -> 
      Format.fprintf ppf "Unification would produce a cycle on %a."
        print t'
    | Unify t' -> 
      Format.fprintf ppf "Structural conflict between %a and %a."
        print t print t'
    | Kind (t', k, k') ->
      let print_kind = K.print_kind ~verbatim:true in
      Format.fprintf ppf "Kinding conflict between %a : %a and %a : %a."
        print t print_kind k print t' print_kind k'
    | Flag ->
      Format.fprintf ppf "Node %a cannot be weakened."
        print t
    | Grafted ->
      Format.fprintf ppf "Node %a cannot be grafted."
        print t
    | Cobound t' ->
      Format.fprintf ppf "Nodes %a and %a are cobound and cannot merge."
        print t print t'
    | Bound (t_prev, t_new) -> 
      Format.fprintf ppf "The bound of %a cannot be raised from %a to %a."
        print t print t_prev print t_new
    end;
    Format.fprintf ppf "\n%!"

  let report_unif_error ppf (meaning, exn, g) =
    report_meaning_in_context ppf meaning;
    let type_exprs = match meaning with
      | None -> None
      | Some m -> Some m.type_exprs in
    print_unif_error type_exprs ppf (exn, g);

end
open Errors

let expect_same_kind meaning t1 t2 =
  if kind t1 <> kind t2 then begin
    if !Debug.unification_error then begin
      let name_suffix =
        Printf.sprintf "check-kinds-%d-%d" (id t1) (id t2) in
      Dot.drum ~ids:true ~proj:false ~name_suffix
        ~other_roots:[t1;t2] (find_root t1)
    end;
    ignore (unif_error meaning (Kind (t1, kind t2, kind t1)) t2)
  end

let check_acyclic meaning t =
  try top_down  (fun _t -> ()) t
  with GType.Cycle t1 ->
    if !Debug.unification_error then begin
      let name_suffix = Printf.sprintf "check-acyclic-%d" (id t) in
      Dot.drum ~ids:true ~proj:false ~name_suffix (find_root t)
    end;
    unif_error meaning (Cycle t1) t

(* First order unification, ignoring the binding structure *)
(*
  A note on higher-kinded constructs.

  With the present implementation of unification, no check is made
  that we're not in presence of higher-kinded constructs. This may
  seem strange, as (@)-nodes don't have first-order structure : it is
  wrong to assume, in the general case, that unification of
    @(σ₁,σ₂)~@(τ₁, τ₂)
  is done by unifying σ₁~τ₁ and σ₂~τ₂

  This is correct in this function because we assume we ran a first
  reduction pass, `pre_unification_reductions`, wich made sure that
  all the term we'll encounter during unification are in weak head
  normal form.
  
  Whnf reduction will erase all redexes : @((λ), σ)
  The remaining (@) nodes are :
  - @(F, σ), where F is a variable (⊥)

    unifying @(F, σ) and @(G, τ) is correct iff F=G, and we must then
    unify σ~τ. The first-order behavior of unify_structure will unify
    F~G and σ~t, instead of checking F and G for equality, but this is
    equivalent : higher-kinded variables can only be introduced by
    explicit quantifications, and are therefore explicitely bounded :
    the only permitted unification is no-op on equal nodes.

  - @((@), τ) were the inner (@) is itself in whnf.
    We recursively unify children.
*)
let rec unify_structure meaning t1 t2 =
  if U.equivalent t1 t2 then () else
  begin
    expect_same_kind meaning t1 t2;
    match constr t1, constr t2 with
    | c1, c2 when eq_reg_constr c1 c2 ->
        let e1 = edges t1 in let e2 = edges t2 in
        merge t1 t2;
        List.iter2 (unify_structure meaning) e1 e2
          (* beware ! swapping the order of this clause with the Bot
             clauses created subtle bugs in xTest (xmlf
             translation). Apparently, it is important to use "merge"
             instead of an arbitrary subst in the "both Bot" case. *)

    | Bot k, c ->
        assert (kind_of_constr c = k);
        subst_by t1 t2
    | _, Bot _ -> unify_structure meaning t2 t1 
          
    | _, _ ->
        if !Debug.unification_error then begin
          let name_suffix = Printf.sprintf "unify-%d-%d" (id t1) (id t2) in
          Dot.drum ~ids:true ~proj:false ~name_suffix (find_root t1)
        end;
        let _ = unif_error meaning (Unify t1) t2 in ()
  end

(* Why pre_unification ? See comment in gunify use site *)
let pre_unification_reductions meaning t1 t2 =
  let rec explore t1 t2 =
    GReduce.reduce_whnf t1;
    GReduce.reduce_whnf t2;
    expect_same_kind meaning t1 t2;
    match constr t1, constr t2 with
    | c1, c2 when eq_reg_constr c1 c2 ->
        let e1 = edges t1 in let e2 = edges t2 in
        List.iter2 explore e1 e2

    | Bot _, _ | _, Bot _ -> ()

    | _, _ ->
        if !Debug.unification_error then begin
          let name_suffix = Printf.sprintf "preunify-%d-%d" (id t1) (id t2) in
          Dot.drum ~ids:true ~proj:false ~name_suffix ~other_roots:[t1; t2] (find_root t1)
        end;
        ignore (unif_error meaning (Unify t1) t2) in
  explore t1 t2

let grafted g =
  let is_bot = function Bot _ -> true | _ -> false in
  is_bot (U.info g).node.constr
  && not (is_bot (U.find g).node.constr);;

let below_nodes roots =
  let nodes = ref [] in
  begin
    try
      List.iter 
        (bottom_up
           ~force_reentrant:true
           ?status:None
           ?interior:None
           ~acyclic:true
           ~exist:false
           (fun t -> nodes := t :: !nodes))
        roots
    with GType.Cycle t ->
      unif_error None (Errors.Cycle t) t
  end;
  !nodes

let gprint = GPrint.print_gtype ~namer:(Utils.namer());;


let gunify ?meaning ?(unsafe=false) t1 t2 =
  (* We assume that nodes are not both the root *)
  (* We assume that binding levels are correct and should leave them
     correct *)
  (* We assume nothing on and erase equiv and invedges fields below t1
     and t2 *)

  (* If the 'unsafe' flag is true, the validity of the rebinding
     process is not checked; this is useful when gunify is used in
     GInstance to replay atomic instance steps, that may locally break
     rebinding validity *)

  (* Printf.fprintf stdout "\n ==> %a and %a\n%!" gprint t1 gprint t2; (*#*) *)

  assert (non_root t1);
  assert (non_root t2);

  (* ERRORS: at that point, nothing has changed; precompute any useful
     data *)
  let meaning_in_context = match meaning with
    | None -> None
    | Some meaning ->
      let name = Print_type.name_nodes [t1; t2] in
      let free_a, table_a = Print_type.open_type_expr name t1 in
      let free_b, table_b = Print_type.open_type_expr name t2 in
      let free_vars =
        TypeVarMap.fold (fun alpha context free_vars ->
          if TypeVarMap.mem alpha free_vars then
            assert (TypeVarMap.find alpha free_vars = context);
          TypeVarMap.add alpha context free_vars) free_a free_b in
      let table, remaining = table_a, table_b in
      let () =
        Table.iter (fun t expr ->
          if Table.mem table t then
            assert (Table.find table t = expr);
          Table.add table t expr)
          remaining in
      Some {
        meaning = meaning;
        context = free_vars;
        name = name;
        type_exprs =
          (* see comments below for the use of a NodeTable here *)
          nodetable_of_table table;
        ta = t1, U.find t1;
        tb = t2, U.find t2;
      } in

  (* UNION_FIND: The vicious union_find use, explained :

     The unification algorithm is explained in two steps : first, the
     graph structure is unified as usual, then the binding structure
     is unified (Rebind phase). The rebinding process, and the
     correctness conditions, are expressed in terms of both the new
     graph (after node and edges unification) and the old graph
     (before unification).

     Node unification uses an Union-Find structure to perform
     fast. There is thus one level of indirection : the node content
     of a gtype is accessed with U.find. U.find actually returns the
     representative element of the equivalence class (under the
     union-find relation) of the node.

     That unification structure is exploited to provide simultaneous
     access to both the new and the old graph structure. See the
     'sync' and 'equiv' comments below.  *)

  (* before union-find subtleties, we pre-iterate on the unification
     structure to find the application nodes, wich we β-reduce before
     unification.

     It is important to do that before union-find synchronization
     because the β-reduction routine use unification itself, so may
     mess the union-find information (reentrancy issue). *)
  (* ERRORS: any error here is _not_ related to the unification, but
     is an error in the reduction process which is indepentent and
     should be reported separately.
     
     The β-reduction process is supposed to be atomic and safe. In
     particular, it should not raise any error. The current code
     contains kind checks and may fail for incorrect kinding, but
     I suppose those could have been performed earlier (TODO). *)
  pre_unification_reductions meaning_in_context t1 t2;

  (* We collect nodes below the unification points and set *)
  let origin = List.map U.repr (below_nodes [t1; t2]) in

  (* We compute non-inert nodes (useful for post-unification permission
     checks).  As we will compute node properties at the `ginfo` level
     (behind the union-find abstraction) during unification, we
     convert it to a NodeTable. *)
  let exposed_nodes = nodetable_of_table (exposed_table_under_nodes [t1; t2]) in

  (* UNION_FIND: Before any unification, we 'synchronize' the nodes, ensuring that
     each node content is exactly its class representative under the
     union-find equivalence *)
  List.iter (* We sync info fields *)
    (fun t ->
       check_node_invariants (U.find t);
       (* We sync t to read back the bound of t *)
       U.sync t;
       (* We sync the bound of t to recognize originally cobound nodes *)
       U.sync (bound t))
    (t1 :: t2 :: origin);

  (* we save a printable dot view of the current graph, to be used for
     error reporting *)
  let print_snapshot =
    Dot.printable_snapshot ~name:"unification"
      ~other_roots:[t1; t2] (find_root t1) in


  (* UNION_FIND: We compute the unifier of the node-edges structure, ignoring
     bindings and flags.
     This will under the hood call the unification operation on the
     Union-Find structure. *)
  (* ERRORS: before first-order unification, the only types available
     are the pre-unification types; in particular any error occuring
     there (constructor conflict or cycle introduction) will be
     explained in terms of the pre-unification types. *)
  unify_structure meaning_in_context t1 t2;
  check_acyclic meaning_in_context t1;
  (* ERRORS: after first-order unification and cycle checking, the
     graph has a well-formed first-order structure (no cycles). It is
     the first-order unifier of the two input graphs. The binding
     arrows may however be ill-formed, or have changed in a way
     forbidden by the rebinding algorithm. The later passes will
     reconstruct the binding arrows and fail if a binding permission
     was broken.
     
     In further error messages, we may therefore include structural
     information from the first-order unifier. As the first-order
     unification process only unified nodes, there are no "fresh
     nodes" in the unified graph and, in particular, all (⊥) nodes
     comes from existing (⊥) nodes of the two input types. It will
     therefore be possible to print the graph structure reusing, for
     (⊥) nodes, the same variable names used for printing the
     pre-unification types.

     We still need a specific printing function to print a first-order
     unifier. *)

  (* UNION_FIND: The effect of that synchronisation is that after we unified the
     node-edge structure, we have the interesting property that the
     union-find equivalence classes are exactly the equivalence class
     of the node-edge unification : for two nodes `a` and `b`, we have
     `eqrepr (U.find a) (U.find b)` if and only if `a` and `b` were
     merged by the unification process. *)
  let equiv = NodeTable.create 10 in
  List.iter (fun t -> NodeTable.add_elem equiv (U.find t) t) origin;

  (* UNION_FIND: We are also sure that if, instead of U.find, one used
     U.info (wich returns the actual node instead of the
     representative element of the node equivalence class), he would
     access the "old node" with the old binding flag information,
     etc. Hence the "previous_..." auxiliary functions, wich are the
     only place outside union_find.ml we use the .info field. *)
  let previous_node s = U.info s in
  let previous_id t = (previous_node t).id in
  let previous_binder s =
    match (previous_node s).bound with
      | GType.Bound(flag, t) -> (flag, t)
      | _ -> assert false in
  let previous_flag s = fst (previous_binder s) in
  let previous_bound s = snd (previous_binder s) in
  let previously_instantiable s =
    let (flags, t) = previous_binder s in
    instantiable_binding flags && (U.info t).instantiable in

  (* we compute mixed inverse edges, where <-- edges are taken from
     the original and --o edges from the actual, but only for visited
     nodes [CHECK] *)
  let invedges = NodeTable.create 10 in
  bottom_up
    (fun t ->
      let add_edge_from_t t' = NodeTable.add_elem invedges (U.find t') t in
      let u = U.find t in
      List.iter add_edge_from_t (edges t);
      let equiv_u = NodeTable.find_list equiv u in
      NodeTable.add invedges u (List.map previous_bound equiv_u))
    t1 (* t2 is equivalent to t1*);

  (* We adjust and check permissions in a top down visit *)
  top_down
    (fun t ->
       let u = U.find t in
       let equiv_u = NodeTable.find_list equiv u in
       (* we compute the min of flags in the original *)
       let new_flags =
         List.fold_left
           (fun flags u -> weaker_flags flags (previous_flag u))
           min_flags equiv_u in
       (* we compute the bound as the lcb in the target of the unions
          of nodes equivalent to bounds of originals nodes and
          inversed edges;
          some old inverse edges may not be followed [CHECK] *)
       let new_bound =
         let invedges_u = NodeTable.find_list invedges u in
         List.fold_left lcb (bound t) invedges_u in

       (* Two cobound locked node must not be merged.  We use a local
          incompatibility set on each locked father (bound node) bound
          to check unicity *)
       let father_of_locked = NodeTable.create 10 in

       List.iter
         (fun s ->
            (* "Fail if either one of the conditions hold : " *)
            if not unsafe then begin
              (* exposed means 'not inert' *)
              let was_exposed =
                NodeTable.mem exposed_nodes (previous_node s) in
              let was_locked =
                was_exposed
                && GType.instantiable_binding (previous_flag s)
                && not (previously_instantiable s) in
              let was_frozen =
                was_exposed && frozen_bound (previous_node s).bound in

              let check_graft = not (previously_instantiable s) in
              let check_raise = was_locked || was_frozen in
              let check_weaken = was_locked || was_frozen in
              let check_cobound = was_locked in

              let prefix = Printf.sprintf "unify-%d-%d"
                  (previous_id t1) (previous_id t2) in

	      begin
                if check_graft && grafted s then begin
                  (* non instantiable nodes cannot be grafted : "there
                     exists a non-green bottom node m of τ such that
                     g(m)≠⊥" *)
                  if !Debug.unification_error then begin
                    let name_suffix =
                     Printf.sprintf "%s_before_raise_Grafted-%d"
                       prefix (id s) in
                     print_snapshot ~name_suffix ();
                  end;
                  (* Why that useless "let _ = .. in ()" pattern ?
                     We break tail-calls to get better backtraces *)
                  let _ = unif_error meaning_in_context Grafted s in ()
                end;

                if check_raise
                  && not (eqrepr new_bound (previous_bound s)) then begin
                    (* changed bounds : "there exists m in red such that
                       old_bound(m) is different from new_bound(m)" *)
                  if !Debug.unification_error then begin
                    let name_suffix =
                      Printf.sprintf "%s_before_raise_Bound-new_%d-raise_from_%d-to_%d"
                       prefix (id s)
                       (id (previous_bound s)) (id new_bound) in                       
                     print_snapshot ~name_suffix ();
                  end;
                  let bound = (Bound (previous_bound s, new_bound)) in
                  let _ = unif_error meaning_in_context bound s in ()
                end;

                if check_weaken
                  && not (new_flags = previous_flag s) then begin
                    (* changed flags : "there exists m in red such that
                       old_flag(m) is different from new_flag(m)"*)
                  if !Debug.unification_error then begin
                    let name_suffix =
                      Printf.sprintf "%s_before_raise_Flag-%d" prefix (id s) in
                    print_snapshot ~name_suffix ();
                  end;
                  let _ = unif_error meaning_in_context Flag s in ()
                end;

                if check_cobound then begin
                  let father = U.info (previous_bound s) in
                  if NodeTable.mem father_of_locked father then begin
                    let cobound = NodeTable.find father_of_locked father in
                    (* cobound nodes : "there exist m1 and m2 distinct in
                       τ and merged in g such that one¹ of them is red and
                       old_bound(m1) = old_bound(m2)" *)
                    if !Debug.unification_error then begin
                      let name_suffix =
                        Printf.sprintf "%s_before_raise_Cobound-%d-%d"
                          prefix (previous_id s) (previous_id cobound) in
                      print_snapshot ~name_suffix ();
                    end;
                    let err = Cobound cobound in
                    let _ = unif_error meaning_in_context err s in ()
                  end;
                  NodeTable.add father_of_locked father s
                  (* ¹ : the phrasing is that "one of them is red";
                     the implementation effectively raise an error
                     only if *both of them* are red. It is actually
                     a non-issue, because those cases are equivalent :
                     if a node under a bound is locked, any other
                     cobound node is either locked (if it is flexibly
                     bound) or rigid. In that last case, the merge
                     would weaken the locked node binding flag,
                     raising a Flag error. *)
                  end
                end
            end;
            rebind_unsafe t new_flags new_bound;
         (* this maintains the binding level correct for t and
            above, but may invalidate binding levels below t *)
         )
         equiv_u;
    )
    t1 (* t2 is equivalent to t1*);

  ()
;;


let emph_nodes l t =
  if List.exists (eqrepr t) l
  then Some "yellow"
  else None

let dump l t =
  Dot.dump ~emph:(emph_nodes l) (find_root t)
