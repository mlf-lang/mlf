open Utils

open Locations
open AST
open GAst
open EType
open GType
open Expr
open TypingErrors

open GEnv

let expect_kind expected_kind etype gtype loc =
  if kind gtype <> expected_kind then
    TypingErrors.typing_error
      (TypingErrors.IncorrectKind
         (`Expect (expected_kind, kind gtype), etype, loc))

let expect_apply_kinds etype func arg loc =
  match kind func with
  | K.Arrow (k, _) when k = kind arg -> ()
  | _ ->
    TypingErrors.typing_error
      (TypingErrors.IncorrectKind
         (`Apply (kind func, kind arg), etype, loc))
      

let fomega_feature conf loc =
  if not (Config.is_set conf Config.experimental_fomega) then
    FeatureErrors.feature_error (FeatureErrors.FOmega loc)

(** Translation from syntactic types to graphic types *)
(*
  In Boris's thesis, the translation is described for restricted
  graphic types, in wich the parameters to type constructors such as
  the arrow are only variables: σ→τ was already translated, according
  to the syntaxic sugar conventions, into ∀(α=σ)∀(β≥τ)α→β.

  In the current implementation, we don't have that property:
  polymorphic types may be passed to the translation function. This
  makes the handling of bindings a bit delicate: with restricted
  types, we are sure that both child of an arrow, wich are variables,
  are already bound by a type quantification. 

  When we encounter arrows, we have therefore two case to consider:
  - if the children are variables, don't bind them
  - if the children are not variable, they're unbound; bind them

  In the second case, we follow the convention that the left type of
  the arrow, if polymorphic, must be understood as rigidly bound,
  while the right type is flexibly bound.

  This case handling is done in the maybe_bind function.

  There is another issue with binding during the syntaxic→graphic type
  translation: bound alias. Boris's thesis is a bit evasive about the
  bound alias handling during translation. The basic idea is that when
  we encounter ∀(α≥σ₁)σ₂, we first translate σ₁, then σ₂ in an
  environment where α associates to (σ₁), the graph for σ1. Finally,
  we bind (σ₁) to the head node of (σ₂).  

  There is a subtlety however in the case of bound aliasing. For
  example, if σ₂ is equal to ⊥ → ∀(β≥α)σ₃, the recursive translation
  process will bind (σ₁), the translation for α (in the environment),
  to the head node of (σ₃), according to the bound ∀β. When returning
  from this recursive call, the translation process for ∀(α≥σ₁)σ₂ will
  try to finally bind (σ₁) to (σ₂), to find out that (σ₁) is already
  bound (to (σ₃)) !

  In this case, it is sound to rebind (σ₁) to (σ₂): this amounts to
  raising the binding in an outer context: the bound ∀(β≥α) is
  considered ineffective.

  This case handling is done by bind_bound_variable.
  *)

