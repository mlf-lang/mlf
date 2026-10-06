(** β-reduction on gMLF types (λ/@ of MLFω types) *)
open GType

(** The old redex reduction is new again ! 

    The previous strategy formulated the usual β-reduction in terms of
    the gUnify and gSolve function, wich embody the useful graph
    transformation logic : copy graph by expanding them, and modify
    them by unification.

    The problem with this approach is that the modification we do here
    are very unfriendly to the unification/expansion invariants and
    properties. Unification/expansion are fundamentally meant to make
    a graph evolve with strict permissions checkings, and β-reduction
    on the contrary is a local reduction that has no permission
    restrictions and should be virtually unobservable.

    There are two solutions : add unsafe hooks to all the
    unification/reduction transforms and subvert their semantics, wich
    I consider a very bad idea, or use unsafe operations for
    β-reduction, wich will led to more bugs in this part of the code,
    and less in the others.

    In the long term, the Good Thing To Do is to find a set of unsafe
    primitives that could be reused by both the unification/expansions
    operations and the β-reduction process. We're not there yet.

    So here is the unsafe approach, in four steps :

    1. If the (λ) node is not in the interior of the (@) node, unmerge
    it by creating a copy of its interior that is (flexibly) bound to
    the (@) node.

        Remark: Unlike in the expansion code, we share the frontier
        nodes between the two versions : we cannot use unification
        edges during the (β)-reduction process.

    2. Unfreeze both (λ) children node (explicit -> implicit flexible).

        Remark: the (λ)-body is possibly bound higher (bound aliasing
        λ(α)β). In this case, don't change it.

    3. Replace the λ-var (⊥) node by the @-arg.

        3A. Give the λ-var the same bound as the @-arg.
        
        3B. Substitute the λ-var (⊥) by the @-arg.

    4. Replace the (@) node by the λ-body

        4A. Give the (λ)-body the flags of (@)
        
        4B. Give the λ-body the same bound as (@)
        - if it is bound above (@), change (@)'s bound (to λ-body's bound)
        - if (@) is root, make it root too (temporarily)
        - elsewhere, give it (@)'s bound, and adjust levels on the rebound node.

        4C. Substitute the (@) node by the (λ)-body.

    A more detailed description, with informal proof of correctness,
    is avaible in Gabriel Scherer's report.
*)


(* unmerge a global inert (λ)-node :
   copy its interior but keep the copied head node with an undef binder

   This is used for β-reduction, to get the (λ) node in the local
   scope by binding its copy to the (@) node. See detailed comment of
   point 1. above.
*)
let lambda_copy lambda =
  assert (lambda_node lambda);
  let interior = in_interior lambda in

  (* we just copy the type subgraph, in a way *very* similar to what
  expansion does, but without invariant checks. *)

  let image_table = Table.create 10 in
  let set_image t t' =
    Table.init image_table t t' in
  let get_image t =
    Table.find image_table t in

  (* bottom-up structure copy *)
  dps
    (fun visit t ->
      if not (interior t)
      then (* share the frontier nodes *)
        set_image t t
      else 
        let edges = edges t in
        List.iter visit edges;
        let edges = List.map get_image edges in
        let t' = fresh Undef (node t) edges in
        set_image t t')
    lambda;

  (* top-down binding copy, leaving the head node undef 

     to get the level correct, it is important that rebinding is
     top-down, and that the level of the head node is set to the
     lambda level     
  *)
  (U.find (get_image lambda)).blevel <- blevel lambda;
  List.iter
    (dps
       (fun visit t ->
         if interior t then begin
           match binder t with
           | Bound (flag, tb) ->
               assert (undef_binder (get_image t));
               bind (get_image t) flag (get_image tb);
               List.iter visit (edges t);
           | _ -> assert false
         end))
    (edges lambda);

  let lambda' = get_image lambda in
  assert (undef_binder lambda');
  lambda'


let reduce_redex app =
  check_kinding (U.find app);
  let (lambda, arg) = below_apply app in
  assert (lambda_node lambda);

  (* step 1 *)
  let lambda =
    if eqrepr (bound lambda) app
    then lambda
    else
      let lambda' = lambda_copy lambda in
      bind lambda' (Flexible, Free) app;
      lambda' in

  let (var, body) = below_lambda lambda in

  let _check_step_1 = 
    assert (frozen var && eqrepr (bound var) lambda);
    (* the λ-body may be bound higher : ∀(β) ... (λ(α)β) *)
    assert (eqrepr (bound lambda) app);
  in

  (* step 2 *)
  reflag_unfrozen var;
  if (eqrepr (bound body) lambda && frozen body) then
    begin
      reflag_unfrozen body;
    end;

  let _check_step_2 =
    assert (not (rigid var));
    assert (not (rigid body));
  in

  (* step 3 *) 
  rebind_unsafe var (flags arg) (bound arg);
  GType.subst_by var arg;

  (* step 4 *)
  if root app then
    begin
      make_root body;
    end
  else if blevel body < blevel app then
    begin
      (* λ-body bound higher than (@) *)
      rebind_unsafe app (flags body) (bound body);
    end
  else begin
    rebind_unsafe body (flags app) (bound app);
    set_levels ~status:(fresh_status ()) ~interior:(bound app) body;
  end;

  GType.subst_by app body;
  ()
  

(* weak head normal form *)
let rec reduce_whnf t = match constr t with
  | Gen (_, _) -> assert false
  | Bot _ | Arrow | Constant _ | Forall _ | Lambda (_, _) -> ()
  | Apply (_, _) ->
      let lambda, _body = below_apply t in
      reduce_whnf lambda;
      match constr lambda with
      | Bot _ -> ()
      | Apply (_, _) -> ()
      | Lambda (_, _) ->
          reduce_redex t;
          reduce_whnf t
      | Arrow | Forall _ ->
          assert (kind t = K.Star);
          assert false (* kind error *)
      | Constant _ ->
          (* This condition can only happen if we had higher-kinded
             constants. Those should have a builtin reduction semantic.
           
             As we don't have those constants for now,
             I'll just suppose it doesn't happen.
           *)
          assert false
      | Gen (_, _) -> assert false
