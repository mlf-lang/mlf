(** Types and auxiliary function on types *)

module U = Union_find;;
module K = ETypeKinds

type flexibility = Rigid | Flexible
type freedom = Frozen | Free
type binding_flags = flexibility * freedom

type instance_flag = [ `Implicit | `Explicit ]
type expansion_type = [ instance_flag | `Apply ]

let graphic_binding_of_syntaxic_binding (flex, expl) =
  (match flex with
    | EType.Flex -> Flexible
    | EType.Rigid -> Rigid),
  (match expl with
   | EType.Explicit -> Frozen
   | EType.Implicit -> Free)

let syntactic_binding_of_graphic_binding (flex, free) =
  (match flex with
     | Flexible -> EType.Flex
     | Rigid -> EType.Rigid),
  (match free with
     | Free -> EType.Implicit
     | Frozen -> EType.Explicit)

type gtype = (** indirection pour union find *)
    ginfo U.point
and ginfo = {
    node : node;
    edges : gtype list;

    mutable bound : bound;
    (** bound : parent node and binding flags *)

    mutable instantiable : bool;
    (** binding path context cache :
        - true for instantiable (binding path composed of all flexible bindings)
        - false for strict (binding path contains at least one rigid binding)

        Warning : this property has no meaning if bound is Undef *)

    mutable blevel : int;
    (** hauteur de l'arbre de binding, utilisé pour le calcul de LCA *)

    status : int ref;
    (** petit poucet, utilisé pendant les visites récursive
     typiquement: default, visiting, visited *)

    id : int;
     (** physical identity of the node: u.id = v.id iff u == v *)
  }
and node = (** symbols *)
  {
    constr : constr;
    polynode : bool;
    (** pour le calcul des "inert nodes",
        source intrinseque de polymorphisme *)
  }
and constr =
  | Bot of K.kind      (* The bottom type *)
  | Arrow              (* Arrow type *)
  | Constant of constant  (* Unit, Integer *)
  | Gen of K.kind * gen_info
  (* Generic nodes, that allows instantiation edges *)
  | Forall of K.kind  
  (* Explicit quantification : Λ(κ) : κ -> * *)
  | Apply of K.kind * K.kind
  (* Type-level application :  @(κ,κ') : (κ -> κ') -> κ -> κ' *)
  | Lambda of K.kind * K.kind
  (* Type-level lambda :       λ(κ,κ') : κ -> κ' -> (κ -> κ') *)

and constant =
  | Int | Unit | Bool

and gen_info =
    { expr : gtype_expr loc
      (** syntactic skeleton of the original term *)
    ; mutable inst :
        (gtype * instance_flag * GMeaning.constraint_meaning) list
      (** instantiation edges, with information on wether this is an
          implicit or explicit instance and, optionally, an annotation
          of the constraint meaning *)
    ; mutable exist : gtype list
      (** virtual edges, which are not part of the structure, but must
          be followed to reach all nodes *) }
and gtype_expr =
  [ `Root (* used by print_type.normalize *)
  | gtype GAst.bound_aware_expr_
  | `Abs of AST.value loc * gtype loc
  | `TyAbs of AST.type_abstraction loc * gtype loc
  | `App of gtype loc * gtype loc * gtype
  | `TyApp of gtype loc * gtype loc * gtype
      (** function node, argument node, arrow/forall node *)
  | `Type of AST.type_expr loc * gtype loc
  | `SomeTy of bound_prefix_expr * gtype loc
      (** prefix nodes, expr node *)
  | `CoerceCt of (AST.coercion loc * gtype loc)
      (** coercion, type node *)
  | `Ct of AST.value * EType.constant_monotype
  | `BuiltinCt of AST.builtin_ct loc ]
and bound_prefix_expr = (AST.bound_abstraction loc * gtype) list
(** gtype_expr structure can express the relation between a gen node,
    the initial AST term, and the nodes generated from its
    subterms. For example the generic node produced from `App(a1, a2)
    will contain `App(n1, n2, t), with n1, n2 the nodes corresponding
    to expressions a1, a2, and t corresponding to the generated arrow
    type *)
and 'a loc = 'a Locations.loc
and bound =
  | Root (** cannot be bound *)
  | Undef (** not yet computed---during creation of graphic types *)
  | Bound of (binding_flags * gtype) (** its bound *)

exception Cycle of gtype

let symbol_constant const = { constr = Constant const ; polynode = false; }
let symbol_bot k = { constr = Bot k ; polynode = true; }
let symbol_arrow = { constr = Arrow ; polynode = false }
let symbol_apply k k' = { constr = Apply (k, k'); polynode = false }
let symbol_forall k = { constr = Forall k; polynode = false }
let symbol_lambda k k' = { constr = Lambda (k, k'); polynode = false }
let symbol_gen k gen_expr =
  let gen = { expr = gen_expr
            ; inst = []
            ; exist = [] } in
  { constr = Gen (k, gen); polynode = false; }

let eq_reg_constr c1 c2 =
  (* re. kinds : we want eq_reg_constr to also test for kind equality.
     Not all kind parameters of the constructors are relevant. For
     example, kind of Forall are ignored, as the result is always of
     kind Star. *)
  match c1, c2 with
  | Constant t1, Constant t2 -> t1 = t2
  | Constant _, _ | _, Constant _ -> false

  | Arrow, Arrow -> true
  | Arrow, _ | _, Arrow -> false

  | Forall _, Forall _ -> true
  | Forall _, _ | _, Forall _ -> false

  | Bot k, Bot k'
  | Apply (_, k), Apply (_, k') -> k = k'
  | Bot _, _ | _, Bot _ 
  | Apply (_, _), _ | _, Apply (_, _) -> false

  | Lambda (k1, k2), Lambda (k1', k2') -> k1 = k1' && k2 = k2'
  | Lambda (_, _), _ | _, Lambda (_, _) -> false

  | Gen (_, _), _ (* | _, Gen (_, _) *) -> assert false (* only regular constructors *)


let kind_of_constr = function
  | Constant (Int | Unit | Bool) -> K.Star
  | Bot k -> k
  | Arrow -> K.Star
  | Apply (_k, k') -> k'
  | Forall _ -> K.Star
  | Lambda (k, k') -> K.Arrow (k, k')
  | Gen (k, _) -> k

let arity_of_constr = function
  | Constant (Int | Unit | Bool) -> []
  | Bot _ -> []
  | Arrow -> [K.Star; K.Star]
  | Apply (k, k') -> [K.Arrow (k, k'); k]
  | Forall k -> [k; K.Star]
  | Lambda (k, k') -> [k; k']
  | Gen (k, _) -> [k]


let node t = (U.find t).node
let edges t = (U.find t).edges
let id t = (U.find t).id
let blevel t  = (U.find t).blevel
let compare_blevel u v = compare (blevel u) (blevel v)

let constr t = (node t).constr
let kind t = kind_of_constr (constr t)


let eqinfo u1 u2 = u1.id = u2.id;;
   (** really the same nodes, used for computation of most common ancestors *)
let eqrepr t1 t2 = eqinfo (U.find t1) (U.find t2);;
   (** identical after unification nodes, normally used *)

let last_id = ref 0;;
let fresh_id() = incr last_id; !last_id;;
let status = ref 0;;
let new_status() = incr status; assert (!status > 0); !status;;

let instantiable_binding = function
  | Flexible, Free -> true
  | Rigid, _ | _, Frozen -> false

let compute_instantiable = function
  | Undef -> true
  | Root -> true
  | Bound (flags, t) ->
      instantiable_binding flags
      && (U.find t).instantiable

let rec really_instantiable u = match u.bound with
  | Undef | Root -> true
  | Bound (flags, t) ->
      instantiable_binding flags
      && really_instantiable (U.find t)

let really_instantiable u = compute_instantiable u.bound

let recompute_instantiable node =
  node.instantiable <- compute_instantiable node.bound

let check_node_invariants node =
  recompute_instantiable node;
  assert (node.instantiable = really_instantiable node)

let check_kinding u =
  let edges_kind = List.map kind u.edges in
  let arity = arity_of_constr u.node.constr in
  assert (List.length arity = List.length edges_kind);
  assert (List.for_all (fun (k, k') -> k = k')
            (List.combine arity edges_kind))

let fresh bound node edges =
  let blevel = match bound with
    | Undef -> -1
    | Root -> 0
    | Bound (_, t) -> blevel t + 1 in
  let node =
    { node = node;
      edges = edges;
      bound = bound;
      instantiable = compute_instantiable bound;
      blevel = blevel;
      status = ref 0;
      id = fresh_id();
    } in
  check_node_invariants node;
  check_kinding node;
  U.fresh node

let subst_by t1 t2 = U.union ~keep:t2 ~lose:t1 ();;
let merge t1 t2 =
  if (U.find t1).id < (U.find t2).id then
    subst_by t2 t1
  else
    subst_by t1 t2;;

let instantiable t =
  let u = U.find t in
  check_node_invariants u;
  u.instantiable

let last_id = ref 0;;
let compare u v = compare (id u) (id v)

let binder t = (U.find t).bound

let locked_bound = function
  | Undef -> assert false
  | Root -> false
  | Bound (flags, t) ->
      instantiable_binding flags
      && not (instantiable t)

let rigid_bound = function
  | Undef -> assert false
  | Root | Bound ((Flexible, _), _) -> false
  | Bound ((Rigid, _), _) -> true

let frozen_bound = function
  | Undef -> assert false
  | Root | Bound ((_, Free), _) -> false
  | Bound ((_, Frozen), _) -> true

let locked node = locked_bound (binder node)
let rigid node = rigid_bound (binder node)
let frozen node = frozen_bound (binder node)

let root t =
  match binder t with
  | Root -> true
  | _ -> false

let undef_binder t =
  match binder t with
  | Undef -> true
  | _ -> false

let flags, bound =
  let bound t = match binder t with
    | Bound (flags, t') -> (flags, t')
    | Undef | Root -> assert false in
  (fun t -> fst (bound t)),
  (fun t -> snd (bound t))

let non_root t =
  (* we actually want to guarantee that t is bound, hence
     'not (root t)' woudln't behave correctly on Undef *)
  match binder t with
    | Bound _ -> true
    | _ -> false

let rebind_unsafe t1 flags t2 =
  if eqrepr t1 t2 then
    raise (Cycle t1);
  let d1 = U.find t1 in
  d1.bound <- Bound (flags, t2);
  d1.blevel <- blevel t2 + 1;
  recompute_instantiable d1

let reflag, rebind_raise =
  let rebind t1 flags t2 =
    assert (non_root t1);
    let u = U.find t1 in
    check_node_invariants u;
    rebind_unsafe t1 flags t2;
    check_node_invariants u in
  let reflag t flags =
    rebind t flags (bound t) in
  let rebind_raise t flags new_bound =
    assert (blevel new_bound <= blevel (bound t));
    rebind t flags new_bound in
  reflag, rebind_raise

let reflag_unfrozen t =
  let flex, free = flags t in
  assert (free = Frozen);
  reflag t (flex, Free)

let bind t1 flags t2 =
  assert (undef_binder t1);
  let u = U.find t1 in
  check_node_invariants u;
  rebind_unsafe t1 flags t2;
  check_node_invariants u

let make_root t =
  assert (undef_binder t);
  let u = U.find t in
  check_node_invariants u;
  u.bound <- Root;
  u.blevel <- 0;
  recompute_instantiable u
;;

let make_undef t =
  assert (not (undef_binder t));
  let u = U.find t in
  u.bound <- Undef

let rec find_root t =
  if root t || undef_binder t then t
  else find_root (bound t)

let gen_node t = match constr t with Gen _ -> true | _ -> false
let reg_node t = not (gen_node t)
let bot_node t = match constr t with Bot _ -> true | _ -> false
let arrow_node t = (node t).constr = Arrow
let apply_node t = match constr t with Apply _ -> true | _ -> false
let lambda_node t = match constr t with Lambda _ -> true | _ -> false
let forall_node t = match constr t with Forall _ -> true | _ -> false
let const_node const t =
  match constr t with Constant c -> c = const | _ -> false

let gen_info tg =
  match constr tg with
    | Gen (_k, g) -> g
    | _ -> assert false

let below_gen, below_arrow, below_apply, below_lambda, below_forall =
  let select f t = f (constr t, edges t) in
  select (function Gen _, [t] -> t | _ -> assert false),
  select (function Arrow, [t1; t2] -> (t1,t2) | _ -> assert false),
  select (function Apply _, [t1; t2] -> (t1,t2) | _ -> assert false),
  select (function Lambda _, [t1; t2] -> (t1, t2) | _ -> assert false),
  select (function Forall _, [t1;t2] -> (t1,t2) | _ -> assert false)

let add_exist t tg =
  assert (gen_node tg);
  let ug = gen_info tg in
  ug.exist <- U.repr t :: ug.exist

let ebind t flags tg =
  assert (gen_node tg);
  bind t flags tg;
  add_exist t tg;
;;

let mkinst tg inst_flag meaning t =
  assert (gen_node tg && reg_node t);
  check_node_invariants (U.find tg);
  let g = gen_info tg in
  g.inst <- (t, inst_flag, meaning) :: g.inst

(** Gen nodes are constructed in two moments :

    - first, with "open_gen" we build a "gen_in_construction" value,
    wich is used to recolt all node bound to it.

    - then, we build all the nodes under that gen node, using the
    under_gen combinator to count them as potential existential
    nodes. Note that all under_gen node are to be bound to the (G)
    node. In partiular, they must not be already bound.

    - finally, after all the bound nodes have been declared, we call
    "close_gen", with the only edge and the node expression (see
    gtype_expr comment), that return the complete gen node.

    Close_gen use a closure computation to find the subnodes that are
    existentially bound (those that are not the child of the node
    directly under the gen node, or one of its children), ensuring the
    existential information is correct by construction.
*)
type gen_in_construction = Subnodes of (gtype list ref)

let open_gen () = Subnodes (ref [])

let under_gen (Subnodes li) node =
  assert (undef_binder node);
  li := node :: !li;
  node

let under_inst inst inst_flag meaning node =
  mkinst inst inst_flag meaning node;
  node

let close_gen (Subnodes children) edge gen_expr =
  let children = !children in
  List.iter (fun t -> check_node_invariants (U.find t)) (edge :: children);
  let not_in list elem = not (List.exists (eqrepr elem) list) in
  let linked_nodes =
    let rec closure old_set =
      (* quite inneficient as it use lists; does not really matter as
         it won't explore more than three levels (AST-generated nodes
         have a very small depth) *)
      let new_set = List.concat (List.map edges old_set) in
      if List.filter (not_in old_set) new_set = [] then old_set
      else closure (new_set @ old_set) in
    closure [ edge ] in
  let g_node = fresh Undef (symbol_gen (kind edge) gen_expr) [ edge ] in
  let existential = not_in linked_nodes in
  let bind child =
    (if existential child then ebind else bind)
      child (Flexible, Free) g_node in
  List.iter bind children;
  check_node_invariants (U.find g_node);
  g_node

let maybe_gen gen node =
  match gen with
    | None -> node
    | Some gen ->
        under_gen gen node

let maybe_inst inst inst_flag node =
  match inst with
    | None -> node
    | Some (inst, meaning) ->
        under_inst inst inst_flag meaning node

let bot ?gen ?inst kind =
  let node = fresh Undef (symbol_bot kind) [] in
  maybe_gen gen (maybe_inst inst `Implicit node)

