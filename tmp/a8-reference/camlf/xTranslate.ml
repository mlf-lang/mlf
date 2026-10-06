open Locations
open GType

(* In order to translate painlessly the "named variable"
   representation of eMLF/gMLF terms into the "de Bruijn indices"
   representation of xMLF terms, we use the XAst.DSL wich provide
   a "named" view of xMLF terms. *)
module X = XAst.DSL

(** Translation of a presolution into the equivalent rigid
    presolution : rigidify *)
let rigidify_node node =
  (* gen node are always kept flexible *)
  if not (gen_node node) then
    match binder node with
      | Undef -> assert false
      | Root | Bound((Rigid, _), _) -> ()
      | Bound ((Flexible, f), t) ->
          rebind_unsafe node (Rigid, f) t

(* To remove inert-locked operations, it suffices to rigidify all
   inert nodes. See §15.2.8 of Boris's thesis. *)
let rigidify_inert inert t =
  ignore (if inert t then rigidify_node t)

(* We also rigidify the direct child of each non-degenerate Gen node
   (§15.2.5.1) *)
let is_scheme_node t =
  non_root t && gen_node (bound t)
  && eqrepr t (below_gen (bound t)) (* child of a gen node *)

let rigidify_gen t =
  if is_scheme_node t
  then ignore (rigidify_node t)

let node_outside_gen_node_structure t =
  non_root t && gen_node (bound t) && reg_node t
  && (try
        top_down ~interior:(bound t) ~exist:false ~status:(fresh_status ())
          (fun k -> if eqrepr k t then raise Exit) (bound t);
        true
      with Exit -> false)

let rigidify_existentials t =
  if node_outside_gen_node_structure t
  then ignore (rigidify_node t)


let rigidify_annot t =
  match constr t with
    | Gen (_, {expr = {obj = `CoerceCt _}}) ->
        let (_, t_res) = below_arrow (below_gen t) in
        (* in the degenerate case, t_res is a free variable (fun (x :
           'a) -> x). In that case, it is bound higher than t, and
           should *not* be rigidified *)
        if eqrepr (bound t_res) t then
          ignore (rigidify_node t_res)
    | _ -> ()

let check_rigidification node =
  (* check the invariants that must hold after rigidification, so that
     the presolution is translatable *)
  let inert = inert_under_nodes [node] in
  let inert_locked t = inert t && locked t in
  let abstraction_or_application_node_below tg =
    if not (gen_node tg) then None
    else match (constr tg) with
      | Gen (_, {expr = {obj = `Abs (_, _)}}) ->
          Some (below_gen tg)
      | Gen (_, {expr = {obj = `App (_, _, t)}}) ->
          Some t
      | _ -> None in
  top_down ~status:(fresh_status ()) ~exist:true
    (fun t ->
       assert (not (inert_locked t));
       if is_scheme_node t then
         assert (rigid t);
       (match abstraction_or_application_node_below t with
          | None -> ()
          | Some t' -> assert (rigid t'));
       if node_outside_gen_node_structure t then begin
         if !Debug.rigidify_error then begin
           let name_suffix = Printf.sprintf "rigid_fail_%d" (id t) in
           if not (rigid t) then
             Dot.drum ~ids:true ~proj:false ~name_suffix (find_root t)
         end;
         assert (rigid t)
       end;
       ())
    node

let rigidify node =
  let inert = inert_under_nodes [node] in
  (* Even if we rigidify nodes bottom-up, the rigidification may break
     the node invariants : in the `rigidify_gen` case, we may rigidify
     a node that has instantiables descendants; in that case, the
     instantiability information associated to those descendants
     becomes invalid.

     We therefore added a top-down recomputation pass for the
     instantiability information. *)
  GType.invariant_all_nodes_invariants node
    (fun () ->
       bottom_up ~interior:node ~exist:true
         (fun t ->
            rigidify_inert inert t;
            rigidify_gen t;
            rigidify_existentials t;
            rigidify_annot t)
         node;
       top_down ~interior:node ~exist:true
         (fun t -> recompute_instantiable (U.find t))
         node)
    ();
  let () = check_rigidification node in
  ()

(** Ordered binding edges : to each node, we associate the list of its
    bound nodes, in the leftmost-lowermost partial order used for the
    translation *)
let ordered_inverse_binding_edges () node =
  (* The former implementation maintained a table of inverse binding
     edges, to cache them instead of recompute them at each call. It
     was full of bugs. For simplicity, they're not simply recomputed.

     The main problem wich makes caching binding edges dangerous is
     that new nodes are added during the translation process. Hacks
     were added to recompute the information for new nodes, but the
     information that have been copmuted once may become invalid in
     the future. That is, when we reaccess a list of inverse binding
     edges we have computed before, it can happen that some of the
     recorded edges have become "rotten" :
     - they have been unified to a rigid edge, hence became rigid
     themselves
     - two binding edges have been unified, so there is a duplication
     in the list

     It is likely that a carefully crafted cached implementation is
     possible : most part of the translation preserve the invariant
     that the new nodes "vanish" after the translation pass, that is
     get unified to older nodes; perhaps it is thus not necessary to
     consider them when computing inverse binding edges.

     For now, we'll use a slower non-cached implementation.  *)

  let list = ref [] in
  ordered_visit ~node
    (fun t ->
       if non_root t
         && eqrepr (bound t) node
         && not (rigid t) then
           list := t :: !list);
  List.rev !list



(* Remark : On lazy computation of node properties

   Most node properties and associated data (structural interiors, but
   also names (see below)) are memoized into tables. This can be
   important for performances (memoization), but also for
   correctness : it is crucial that at most one name is given to each
   node.

   Most of those properties are computed once and for all, before
   being used. They are usually computed only in a structural subtree
   of the graph, eg. inside a specific presolution, by doing a dps
   iteration on the root of the presolution.

   It is however important that some properties are computed 'on
   demand', 'lazily' : in situations involving expansions, new nodes
   can appear during the computation, so it is not possible to
   initialize the data for all nodes upfront.
*)


(** Give names to nodes;

    For expression translation, only 'named nodes' (as defined in the
    thesis : regular node flexibly bound on a gen node) need to be
    named. However, the translation of types will also want to express
    quantification on non-named nodes (you want to translate the type
    of a reg node wich has nodes bound on it), so we give names to all
    instantiable reg nodes.

    In the situations were only named nodes need to be named, the
    implementation should not assume accessing the name of a non-named
    node will fail. For better invariant checking, it is advised to
    check independently of the name access that the 'named_node'
    predicate defined below is verified.
*)
let named_node t =
  reg_node t && non_root t && fst (flags t) = Flexible && gen_node (bound t)

let names_table () =
  let names = Table.create 10 in
  (* see remark 'On lazy computation of node properties'; this
     property may be used in expanded subtrees, to compute type
     translations needed when translating a flexible non-root Raise *)
  fun t ->
    (* assert (named_node t); *)
    try Table.find names t
    with Not_found ->
      let name = X.tbind () in
      Table.init names t name;
      name

(** Translation environments *)
module ValueMap = AST.ValueMap

type env =
  { tvar : gtype -> X.tvar;
    evar : X.evar ValueMap.t;
    bound_nodes : gtype -> gtype list }

let env_init root =
  ignore root;
  { tvar = names_table ();
    evar = ValueMap.empty;
    bound_nodes = ordered_inverse_binding_edges () }

let tbound_quant bounds = (* ∀(Γ) *)
  List.fold_right (fun (alpha, sigma) -> X.tbound alpha sigma) bounds
let tyabs_quant bounds = (* Λ(Γ) *)
  List.fold_right (fun (alpha, sigma) -> X.tyabs alpha sigma) bounds

let translate_const t =
  X.tconst
    (match t with
    | Int -> `Int
    | Unit -> `Unit
    | Bool -> `Bool)

(** Translation from graphic constraint to xMLF types *)
let rec translate_type env (a : gtype) : X.typ' = (* S_χp(n) *)
  (* constructor translation *)
  let constr = match constr a with (* χp(n) *)
    | Bot _ -> (function [] -> X.tbot | _ -> assert false)
    | Arrow -> (function [t1;t2] -> X.tarrow t1 t2 | _ -> assert false)
    | Forall _ -> (function [_t1; t2] -> t2 | _ -> assert false)
    | Constant t -> (function [] -> translate_const t | _ -> assert false)
    | Lambda (_, _) | Apply (_, _) ->
        let loc = (gen_info a).expr.Locations.loc in
        FeatureErrors.feature_error (FeatureErrors.XmlfOmega loc)
    | Gen (_, _) -> (function [t] -> t | _ -> assert false) in
  (* quantifier prefix computation : B(n_1), .., B(n_k) *)
  let quant = tbound_quant (translate_bounds env a) in
  (* complete node translation *)
  quant (constr (List.map (translate_child env) (edges a)))
and translate_child env t =
  (* children translation : V(n.i) *)
  if rigid t then translate_type env t
  else X.tvar (env.tvar t)
and translate_bounds env t = (* (≥ → n) *)
  let bound t' =
    let name = env.tvar t' in
    let translation = translate_type env t' in
    (name, translation) in
 List.map bound (env.bound_nodes t)

let translate_subtype env (a : gtype) = (* S'_χp(n) *)
  if named_node a then X.tvar (env.tvar a)
  else translate_type env a

let subterm_type env a' = (* Typ(a') *)
  let bounds = translate_bounds env a' in
  tbound_quant bounds (translate_subtype env a')



(** Translation of normalized instance derivations into type computations *)
module Context = struct

  (* Idée (non implémentée) de représentation des contextes qui n'est
     pas dans la thèse : au lieu d'avoir un pas de contexte par
     quantificateur, on pourrait avoir des pas de contexte de la forme
     Access(n) = (`Inner; `Outer^n) : un seul pas pour descendre d'un
     noeud à l'un de ses fils (noeuds bindés), numérotés par
     position. Ça permettrait une représentation plus naturelle, et on
     pourrait retrouver la propriété C_m_n = C_m_n'.C_n'_n qui n'est
     en fait pas vraie avec la définition actuelle

     Autre possibilité qui change moins de choses : aujourd'hui on
     représente C_m_n comme l'intervalle ]m; n[ : la racine n'est pas
     représentée, et on descend "juste avant" le noeud n. On pourrait
     choisir la représentation ]m; n] où on descend sur le noeud n, et
     pas juste avant. On peut récupérer la propriété
     C_m_n'.C_n'_n = ]m;n']∪]n';n] = ]m;n] = C_m_n, et pour se placer
     "juste avant" il suffit de faire (List.tl path) (où les chemins
     sont représentés dans les listes); ce n'est pas défini pour la
     racine, ce qui est un invariant déjà vérifié. *)

  type context_step = [ `Inner | `Outer of gtype ]
  type context = context_step list

  module HashedCont = struct
    type t = context
    let hash_step = function
      | `Inner -> `Inner
      | `Outer t -> `Outer (id t)
    let hash context = Hashtbl.hash (List.map hash_step context)
    let equal cont cont' = hash cont = hash cont'
  end
  module ContTable = Hashtbl.Make(HashedCont)

  type context_env =
    { node_of_path : gtype ContTable.t
    ; path_of_node : context Table.t
    ; name_of_node : X.tvar Table.t }

  let print_path path =
    let print = function
      | `Inner -> "In"
      | `Outer t -> Printf.sprintf "Out %d" (id t) in
    String.concat ";" (List.map print path)

  let apply (env : context_env) (context : context) type_computation =
    let step phi = function
      | `Inner -> X.inner phi
      | `Outer n -> X.outer (Table.find env.name_of_node n) phi in
    List.fold_left step type_computation context

  let context_tables env root =
    let path_of_node : context Table.t = Table.create 10 in
    let node_of_path : gtype ContTable.t = ContTable.create 10 in
    let name_of_node : X.tvar Table.t = Table.create 10 in
    let register node path =
      Table.init path_of_node node path;
      ContTable.add node_of_path path node in
    let rec build context node =
      (* Each time we descend into a bound node, we add an Inner
         context. Each time we go to the next bound of the node, we
         add an Outer context. *)
      let traverse context sibling =
        register sibling context;
        build (`Inner :: context) sibling;
        Table.init name_of_node sibling (X.tbind ());
        (`Outer sibling :: context) in
      let children = env.bound_nodes node in
      ignore (List.fold_left traverse context children) in
    build [] root;
    { node_of_path = node_of_path
    ; path_of_node = path_of_node
    ; name_of_node = name_of_node }

  let to_node env p = ContTable.find env.node_of_path p
  let of_node env n = Table.find env.path_of_node n
  let name env n = Table.find env.name_of_node n

  (* On utilise split_path quand on Raise un noeud; il s'agit de
     trouver le contexte du noeud avant lequel on va placer la
     nouvelle quantification (celle correspondant à la nouvelle
     flèche, plus haute); dans la thèse de Boris, ce noeud est défini
     de façon compliqué (le plus petit des fils du grand-père du noeud
     qui sont plus grands que le noeud) mais indépendante de l'ordre
     total choisi sur les noeuds; en pratique, dans le cas de l'ordre
     leftmost-outermost, c'est toujours le père du noeud bindé. On
     récupère le contexte amenant au père en remontant le contexte du
     fils jusqu'à trouver un `Inner. *)
  let rec split_path_at_bound = function
    | [] -> assert false
    | `Inner :: path -> (path, [`Inner])
    | `Outer n :: path ->
        let (before, after) = split_path_at_bound path in
        (before, `Outer n :: after)
