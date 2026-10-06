open GType

type operation =
  | Graft of constr * gtype
  | Weaken of gtype
  | Merge of gtype * gtype
  | Raise of gtype
  | RaiseMerge of gtype * gtype

let print = function
  | Graft (tau, n) -> Printf.sprintf "graft-%s-%d"
      (GPrint.string_of_constr tau) (id n)
  | Weaken n -> Printf.sprintf "weaken-%d" (id n)
  | Merge (n, n') -> Printf.sprintf "merge-%d-%d" (id n) (id n')
  | Raise n -> Printf.sprintf "raise(%d)" (id n)
  | RaiseMerge (n, n') -> Printf.sprintf "raise_merge-%d-%d" (id n) (id n')

let constructor_type = function
  | Bot k -> bot k
  | Arrow ->
      let src = bot K.Star in
      let dst = bot K.Star in
      let arr = arrow src dst in
      List.iter (fun t -> bind t (Flexible, Free) arr) [src;dst];
      arr
  | Forall k ->
      let src = bot k in
      let dst = bot K.Star in
      let quant = forall src dst in
      List.iter (fun (freedom, t) -> bind t (Flexible, freedom) quant)
        [(Frozen, src); (Free, dst)];
      quant
  | Apply (_, _) | Lambda (_, _) ->
    assert false (* λ/@ must have been β-reduced away *)
  | Constant c -> constant c
  | Gen (_, _) -> failwith "constructor_type : unsupported gen node"