let maybe_bind (s, t) flags father =
  (* This function is meant to be used under constructors such as
     Arrow *)
  (* If the variables are bound in the environment or
     a `Forall` construction higher in the type, they should
     keep their bound scope. Elsewhere we bind them locally.
   
     See big comment above 
   *)
  match s with
    | `Var _ when not (undef_binder t) -> ()
    | _ -> GType.bind t flags father

let bind_bound_variable v loc tb flags dest =
  (* This function is meant to be used under binding constructors
     (Forall, Lambda), on the bound variable *)
  ignore v;
  if undef_binder tb then begin
    (* we make a special case for when tb==dest : this corresponds to
       the ∀(β)β type, which should be considered equivalent to (⊥),
       hence no actual binding is performed (oresle we would have
       a Cycle error). *)
    if eqrepr tb dest then ()
    else
      GType.bind tb flags dest
  end
  else
    let _ = loc in
    GType.rebind_raise tb flags dest

let type_of_type_expr conf env loc s =
  let module T = Typ in
  let rec type_from env (s0 : AST.type_expr) =
    let result = match s0 with
      | `Bottom ->
          (* syntaxic Bottom must be of kind Star *)
          GType.bot K.Star
      | `Var v ->
          begin
            try T.TMap.find v env.T.local
            with Not_found ->
              typing_error (UnboundTypeVar (v, loc))
          end

      | `Constr (`Arrow, arg) ->
          let s1, s2 = match arg with
            | [s1;s2] -> s1, s2
            | li ->
              let arrow = ETypeConstructors.s_typeconstr "->" in
              TypingErrors.typing_error
                (TypingErrors.IncorrectArity
                   (arrow, 2, List.length li, loc)) in
          let t1 = type_from env s1 in
          let t2 = type_from env s2 in
          expect_kind K.Star s1 t1 loc;
          expect_kind K.Star s2 t2 loc;
          let t_arr = GType.arrow t1 t2 in
          maybe_bind (s1, t1) (Rigid, Free) t_arr;
          maybe_bind (s2, t2) (Flexible, Free) t_arr;
          t_arr

      | `Constr ((`Unit | `Bool | `Int) as const, arg) ->
        assert (arg = []);
        constant (match const with
          | `Unit -> Unit 
          | `Bool -> Bool
          | `Int -> Int)
      | `Constr (`PConstr c, li) ->
          begin match ETypeConstructors.typeconstr_s c, li with
          | "unit", [] -> constant Unit
          | "bool", [] -> constant Bool
          | "int", [] -> constant Int
          | _, _ ->
              TypingErrors.typing_error
                (TypingErrors.UnknownTypeConstructor (c, loc))
          end
      | `Constr ((`Uple _ | `User _), _) ->
        failwith "unsupported constructors"

      | `Forall ((v, bound), s) ->
          let tb, flags =
            match bound with
              | `Bound (flags, b) ->
                let tb = type_from env b in
                expect_kind K.Star b tb loc;
                let fl = graphic_binding_of_syntaxic_binding flags in
                tb, fl
              | `Kind k ->
                GType.bot k, (Flexible, Frozen) in
          let ts = type_from (T.add v tb env) s in
          expect_kind K.Star s ts loc;
          bind_bound_variable v loc tb flags ts;
          ts

      | `Abstraction (b, s) ->
        let tb = type_from env b in
        let ts = type_from env s in
        (* no constraint on tb's kind, as it may be any kind:
           ∀e(φ : ★ → ★). A(φ, σ) *)
        expect_kind K.Star s ts loc;
        let t_forall = GType.forall tb ts in
        let bind a ta = maybe_bind (a, ta) (Flexible, Free) t_forall in
        bind b tb;
        bind s ts;
        t_forall

      | `Apply (f, s) ->
        fomega_feature conf loc;
        let tf = type_from env f in
        let ts = type_from env s in
        expect_apply_kinds s0 tf ts loc;
        let t_app = GType.apply tf ts in
        let bind a ta = maybe_bind (a, ta) (Rigid, Free) t_app in
        bind f tf;
        bind s ts;
        t_app

      | `Lambda ((alpha, `Kind k), sigma) ->
        fomega_feature conf loc;
        let tv = GType.bot k in
        let ts = type_from (T.add alpha tv env) sigma in
        let t_lam = GType.lambda tv ts in
        bind_bound_variable alpha loc tv (Flexible, Frozen) t_lam;
        maybe_bind (sigma, ts) (Flexible, Frozen) t_lam;
        t_lam

    in
    check_node_invariants (U.find result);
    result in

  type_from env s

let type_of_annot conf loc type_envs ((unif_vars, {obj=st}) : coercion) =
  let a = ETypeConstructors.s_typevar "_a" in
  let b = ETypeConstructors.s_typevar "_b" in
  let s =
    `Forall ((a, `Bound ((EType.Rigid, EType.Implicit), st)),
            `Forall ((b, `Bound ((EType.Flex, EType.Implicit), st)),
                    `Constr (`Arrow, [`Var a; `Var b]))) in
  let s2 =
    let of_unif {obj=abs} s =
      `Forall ((abs :> type_abstraction), s) in
    List.fold_right of_unif unif_vars s in
  let t_annot = type_of_type_expr conf loc type_envs s2 in
  let t_node = fst (below_arrow t_annot) in
  t_annot, t_node


(** Global variables translation *)
let close_global_graph gtype meaning gtype_expr : gtype =
  let gen = open_gen () in
  let var = bot ~gen (kind gtype) in
  let ret = close_gen gen var gtype_expr in
  (* We solve the instantiation edge immediately, otherwise we should
     keep track of these instantiation edges during elaboration.
     This also avoids making ret an existential type of the current graph.
     This works because gtype must have no free variable.
     It is also a root node.

     make_root/make_undef : when calling GSolve, it is important that
     the graph type is correctly defined, and in particular has
     a root.  However, close_global_gen must return a node with
     undefined bound, as it is was the user function type_of_expr
     expects. We therefore make_undef after the direct instance resolution.
 *)
  make_root ret;
  GSolve.solve_inst gtype (var, `Implicit, meaning);
  make_undef ret;
  ret