let constant ?gen const =
  let node = fresh Undef (symbol_constant const) [] in
  maybe_gen gen node

let arrow ?gen ?inst t1 t2 =
  let node = fresh Undef symbol_arrow [ t1; t2 ] in
  maybe_gen gen (maybe_inst inst `Implicit node)

let apply ?gen ?inst t1 t2 =
  let (k, k') = match kind t1 with
    | K.Arrow (k, k') -> k, k'
    | _ -> assert false in
  let node = fresh Undef (symbol_apply k k') [ t1; t2 ] in
  maybe_gen gen (maybe_inst inst `Implicit node)

let lambda ?gen ?inst t1 t2 =
  let k, k' = kind t1, kind t2 in
  let node = fresh Undef (symbol_lambda k k') [ t1; t2 ] in
  maybe_gen gen (maybe_inst inst `Implicit node)

let forall ?gen ?expl_inst t1 t2 =
  let node = fresh Undef (symbol_forall (kind t1)) [ t1; t2 ] in
  maybe_gen gen (maybe_inst expl_inst `Explicit node)

let in_interior t =
  let level = blevel t in
  fun t' ->
    eqrepr t t' || blevel t' > level

let maybe_interior t t' =
  match t with
    | None -> true
    | Some t -> in_interior t t'

(** Table and NodeTable are two associative structures extending
    hashtables, indexed by gMLF nodes. More precisely, NodeTable is
    indexed by `ginfo`, the concrete structure of a node, while Table
    is indexed by a `gtype`, which correspond to a whole equivalence
    class in the Union-find structure used to track unifications of
    nodes.

    In general, `Table` should be preferred, as the main semantic
    object, a gMLF graph node, corresponds exactly to
    a `gtype`. `NodeTable` should only be used in the rare case where
    the representant in the union-find matters, such as in the
    `GUnify.gunify` unficitation algorith which exploits fine-grained
    properties of the union-find structure.

    It is possible to convert a `Table` into a more precise
    `NodeTable` with the `nodetable_of_table` function: each key is
    mapped to the union-find representant of the equivalence
    class. The reverse conversion is not possible in general as it
    would require to "guess" an union-find index for a given concrete
    node structure.
*)
module NodeTable = Utils.MakeTable
  (struct
    type t = ginfo
    let hash node = node.id
    let equal = eqinfo
   end)


module Table = Utils.MakeTable
  (struct
    type t = gtype
    let hash = id
    let equal = eqrepr
   end)

let nodetable_of_table table =
  let nodetable = NodeTable.create (Table.length table) in
  let add t v =
    let u = U.find t in
    NodeTable.add nodetable u v in
  Table.iter add table;
  nodetable

(** Depth first search visits *)
let do_nothing _ = ()

let fresh_status () =
  let table = Table.create 10 in
  fun u ->
    try Table.find table u
    with Not_found ->
      let status = ref 0 in
      Table.add table u status;
      status

(** Semi-ugly debug hacks to protect against nasty reentrency problems
    The idea is that a reentrency bug happen when all those conditions
    are met :

    1) we start a dps iteration on nodes
    2) during the iteration, there is an inner dps call
    3) the inner dps call overwrite the status information of the
       outer dps call
    4) the outer dps call try to read status information that have
       been overwritten by the inner call

    (1 and 2) alone are not sufficient to have a race condition : for
    example, during a top-down iteration, we might run other nested
    top-down iterations; if they don't change the status of node above
    their local root, the outer dps status are still valid (the
    visiting/visited information if correct)

    The last_closed_status global, check_last_closed_status and
    close_status functions are there to detect situation (3) . The
    idea is that the status informations that can be safely erased are
    the informations corresponding to "closed iteration" : iteration
    that have been completed, that are not an outer dps currently
    being called. We can therefore use a global variable
    (last_closed_status), that contains the value of the status of the
    last closed iteration : when we end an operation, we update that
    status (close_status). During an iteration, just before
    overwriting some status information, we check that the status to
    be overwritten either :
    - is one of the "visiting, visited" status of the current iteration
    - is inferior or equal to the last closed status

    If those conditions are not met, we have a potential race
    condition : we're overwriting status information of a still open
    iteration, that might need it in the future.


    It is also easy to detect situation (2) and report it accurately,
    wich as noted is not necessarily dangerous, but should be
    considered suspicious (when nesting two dps, better use local
    status tables for either one) : at the end of an iteration, just
    before updating last_closed_status, we can check that
    last_closed_status is still inferior to the status of the current
    iteration. If not, there was an inner iteration running after the
    start of the current one. This is what the
    `last_closed_was_before_current_status` checks.

    It is more useful to report (warning or error) the issue during
    the outer iteration, as for efficiency reasons it is better to
    have the outer iterations using local tables, and the inner
    iteration (probably running more often) using the efficient
    non-reentrant field.


    Notes :

    This make use use of the (undocumented) invariant that fresh
    status are strictly increasing.

    The check_last_closed_status and close_status functions are made
    public, because some other modules use fresh_status directly for
    hand-written dps-like iterations.