end


open GInstance
let translate_inst env (source, inst_mode, destination) =
  let type_constructor = function
    | Bot _ -> X.tbot
    | Forall _ -> X.tbot
    | Arrow -> (* ∀(α≥⊥) ∀(β≥⊥) α → β *)
        X.tbound_h X.tbot (fun alpha ->
          X.tbound_h X.tbot (fun beta ->
            (X.tarrow alpha beta)))
    | Constant const -> translate_const const
    | Lambda (_, _) | Apply (_, _) ->
        FeatureErrors.feature_error
          (FeatureErrors.XmlfOmega Locations.dummy_loc)
    | Gen _ -> assert false in

  let translate_op root =
    let context = Context.context_tables env root in
    let c_r n phi =
      let path = Context.of_node context n in
      Context.apply context path phi in
    let bot tau = X.bot (type_constructor tau) in
    (* interior hyp use context variables
       exterior hyp use environment variables *)
    let in_hyp n = X.hyp (Context.name context n) in
    let ex_hyp n = X.hyp (env.tvar n) in
    fun op ->
      (* Printf.printf "Instance (%d, %d) under %d : %s\n%!" *)
      (*   (id source) (id destination) *)
      (*   (id root) (GInstance.print op); *)
      (* let log_rigid () = print_endline "rigid" in *)
      (* let log_root () = print_endline "root" in *)
      (* let log_inner () = print_endline "inner" in *)
      let log_rigid, log_root, log_inner = ignore, ignore, ignore in
      match op with
      (* translating an operation on a rigid node *)
      | ( Raise n
          | Merge (n, _)
          | RaiseMerge (n, _) ) when rigid n -> log_rigid (); X.refl
      | Weaken n when rigid n -> log_rigid (); X.refl
      | Graft (_, n) when rigid n -> log_rigid (); assert false

      (* translating an operation on the expansion root *)
      | Graft (tau, r) when eqrepr r root -> log_root (); bot tau
      | RaiseMerge (r, n) when eqrepr r root -> log_root (); ex_hyp n
      | Weaken r when eqrepr r root -> log_root (); X.refl
      | Raise r | Merge (r, _) when eqrepr r root -> log_root (); assert false

      (* translating an operation on a flexible node different from the root *)
      | Graft (tau, n) -> log_inner (); c_r n (X.inner (bot tau))
      | RaiseMerge (n, n') -> log_inner ();
          c_r n (X.trans (X.inner (ex_hyp n')) X.elim)
      | Merge (n, n') -> log_inner ();
          c_r n (X.trans (X.inner (in_hyp n')) X.elim)
      | Weaken n -> log_inner ();
          c_r n X.elim
      | Raise n -> log_inner ();
          let path_r_n = Context.of_node context n in
          let path_r_n', path_n'_n =
            Context.split_path_at_bound path_r_n in
          let () = (* only a verification check *)
            (* TODO find the bug here.
               Provoking entry :
               let rec mult a b = if b = 0 then 0 else a + mult a (b - 1) in mult 2 4
             *)
            let n' = Context.to_node context path_r_n' in
            (* Printf.eprintf "r:%d\tn':%d\tn:%d\n" *)
            (*   (id root) (id n') (id n); *)
            (* Printf.eprintf "r->n : [%s]\nr->n' : [%s]\nn'->n : [%s]\n\n%!" *)
            (*   (Context.print_path path_r_n) *)
            (*   (Context.print_path path_r_n') *)
            (*   (Context.print_path path_n'_n); *)
            let contexts_n' = Context.context_tables env n' in
            (* List.tl because contexts_n' start from n' instead of
               *just before* n' like path_n'_n *)
            assert (Context.of_node contexts_n' n = List.tl path_n'_n) in
          let c_r_n' = Context.apply context path_r_n' in
          let c_n'_n = Context.apply context path_n'_n in
          let tau_n = translate_type env n in
          let beta = X.tbind () in
          c_r_n'
            (X.trans
               (X.trans X.intro (X.inner (X.bot tau_n)))
               (X.outer beta (c_n'_n (X.trans (X.inner (X.hyp beta)) X.elim))))
  in

  let type_computation =
    let tycomp = ref X.refl in
    let add phi = tycomp := X.trans !tycomp phi in
    let recorder source op = add (translate_op source op) in
    try
      (* translation invariant : while the translation internally expand
         presolutions (twice) to compute the instance derivation, no fresh
         node is left in the wild : all created nodes are unified to
         existing nodes before the end of the translation. *)
      GType.invariant_no_new_node
        (GInstance.normalize_presolution recorder source inst_mode) destination;
      !tycomp
    with Degenerate_instance _ -> X.refl in

  let quantifiers_reordering =
    assert (gen_node source);
    let s1 = env.bound_nodes source in
    let s2 = env.bound_nodes (below_gen source) in
    let s0 = (* ordered nodes bound on either source or below_gen(source) *)
      let li = ref [] in
      ordered_visit ~node:source
        (fun t ->
           if non_root t && not (rigid t)
             && List.mem (id (bound t)) [id source; id (below_gen source)] then
               li := t :: !li);
      List.rev !li in
    if (let ids = List.map id in
        ids (s1 @ s2) = ids s0)
    then X.refl
    else begin
      (* let print_li name li = *)
      (*   print_endline name; *)
      (*   List.iter (fun t -> Printf.printf "%d " (id t)) li; *)
      (*   print_newline () in *)
      (* Printf.printf "quantifiers reordering %d\n%!" (id source); *)
      (* print_li "s1" s1; *)
      (* print_li "s2" s2; *)
      (* print_li "s0" s0; *)
      (* print_li "s1 @ s2" (s1 @ s2); *)
      let open_quant n phi =
        let tau_n = translate_type env n in
        X.trans
          X.intro
          (X.trans
             (X.inner (X.bot tau_n))
             (X.outer (env.tvar n) phi)) in
      let close_quant n =
        X.trans (X.inner (X.hyp (env.tvar n))) X.elim in
      List.fold_right open_quant s0
        (List.fold_right X.trans (List.map close_quant (s1 @ s2)) X.refl)
    end in

  X.trans quantifiers_reordering type_computation

(** Translation from graphic constraint to xMLF expressions *)
let rec translate_expr env (t : gtype loc) : X.exp' =
  let t = t.obj in
  let quant = tyabs_quant (translate_bounds env t) in
  let inst (a : gtype) (b : gtype) = (a, `Implicit, b) in
  let expl_inst (a : gtype) (b : gtype) = (a, `Explicit, b) in
  let sigma a = translate_subtype env a in
  let _T ?(env'=env) a = translate_expr env' a in
  let _Phi inst = translate_inst env inst in
  (* quantifiers reordering φ(a) are actually included in the _Phi
     function :  if 'a' is an instance by 'e', _Phi(e) is
     [φ(a); Φ(e)] *)
  let var node = X.evar (ValueMap.find node env.evar) in
  match constr t with
    | Bot _ | Arrow | Constant (Int | Unit | Bool) | Forall _
    | Lambda (_, _) | Apply (_, _) -> assert false (* gen node assumed *)
    | Gen (_,{expr={obj=term;loc=loc}}) ->
	begin match term with
	  | `Value (`VAL None, _x) -> assert false

          | `Value (`LAM, x) -> var x
	      (* T(x) = x    if x is λ-bound *)

	  | `Value (`VAL (Some tg), x) ->
              assert (root tg);
              (* free variable, taken in global en *)
	      let e = inst tg (below_gen t) in
              let _Phi_e = _Phi e in
              (* what should var x be ? *)
              if true then
                FeatureErrors.feature_error
                  (FeatureErrors.XmlfGlobalVal loc);
	      quant (X.tycomp (var x) (_Phi_e))
		(* T(x) = Λ(Γg) x[φ(a); Φ(e)] *)

	  | `Value (`LET t', x) ->
	      let e = inst t'.obj (below_gen t) in
              let _Phi_e = _Phi e in
	      quant (X.tycomp (var x) (_Phi_e))
		(* T(x) = Λ(Γg) x[φ(a); Φ(e)] *)

	  | `Abs (x, a) ->
              let (n, n2) = below_arrow (below_gen t) in
              let e = inst a.obj n2 in
              let x' = X.ebind () in
              let env' = {env with evar = ValueMap.add x.obj x' env.evar} in
              quant (X.lam x' (sigma n) (X.tycomp (_T ~env' a) (_Phi e)))
		(* T(λ(x) a) = Λ(Γg) λ(x:S'(n)) T(a)[φ(a); Φ(e)] *)

	  | `App (a1, a2, arr) ->
              let (arg, _) = below_arrow arr in
              let e1 = inst a1.obj arr in
              let e2 = inst a2.obj arg in
              let trad ai ei = X.tycomp (_T ai) (_Phi ei) in
              quant (X.app (trad a1 e1) (trad a2 e2))
                (* T(a1 a2) = Λ(Γg) T(a1)[φ(a1); Φ(e2)] T(a2)[φ(a2); Φ(e2)] *)

	  | `Let (x, a, b) ->
              let x' = X.ebind () in
              let env' = {env with evar = ValueMap.add x.obj x' env.evar} in
	      let e = inst b.obj (below_gen t) in
	      quant (X.let_ x' (_T a) (X.tycomp (_T ~env' b) (_Phi e)))
		(* T(let x = a in b) = Λ(Γg) let x = T(a) in T(b)[φ(b); Φ(e)] *)

	  | `CoerceCt (_st, tau) ->
              let bounds = translate_bounds env (below_gen t) in
              translate_coerce env bounds tau.obj

          | `TyAbs (_abs, a) ->
              let forall = below_gen t in
              let e = inst a.obj (snd (below_forall forall)) in
              let inner_quant = tyabs_quant (translate_bounds env forall) in
              quant (inner_quant (X.tycomp (_T a) (_Phi e)))

          | `TyApp (a, _tau, arr) ->
              let e = expl_inst a.obj arr in
              quant (X.tycomp (_T a) (_Phi e))

          | `SomeTy (_q, a) ->
              let e = inst a.obj (below_gen t) in
              quant (X.tycomp (_T a) (_Phi e))

          | `Ct (_, ct_type) as ct ->
              let value, typ = match ct_type with
              | `Constr (`Int, []) ->
                  `Int (AST.int_of_ct ct),
                  translate_const GType.Int
              | `Constr (`Unit, []) ->
                  AST.unit_of_ct ct;
                  `Unit, translate_const GType.Unit
              | `Constr (`Bool, []) ->
                  `Bool (AST.bool_of_ct ct),
                  translate_const GType.Bool
              | _ -> assert false in
              X.builtin value (X.to_typ typ)

          | `BuiltinCt builtin ->
              let value = match builtin.obj with
              | AST.OpPlus -> `Arith_op `Plus
              | AST.OpMinus -> `Arith_op `Minus
              | AST.OpEq -> `EqInt
              | AST.OpIfThenElse -> `If
              | AST.OpFix -> `Fix
              | _ -> assert false in
              let typ =
                (* mirrors the {e,g}MLF types from gTranslate.ml *)
                let module X = XAst.DSL in
                let int, bool = X.tconst `Int, X.tconst `Bool in
                let (^>) = X.tarrow in
                let forall_i = X.tbound_h in
                let forall = forall_i X.tbot in
                match value with
                | `Arith_op _ -> int ^> int ^> int
                | `EqInt -> int ^> int ^> bool
                | `If -> bool ^> forall (fun a -> a ^> a ^> a)
                | `Fix ->
                    (* ∀(γ≥∀α∀β.α→β).(γ→γ)→γ *)
                    forall_i
                      (forall (fun a -> forall (fun b -> a ^> b)))
                      (fun c -> (c ^> c) ^> c) in
              X.builtin value (X.to_typ typ)

          (* unsupported terms *)
          | `Type _ -> assert false
	  | `Root -> assert false
	end

and translate_quant env a =
  let translate_bound t =
    assert (named_node t);
    (env.tvar t, translate_type env t) in
  let bounds = List.map translate_bound (env.bound_nodes a.obj) in
  fun term ->
    List.fold_right
      (fun (alpha, sigma) body -> X.tyabs alpha sigma body)
      bounds term

(** Translation of type coercions *)
and translate_coerce env bounds node = (* (:∃̱β.τ) => Λ(β).λ(x:τ)x *)
  (* we use translate_child instead of translate_subtype because we
     are inside a type-graph with no (G) nodes generated by the
     translation of the coercion, hence quantified nodes are not in
     general 'named nodes' (in the sense of "flexibly bound on (G)
     nodes") *)
  let tau = translate_child env node in
  tyabs_quant bounds (X.lam_h tau (fun x -> x))

(** High-level translation *)
let translate graph : XAst.exp =
  let root = graph.Expr.root in
  let () = GSolve.solve_all graph in
  if !Debug.after_gsolve then
    Dot.drum ~name_suffix:"after_gsolve" ~ids:true ~proj:false root;
  GType.invariant_all_nodes_invariants root rigidify root;
  (* Dot.drum ~name_suffix:"graph_rigidified" ~ids:true ~proj:false (find_root root); *)
  flush_all ();
  let exp =
    let env = env_init root in
    GType.invariant_no_new_node
      (fun root -> translate_expr env (Locations.noloc root))
      root in
  XSimplify.simplify (X.to_exp_debug exp)

(** Type erasure (from xMLF back to syntaxic gMLF) *)
let loc e = { Locations.obj = e; Locations.loc = Locations.dummy_loc }

let fresh_var =
  let count = ref (-1) in
  fun () -> incr count; Opaque.string_t ("_v" ^ string_of_int !count)

let gmlf_of_builtin : XAst.builtin -> _ = function
(* TODO factorize `Ct cases with parser *)
| `Unit -> AST.ct_of_unit ()
| `Int i -> AST.ct_of_int i
| `Bool b -> AST.ct_of_bool b
| `EqInt -> `BuiltinCt AST.OpEq
| `If -> `BuiltinCt AST.OpIfThenElse
| `Fix -> `BuiltinCt AST.OpFix
| `Arith_op op ->
    `BuiltinCt (match op with
                | `Plus -> AST.OpPlus
                | `Minus -> AST.OpMinus)

let rec erasure_ env : XAst.exp -> GAst.expr Locations.loc = function
  | `Builtin (b, _ty) -> loc (gmlf_of_builtin b)
  | `TyAbs (_, _, a) | `TyComp (a, _) -> erasure_ env a
  | `App (a1, a2) -> loc (`App (erasure_ env a1, erasure_ env a2))
  | `Lam (x, _, a) ->
      let v = fresh_var () in
      loc (`Abs(loc v, erasure_ (XEnv.add_evar x (`LAM, v) env) a))
  | `Let (x, a, b) ->
      let v = fresh_var () in
      let a' = erasure_ env a in
      let env' = XEnv.add_evar x (`LET a', v) env in
      loc (`Let(loc v, a', erasure_ env' b))
  | `Var (`F _v) -> assert false (* solution : ajouter un marqueur `Free dans gAst *)
  | `Var (`B _ as x) -> loc (`Value (XEnv.find_evar x env))

let erasure = erasure_ XEnv.empty