(** Add a `Type (G) node to a syntaxic type translation;
    Used in translation of a[τ] for example *)
let gen_type_of_type_expr conf type_env tau =
  let tau_gen = open_gen () in
  let tau_node =
    let node = type_of_type_expr conf type_env tau.loc tau.obj in
    if not (undef_binder node)
    then node (* degenerate case where τ is a type variable bound higher *)
    else under_gen tau_gen node in
  let res = close_gen tau_gen tau_node
    (with_loc tau (`Type (tau, with_loc tau tau_node))) in
  res

(** Translation from expressions to graphic constraints *)
let type_of_expr conf (global_env : Global.env) (expr : GAst.expr loc) = 
  let type_to_expr = ref G.empty in

  let module M = GMeaning in

  let rec type_of_expr (env : Local.env) (a : GAst.expr loc) : gtype =
    let type_from ~gen env a = under_gen gen (type_of_expr env a) in
    let loc = a.loc in
    let located = with_loc a in
    let gtype = match a.obj with
    | `Value (`VAL _, x) ->
        let tg =
          try Global.EMap.find x env.Local.exp.Exp.global
          with Not_found ->
            typing_error (UnboundVar (Opaque.any_string x, loc)) in
        close_global_graph tg
          (M.VarVal loc)
          (located (`Value (`VAL (Some tg), x)))

    | `Value ((`LAM | `LET _) as binder, x) ->
	let t = Exp.find x env.Local.exp in
	(* NB : no need to catch Not_found particularly carefully, as
	   binding resolutions have already been done in
	   gAst.desugar *)
        let gen = open_gen () in
        let t, v =
          match binder with
          (* rules differ if x is lambda-bound or let-bound *)
          | `LAM -> t, `Value (`LAM, x)
          | `LET binder ->
            let locs = {
              M.var_binding_loc = binder.loc;
              M.var_loc = loc;
            } in
            bot ~gen ~inst:(t, GMeaning.VarLet locs) K.Star,
            `Value (`LET (with_loc binder t), x) in
	close_gen gen t (located v)

    | `Ct (_, `Constr (t, [])) as ct ->
        let const = match t with
        | `Int -> Int
        | `Unit -> Unit
        | `Bool -> Bool in
        let gen = open_gen () in
        let t = constant ~gen const in
        close_gen gen t (located ct)
    | `Ct (_v, _t) -> assert false

    | `Abs (x, a1) ->
        let gen = open_gen () in
        let t_arg = bot ~gen K.Star in
        let t_a1 =
          let env = Local.add_exp x.obj t_arg env in
          type_from ~gen env a1 in
        let t_return = bot ~gen ~inst:(t_a1, M.Abs a1.loc) K.Star in
        let t_func = arrow ~gen t_arg t_return in
        close_gen gen t_func (located (`Abs (x, with_loc a1 t_a1)))

    | `TyAbs ({loc=loc;obj=(alpha, bound)} as abs, a) ->
        let gen = open_gen () in
        let t_arg =
          match bound with
            | `Bound (_, sigma) ->
                let result =
                  type_of_type_expr conf env.Local.typ abs.loc sigma in
                expect_kind K.Star sigma result loc;
                result
            | `Kind k ->
              fomega_feature conf loc;
              bot k in
        let t_a =
          let env = Local.add_typ alpha t_arg env in
          type_from ~gen env a in
        let t_return = bot ~gen ~inst:(t_a, M.TyAbs a.loc) K.Star in
        let t_forall = forall ~gen t_arg t_return in
        let gen =
          close_gen gen t_forall
            (located (`TyAbs (abs, with_loc a t_a))) in
        let () =
          let flex = match bound with
            | `Kind _ ->
                fomega_feature conf loc;
                Flexible
            | `Bound (flags, _) ->
                fst (graphic_binding_of_syntaxic_binding flags) in
          bind_bound_variable alpha abs.loc t_arg (flex, Frozen) gen in
        gen

    | `App (a1, a2) ->
        let gen = open_gen () in
        let t_a1 = type_from ~gen env a1 in
        let t_a2 = type_from ~gen env a2 in
        let t_arg = bot ~gen ~inst:(t_a2, M.app_arg a1 a2) K.Star in
        let t_return = bot ~gen K.Star in
        let t_func = arrow ~gen ~inst:(t_a1, M.app_fun a1 a2) t_arg t_return in
        close_gen gen t_return
          (located (`App (with_loc a1 t_a1, with_loc a2 t_a2, t_func)))

    | `TyApp (e, tau) ->
        let gen = open_gen () in
        let t_e = type_from ~gen env e in
        let t_tau =
          under_gen gen
            (gen_type_of_type_expr conf env.Local.typ tau) in
        (* Do not forgot to add the intermediary t_tau node to the
           type_to_expr map !

           As this map is used to determine the nodes of the graph,
         wich are themselves used to compute the set of constraint
         edge to solve, forgetting that addition caused a serious bug :
         tye type part of type application constraints were never
         resolved *)
        type_to_expr := G.add t_tau a !type_to_expr;
        (* TODO kinding check; this case is actually a bit delicate *)
        let t_arg = bot ~gen ~inst:(t_tau, M.TyAppArg tau.loc) (kind t_tau) in
        let t_return = bot ~gen K.Star in
        let t_forall =
          forall ~gen ~expl_inst:(t_e, M.TyAppFun loc) t_arg t_return in
        close_gen gen t_return
          (located (`TyApp (with_loc e t_e, with_loc tau t_tau, t_forall)))
        
    | `SomeTy ((q : bound_prefix), e) ->
        let type_env', q_with_nodes =
          quantifiers_prefix_translation env.Local.typ q in
        let gen = open_gen () in
        let t_content = type_from ~gen { env with Local.typ = type_env' } e in
        let t_return = bot ~gen ~inst:(t_content, M.SomeIn e.loc) K.Star in
        let gen = close_gen gen t_return
            (located (`SomeTy (q_with_nodes, with_loc e t_content))) in
        close_quantifier_prefix_translation gen q_with_nodes;
        gen

    | `Let (x, a1, a2) ->
        (* The original let-translation is very succint; we use
           a strictly more general form (with one additional gen node)
           wich ease translation by a more transparent treatment of
           binding scopes, as described in the (gMLF -> xMLF) chapter
           of Boris's thesis, "Scopes in a let construct" *)
        let gen = open_gen () in
        let t_a1 = type_from ~gen env a1 in
        let t_a2 =
          let env = Local.add_exp x.obj t_a1 env in
          type_from ~gen env a2 in
        let t_body = bot ~gen ~inst:(t_a2, M.LetBody a2.loc) K.Star in
        close_gen gen t_body
          (located (`Let (x, with_loc a1 t_a1, with_loc a2 t_a2)))

    | `CoerceCt st ->
        let gen = open_gen () in
        let t_annot, t_node =
          type_of_annot conf env.Local.typ a.loc st.obj in
        close_gen gen (under_gen gen t_annot)
          (located (`CoerceCt (st, with_loc a t_node)))

    | `BuiltinCt op ->
        let t const = `Constr (const, []) in
        let int, bool = t `Int, t `Bool in
        let (^>) a b = `Constr (`Arrow, [a; b]) in
        let forall_i, forall_e =
          let binder flex =
            let count = ref 1 in
            fun bound f ->
              let var = EType.var_n !count in
              incr count;
              let flags = (flex, EType.Implicit) in
              `Forall ((var, `Bound (flags, bound)), f (`Var var)) in
          binder EType.Flex, binder EType.Rigid in
        let forall = forall_i `Bottom in
        let (^=>) a b =
          (* arrow with a rigid result type
             instead of the flexible default *)
          forall_e b (fun v -> a ^> v) in
        let sigma =
          type_of_type_expr conf env.Local.typ loc
            (match op with
            | OpPlus | OpMinus -> int ^> int ^> int
            | OpEq -> int ^> int ^> bool
            | OpIfThenElse ->
                (* there is a subtlety in the use of (^=>) instead of
                   (^>) : if the arrow is not rigid, gMLF will
                   generate a flexible node, wich will get weakened
                   during resolution, giving a [&] instantiation in
                   the translated xMLF term. That is correct if the
                   type of the xMLF #If primitive is
                   ∀(β≥∀α.α→α→α) bool→β, but we want to have the
                   simpler type bool→(∀α.α→α→α), so we have to use the
                   rigid arrow here. *)
                bool ^=> forall (fun a -> a ^> a ^> a)
            | OpFix ->
                (* ∀(γ≥∀α∀β.α→β).(γ→γ)→γ *)
                forall_i
                  (forall (fun a -> forall (fun b -> a ^> b)))
                  (fun c -> (c ^> c) ^> c)
            | _ -> assert false) in
        let gen = open_gen () in
        close_gen gen (under_gen gen sigma)
          (located (`BuiltinCt (with_loc a op)))
    in
    type_to_expr := G.add gtype a !type_to_expr;
    gtype

          (* quantifiers_prefix_translation / close_quantifier_prefix_translation

             The way we translate the "some Q in σ" or "some Q in e"
             constructions is slightly unusual. The usual way to do
             would be to create a (G) node, translate the quantifiers,
             and then link them to the (G) node.

             The problem is that, with the "some Q in σ" construct,
             the (G) node content is (σ) translation, therefore we
             can't build the (G) node before translating (σ). But (σ)
             need Q to be already translated in it's environment !

             The solution is to build "floating" nodes for the
             variables in (Q) : their bound stay undef while they're
             put in the translation environment. We then translate the
             expression/type nodes, and finally build the G node and
             bind the (Q) nodes to it.

             Note : there is a subtlety in that some of the floating
             nodes may become bound during the translation. See
             close_quantifier_prefix comment.  *)
  and quantifiers_prefix_translation type_env q =
    let handle (env, q_rev) ({obj=(alpha, `Bound (_, sigma))} as abs) =
      let loc = abs.loc in
      let t_alpha = type_of_type_expr conf env loc sigma in
      expect_kind K.Star sigma t_alpha loc;
      (Typ.add alpha t_alpha env, (abs, t_alpha) :: q_rev) in
    let (type_env', q_rev) =
      List.fold_left handle (type_env, []) q in
    (type_env', List.rev q_rev)

  and close_quantifier_prefix_translation gen q_with_nodes =
    let rebind ({loc=loc;obj=(_alpha, `Bound (flags, _sigma))}, t) =
      let flags = graphic_binding_of_syntaxic_binding flags in
      (* If a variable is bound, it was bound during the translation
         of the prefixed term; therefore they appear syntaxically in
         it, therefore they appear structurally in its translation. We
         still have to raise the binding to give it the correct
         scope. If their bound is undef, we add an existential
         edge. *)
      if undef_binder t then begin
        add_exist t gen;
        rebind_unsafe t flags gen
      end else
        if not (frozen t) then
          rebind_raise t flags gen
        else (* see bind_bound_variable comment *)
          GraphErrors.graph_error
            (GraphErrors.IncompatibleFlags
               (t, loc, GType.flags t, flags)) in
    
    List.iter rebind q_with_nodes
  in

  let tg = type_of_expr (Local.of_global global_env) expr in
  make_root tg;
  set_levels tg;
  (* it is important that the node are given in the correct, bottom-up
     order (hence List.rev). Otherwise, instantiation edges may be
     resolved while there are still pending instance edges in the
     subtree, leading to a constraint duplication. The current
     algorithm (solve each constraint edge once) woudln't work
     anymore.*)
  let nodes = List.rev (G.fold (fun node _ li -> node :: li) !type_to_expr []) in
  global_check_node_invariants tg;
  { root = tg;
    type_to_expr = !type_to_expr;
    nodes = nodes }

(*
   let expr_of_phrase p =
   match p with
   | Expr (e, true) ->  e
   | Val (r, e1, e2) ->  `Let (r, e1, e2)
   | Inductive (_, _) -
   | Alias (_,_) -
   | InlineTypes _
   -> assert false
   | Expr (e, true)
   | Include _
   -> assert false

   | Val of rec_flag * constrained_let_name * source_expr loc ->
   `Let of rec_flag * (constrained_let_name  * 'a loc) * 'a loc
 *)