*)
let last_closed_status = ref (-1)
let check_last_closed_status visiting visited status =
  let last_status = !last_closed_status in
  if last_status >= 0 then
    if status > last_status && status < min visited visiting then
      failwith
        (Printf.sprintf
           "Status failure : status %d, last closed %d, visiting %d, visited %d\n%!"
           status last_status visiting visited)
let close_status visiting visited =
  last_closed_status := max !last_closed_status (max visiting visited)
let last_closed_was_before_current_status visiting visited =
  !last_closed_status <= max visiting visited

let global_status t = (U.find t).status

let warn_dps = ref true

let dps ?(force_reentrant=false)
    ?status ?interior ?(acyclic=true) ?(seen=do_nothing) unseen =
  let use_global_status = (status = None) in
  let visiting = new_status() in
  let visited = new_status() in
  let rec visit status t1 =
    if maybe_interior interior t1 then
      if !(status t1) = visited then
        seen t1
      else if !(status t1) = visiting then
        (if acyclic then raise (Cycle t1) else ())
      else
        begin
          if use_global_status then
            check_last_closed_status visiting visited !(status t1);
          status t1 := visiting;
          unseen (visit status) t1;
          status t1 := visited;
        end in
  fun node ->
    match status with
      | Some status -> visit status node
      | None ->
          let result = visit global_status node in
          if not (last_closed_was_before_current_status visiting visited) then
            (if force_reentrant then failwith "Error : nested dps call"
             else Printf.eprintf "Warning : nested dps call !\n%!");
          close_status visiting visited;
          result