let eval ~root =
  let interior = in_interior root in
  let unsafe_unify (n, n') =
    (* we use 'unify' for the Merge operation; however, we may call
       merge on mergeable nodes wich break one of the unification
       rules (no cobound nodes, etc.), so we set the 'unsafe' flag to
       disable unification verification *)
    GUnify.gunify ~unsafe:true n n' in
  function
    | Graft (tau, n) ->
        let n' = constructor_type tau in
        bind n' (Flexible, Free) (bound n);
        (* n' must be bound somewhere or unification fail *)
        GUnify.gunify ~unsafe:true n n'
    | Weaken n ->
        assert (non_root n && interior n);
        GType.invariant_all_nodes_invariants root
          (fun () ->
             let _, freedom = flags n in
             reflag n (Rigid, freedom);
             (* TODO correct instantiability computation *)
             top_down ~status:(fresh_status()) ~exist:true
               (fun t -> recompute_instantiable (U.find t))
               (find_root n))
          ()
    | Merge (n1, n2) ->
        assert (interior n1 && interior n2);
        unsafe_unify (n1, n2);
    | Raise n ->
        assert (non_root n && interior n && non_root (bound n) && interior (bound n));
        rebind_raise n (flags n) (bound (bound n))
    | RaiseMerge (n, n') ->
        assert (interior n && not (interior n'));
        let () = GType.global_check_node_invariants root in
        GType.invariant_all_nodes_invariants root unsafe_unify (n, n');
        ()

(** Normalized expansion solving, according to the algorithm in Lemma
    11.5.3 (p. 169) of Boris's thesis. *)
exception Degenerate_instance of gtype

(** The control flow of the normalize_presolution function is a bit
    peculiar, because of side-effect issues. The implementation is
    roughly as follows.

    1) We create an expansion ('source') of the instantiation
    constraint source ('preserved_source'), then we create a second
    copy of it, with a mapping table between them.

    2) We unify the second copy with the instantiation constraint
    destination, so that the mapping table ('image') now relates the
    expansion and the result (this mapping is necessary to use the
    normalization algorithm presented in Boris's thesis).

    3) We apply the thesis algorithm to the expansion, to build step
    by step the normalized instance atomic operations. This require to
    apply the operations on the expansion at the same time.

    4) When the decomposition in atomic instance operations is
    complete, the expansion is completely identical to the
    destination.

    The problem is that we cannot collect the atomic operations, send
    them to xTranslate, and expect good results : the translation
    process of those operations into xMLF type computations needs
    information about the expansion nodes, wich is not available
    anymore because the expansion was mutated during normalization.

    To work around this, the normalization function takes an
    additional "recorder" parameter, with type "operation -> unit", to
    wich every operation is feed _before_ being applied on the
    expansion. The xTranslate calls the normalization with
    a "recorder" function that builds the translation during the
    normalization.

    Remark : the node recorded during normalization are the node *of
    the expansion*, not the nodes of the origial subtree.
*)

let normalize_presolution recorder preserved_source inst_mode destination =
  let root = bound destination in
  if !Debug.before_normalize_instance then begin
    let name_suffix =
      Printf.sprintf "before_normalize_instance_%d_%d"
        (id preserved_source) (id destination) in
    Dot.drum ~ids:true ~proj:false ~name_suffix (find_root destination)
  end;
  let source = GSolve.expand preserved_source inst_mode root in

  if eqrepr source destination then
    raise (Degenerate_instance source);
  let image_table =
    (* why binding_reset:false ?
       
       Because if a node is explicitly bound (frozen) to
       'destination', the binding reset would (explicitely) rebind it
       to 'mapped_source', and the further unification would fail with
       a Bound error.
       
       Maybe we shouldn't reset explicit bindings. Maybe we should not
       raise Bound for gen_node/son_of_gen_node changes. *)
    match GSolve.expansion_image ~binding_reset:false root source inst_mode root with
      | None -> raise (Degenerate_instance source)
      | Some mapping_copy ->
        let mapped_source = Table.find mapping_copy source in
        if !Debug.before_normalize_unification then begin
          let name_suffix =
            Printf.sprintf "before_normalize_unification_%d_%d"
              (id mapped_source) (id destination) in
          Dot.drum ~ids:true ~proj:false ~name_suffix (find_root root)
        end;
        GUnify.gunify mapped_source destination;
        mapping_copy in
  (* we keep `image_table` around instead of just using the `image`
     function, because we may need to update the binding table when
     grafting fresh nodes *)
  let image n = Table.find image_table n in
  let interior = in_interior source in
  let apply op =
    if !Debug.before_apply_atomic_instance_operation then begin
      let name_suffix = Printf.sprintf "before_apply_%s_under_%d"
        (print op) (id source) in
      Dot.drum  ~name_suffix ~ids:true ~proj:false (find_root source)
    end;
    recorder source op;
    eval ~root:source op;
    () in

  (* 1 : Grafting inner nodes *)
  GType.invariant_all_nodes_invariants root
    (top_down ~interior:source ~status:(fresh_status())
       (fun n ->
          let n_d = image n in
          if constr n <> constr n_d then begin
            assert (bot_node n);
            apply (Graft (constr n_d, n));
            (* after new nodes have been grafted to the source,
               image_table must be updated *)
            let update_table t t_d = Table.init image_table t t_d in
            List.iter2 update_table (edges n) (edges n_d);
            (* the n node itself may have changed during unification,
               so it is updated as well *)
            Table.add image_table n n_d;
          end))
    source;
  (* 1' : Raising inner nodes *)
  GType.invariant_all_nodes_invariants root
    (bottom_up ~interior:source
       (fun n ->
          while interior (bound n) && not (eqrepr (bound n) source)
            && not (eqrepr (image (bound n)) (bound (image n))) do
              apply (Raise n)
          done))
    source;
  (* 1'' :  Merging inner nodes *)
  GType.invariant_all_nodes_invariants root
    (fun () ->
       let merge_sets = Table.create 10 in
       (* we use an ordered visit to guarantee that when Merge(n, n'),
          n > n' in the leftmost-lowermost ordered used by
          xTranslate *)
       ordered_visit ~condition:(in_interior source) ~node:source
         (fun n -> Table.add_elem merge_sets (image n) n);
       bottom_up ~interior:source ~status:(fresh_status())
         (fun n ->
            let merge n1 n2 =
              (* only merge merged node wich are both _inside_ the presolution *)
              if interior (lcb n1 n2) then
                apply (Merge (n1, n2)) in
            match Table.find_list merge_sets (image n) with
              | [] | [_] -> ()
              | hd::tl ->
                  (* Remark : we iterate on the node in increasing order, but as
                     merged nodes get stacked in a list (Table.add_elem), they
                     are then reiterated (List.fold_left) in _decreasing_ order,
                     effectively guaranteeing than Merge(n, n') => n > n' *)
                  let do_merge last next =
                    merge last next;
                    next in
                  ignore (List.fold_left do_merge hd tl))
         source)
    ();
  (* 2 : weakening strictly-inner nodes *)
  GType.invariant_all_nodes_invariants root
    (bottom_up ~interior:source
       (fun n ->
          if not (eqrepr n source) then
            if fst (flags n) = Flexible && fst (flags (image n)) = Rigid then
              apply (Weaken n)))
    source;
  (* At this stage, the interiors are identical : check *)
  let bijection = Table.create 10 in
  GType.invariant_all_nodes_invariants root
    (bottom_up ~interior:source
       (fun n ->
          assert (not (Table.mem bijection (image n)));
          Table.init bijection (image n) n;
          if not (eqrepr n source) && not (eqrepr (bound n) source) then begin
            assert (flags n = flags (image n));
            assert (eqrepr (image (bound n)) (bound (image n)));
          end))
    source;
  (* raisemerging non-root nodes *)
  GType.invariant_all_nodes_invariants root
    (bottom_up ~interior:source ~status:(fresh_status ())
       (fun n ->
          let n_d = image n in
          if non_root n && eqrepr (bound n) source then
            if not (eqrepr (bound n_d) destination) then
              apply (RaiseMerge (n, n_d))))
    source;
  (* possibly weakening, then merging root nodes *)
  GType.invariant_all_nodes_invariants root
    (fun () ->
       if rigid destination then apply (Weaken source);
       apply (RaiseMerge (source, destination)))
    ();
  ()
;;