let top_down ?force_reentrant ?status ?interior ?acyclic ?(exist=false) unseen =
  dps ?force_reentrant ?status ?interior ?acyclic
    (fun visit t ->
       unseen t;
       List.iter visit (edges t);
       if exist && gen_node t then
         List.iter visit (gen_info t).exist)

let bottom_up ?force_reentrant ?status ?interior ?acyclic ?(exist=false) unseen =
  dps ?force_reentrant ?status ?interior ?acyclic
    (fun visit t ->
       List.iter visit (edges t);
       if exist && gen_node t then
         List.iter visit (gen_info t).exist;
       unseen t)

(* An auxiliary function for a guaranteed leftmost-lowermost iteration
   below a given node *)
let ordered_visit
    ?(condition = (fun _t -> true))
    ~node action =
  let status = fresh_status () in
  dps ~status (fun visit t->
    if condition t then begin
      List.iter visit (edges t);
      action t;
    end) node

(* An auxiliary function for a guaranteed inverse-ordered iteration
   below a given node *)
let inverse_ordered_visit
    ?(condition = (fun _t -> true))
    ~node action =
  let status = fresh_status () in
  dps ~status (fun visit t->
    action t;
    if condition t then begin
      List.iter visit (List.rev (edges t));
    end) node

let set_local_level t =
  let u = U.find t in
  match u.bound with
    | Root -> u.blevel <- 0
    | Bound (_, t') -> u.blevel <- blevel t' + 1;
    | Undef -> assert false

let set_levels ?force_reentrant ?status ?interior ?acyclic t =
  top_down ?force_reentrant ?status ?interior ?acyclic ~exist:true
    set_local_level
    t

(** Returns the lowest common node that is equal or above both t1 and t2 *)
let rec lcb t1 t2 =
(*   Printf.printf "\n id=%d level=%d /\ id=%d level=%d\n%!" *)
(*     (U.find t1).id (U.find t1).blevel (U.find t2).id (U.find t2).blevel; *)
  if eqrepr t1 t2 then t1
  else
    let c = compare_blevel t1 t2 in
    if c < 0 then lcb t1 (bound t2)
    else if c > 0 then lcb (bound t1) t2
    else lcb (bound t1) (bound t2)
;;


(** Computation of the inert node under a set of roots:

    `exposed_table_under_nodes` returns a table of the nodes under the
    given roots that are not inert ('exposed' means 'not inert'). It
    allows for efficient checking on all the nodes below the roots,
    and is therefore useful in procedure that needs lots of inert test
    in a given subforest of the graph, such as the rigidification
    procedure of xTranslate.

    `inert_under_nodes` abstract the table away into a `node -> bool`
    function.

    `inert` gives up the caching, recomputing the set of inerts each
    time it is called. Less efficient, for parts where you do not care
    (printing, debug...).
*)
let exposed_table_under_nodes roots =
  let exposed = Table.create 10 in
  let set_exposed t = Table.replace exposed t () in
  let status = fresh_status () in
  List.iter
    (bottom_up ~force_reentrant:true ~status ~acyclic:false ~exist:true
       (fun t ->
         if (node t).polynode then set_exposed t;
         if Table.mem exposed t
           && non_root t
           && instantiable_binding (flags t)
         then set_exposed (bound t)))
    roots;
  exposed

let inert_under_nodes roots =
  let exposed = exposed_table_under_nodes roots in
  fun t -> not (Table.mem exposed t)

let inert t = inert_under_nodes [t] t

let rec find_graph_root t =
  if root t then t
  else find_graph_root (bound t)



(** Invariant enforcment : the given function does not create new nodes *)
let node_count node =
  let count = ref 0 in
  top_down ~exist:true (fun _ -> incr count) (find_root node);
  !count

let invariant_no_new_node f t =
  let count_before = node_count t in
  let res = f t in
  let count_after = node_count t in
  assert (count_before = count_after);
  res

let global_check_node_invariants node =
  let check t = check_node_invariants (U.find t) in
  top_down ~status:(fresh_status ()) ~exist:true check (find_root node)

let invariant_all_nodes_invariants node action input =
  let root = find_root node in
  let () = global_check_node_invariants root in
  let result = action input in
  let () = global_check_node_invariants root in
  result



(** binding flags unification : when unifying bindings, it is possible
    to unify a weaker flag to a stronger one. min_flags is the most
    permissive couple of flags, neutral element of flags weakening *)
let weaker_flexibility_flag = function
  | Flexible, Flexible -> Flexible
  | ( Rigid, Flexible
    | Flexible, Rigid
    | Rigid, Rigid ) -> Rigid

let weaker_freedom_flag = function
  | Free, Free -> Free
  | ( Frozen, Free
    | Free, Frozen
    | Frozen, Frozen ) -> Frozen

let weaker_flags (flex, free) (flex', free') =
  weaker_flexibility_flag (flex, flex'),
  weaker_freedom_flag (free, free')

let min_flags = (Flexible, Free)

(* if two flags want to go from the same source to the same
   destination, merge them *)
let merge_flags f1 f2 = match (f1, f2) with
| (Flexible, Free), flag
| flag, (Flexible, Free) -> Some flag

| (Rigid, Free), (Rigid, Free) -> Some (Rigid, Free)

| (flex, Frozen), (flex', _)
| (flex, _), (flex', Frozen) ->
    if flex = flex' then Some (flex, Frozen)
    else None
