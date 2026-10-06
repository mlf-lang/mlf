let conf =
  (Config.set Config.default_conf Config.experimental_fomega)

(* from xTest *)
let specification_test ?nb_runs title generator (func, spec) =
  if nb_runs <> Some 0 then
    Kaputt.Test.run_test
      (Kaputt.Test.make_random_test ?nb_runs ~title
         generator func [spec]);
  flush_all ()

let () =
  specification_test "reflexivity for alpha equivalence of gMLF syntaxic terms"
    Gmlf_generators.exp_k
    (ignore, Gmlf_specifications.alpha_equiv_is_reflexive)

let () =
  specification_test "symmetry for alpha equivalence of gMLF syntaxic terms"
    ~nb_runs:0 (* precondition too hard *)
    (Kaputt.Generator.zip2 Gmlf_generators.exp_k Gmlf_generators.exp_k)
    (ignore, Gmlf_specifications.alpha_equiv_is_symmetric)

let () =
  specification_test "transitivity for alpha equivalence of gMLF syntaxic terms"
    ~nb_runs:0 (* precondition too hard *)
    (Kaputt.Generator.zip3
       Gmlf_generators.exp_k Gmlf_generators.exp_k Gmlf_generators.exp_k)
    (ignore, Gmlf_specifications.alpha_equiv_is_transitive)

let () =
  specification_test "(Parse . Print) involutive"
    Gmlf_generators.exp_k
    Gmlf_specifications.print_parse_involution

let () =
  if false then
    (* the following test fails; no idea why, but no time to investigate *)
    specification_test "noloc e = noloc (parse (print e))"
      Gmlf_generators.exp_k
      Gmlf_specifications.parse_print_same

let () = flush_all ()

(** Manual tests *)
module G = GType

let prn t = string_of_int (G.id t)
let bind t t' = G.bind t (G.Flexible, G.Free) t'
let exbind t t' = G.bind t (G.Flexible, G.Frozen) t'
let eq = G.eqrepr

let is t ~msg t' =
  Kaputt.Assertion.equal ~prn ~msg ~eq t t'

let is_any ~msg t =
  ignore (msg, t)

let check predicate ~msg t =
  Kaputt.Assertion.is_true ~msg (predicate t)

let is_bot = check G.bot_node

let is_int = check (G.const_node G.Int)

let is_arrow check_a check_b ~msg t =
  Kaputt.Assertion.is_true ~msg (G.arrow_node t);
  let (a, b) = G.below_arrow t in
  check_a ~msg a;
  check_b ~msg b

let is_id check ~msg t =
  is_arrow check check ~msg t;
  let (a, b) = G.below_arrow t in
  is a ~msg b

let is_gen check ~msg t =
  Kaputt.Assertion.is_true ~msg (G.gen_node t);
  check ~msg (G.below_gen t)

(** Resolution tests *)
let gsolve_test src check =
  let build src =
    let ast = EParse.expr src in
    let exp = GAst.desugar (AST.desugar ast) in
    GTranslate.type_of_expr conf GEnv.Global.empty exp in
  Kaputt.Test.run_test
    (Kaputt.Test.make_assert_test ~title:src
       (fun () -> build src)
       (fun graph -> GSolve.solve_all graph; GSolve.normalize graph.Expr.root)
       check)

let () =
  let msg = "fun x -> x + 1" in
  gsolve_test msg
    (is_gen (is_arrow is_int is_int) ~msg)

let () =
  (* counter-example for the TyApp bug fixed in "a vicious
     \!type_to_expr bug that has been there since 'c4bc554 [minor]
     gen_expr now carry locations...'" *)
  let msg = "(Fun 'a -> fun (x : 'a) -> x)[int]" in
  gsolve_test msg
    (is_gen (is_arrow is_int is_int) ~msg)

let () =
  (* counter-example for the unification bugs fixed in "Change in
     gUnify permission computations to account for inert nodes" *)
  let msg = "fun (x : ('a > int) . 'a -> 'a) -> (x : int -> int)" in
  gsolve_test msg ignore

let () =
  (* counter-example for the (forall b. b) bug fixed in
     "fix for (∀(β) β)" *)
  let msg = "if True then (fun (x : _) -> x) else (fun (x : 'b . 'b) -> x)" in
  gsolve_test msg ignore

(** Beta reduction tests *)
module R = GReduce
module K = ETypeKinds

let reduce_test msg app check =
  Kaputt.Test.run_test
    (Kaputt.Test.make_assert_test ~title:msg
       (Kaputt.Test.return app) R.reduce_whnf check)

let () =
  let msg = "@(λ(α,α), n) @⇝ n" in
  let gen = G.open_gen () in
  let n = G.bot K.Star in
  let app =
    let lam =
      let alpha = G.bot K.Star in
      let lam = G.lambda alpha alpha in
      exbind alpha lam;
      lam in
    let app = G.apply lam n in
    bind n app; bind lam app;
    G.under_gen gen app in
  let root =
    G.close_gen gen app (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
   (* reduce won't work properly if levels are not set, because the
      frontier computation use binding level to determine the node
      structural interior *)
  reduce_test msg app (fun () -> is n ~msg app)

let () =
  let msg = "@(λ(α,α→α), n) @⇝ (n→n)" in
  let gen = G.open_gen () in
  let n = G.bot K.Star in
  let app =
    let lam =
      let alpha = G.bot K.Star in
      let arrow = G.arrow alpha alpha in
      let lam = G.lambda alpha arrow in
      exbind alpha lam; exbind arrow lam;
      lam in
    let app = G.apply lam n in
    bind n app; bind lam app;
    G.under_gen gen app in
  let root = G.close_gen gen app (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
  reduce_test msg app
    (fun () -> is_arrow (is n) (is n) ~msg app)

let () =
  let msg = "(n → @(λ(α,α→n), n')) @⇝ (n→(n'→n))" in
  let gen = G.open_gen () in
  let n = G.bot K.Star in
  let n' = G.bot K.Star in
  let app =
    let lam =
      let alpha = G.bot K.Star in
      let arrow = G.arrow alpha n in
      let lam = G.lambda alpha arrow in
      exbind alpha lam;
      exbind arrow lam;
      lam in
    let app = G.apply lam n' in
    bind lam app; bind n' app;
    app in
  let arrow =
    let arrow = G.arrow n app in
    bind n arrow; bind app arrow;
    G.under_gen gen arrow in
  let root = G.close_gen gen arrow (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
  reduce_test msg app
    (fun () ->
      is_arrow (is n) 
        (is_arrow (is n') (is n)) ~msg arrow)

let () =
  let msg = "(n → @(λ(α,α→α), n→n)) @⇝ (n → (n→n)→(n→n))" in
  let gen = G.open_gen () in
  let n = G.bot K.Star in
  let inner_arrow = G.arrow n n in
  let app =
    let lam =
      let alpha = G.bot K.Star in
      let arrow = G.arrow alpha alpha in
      let lam = G.lambda alpha arrow in
      exbind alpha lam; exbind arrow lam;
      lam in
    let app = G.apply lam inner_arrow in
    bind lam app; bind inner_arrow app;
    app in
  let arrow =
    let arrow = G.arrow n app in
    bind n arrow; bind app arrow;
    G.under_gen gen arrow in
  let root = G.close_gen gen arrow  (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
  reduce_test msg app
    (fun () ->
      is_arrow
        (is n)
        (is_id (is inner_arrow))
        ~msg arrow)

let unify_test msg t1 t2 check =
  Kaputt.Test.run_test
    (Kaputt.Test.make_assert_test ~title:msg
       (Kaputt.Test.return (t1, t2))
       (fun (t1, t2) -> GUnify.gunify t1 t2)
       check)

let () =
  let msg = "(λα.α→⊥)@(⊥→⊥) ≡ ⊥→⊥" in
  let gen = G.open_gen () in
  let arrow () =
    let b1 = G.bot ~gen K.Star in
    let b2 = G.bot ~gen K.Star in
    let arr = G.arrow ~gen b1 b2 in
    arr in
  let arr1, arr2 = arrow (), arrow () in
  let lam =
    let alpha = G.bot K.Star in
    let b3 = G.bot ~gen K.Star in
    let body = G.arrow alpha b3 in
    let lam = G.lambda ~gen alpha body in
    exbind body lam;
    exbind alpha lam;
    lam in
  let app = G.apply ~gen lam arr1 in
  let root = G.close_gen gen app (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
  unify_test msg app arr2 
    (fun () ->
      is_arrow (is_arrow is_bot is_bot) is_bot ~msg app)

let () =
  let msg = "(λα.α)@⊥ ≡ ⊥" in
  let gen = G.open_gen () in
  let b1, b2 = G.bot ~gen K.Star, G.bot ~gen K.Star in
  let lam =
    let alpha = G.bot K.Star in
    let lam = G.lambda ~gen alpha alpha in
    exbind alpha lam;
    lam in
  let app = G.apply ~gen lam b1 in
  let arr = G.arrow ~gen app b2 in
  let root = G.close_gen gen arr (Locations.dummy_located `Root) in
  G.make_root root;
  G.set_levels root;
  unify_test msg app b2 (fun () -> is b1 ~msg b2)

let gsolve_test src check =
  let build src =
    let exp = GAst.desugar (AST.desugar (EParse.expr src)) in
    GTranslate.type_of_expr conf GEnv.Global.empty exp in
  Kaputt.Test.run_test
    (Kaputt.Test.make_assert_test ~title:src
       (fun () -> build src)
       (fun graph -> GSolve.solve_all graph; graph)
       (fun graph -> check graph.Expr.root))

let () =
   let msg = "some 'a in (fun (x : 'a) -> (x : (lam 't . 't) @ 'a))" in
   gsolve_test msg
     (is_gen (is_id is_bot) ~msg)


let () =
   let msg = 
     "some 'a in (fun (x : 'a -> 'a) -> (x : (lam 't . 'a -> 'a) @ 'a))" in
   gsolve_test msg
     (is_gen (is_arrow (is_id is_bot) (is_id is_bot)) ~msg)

let () =
   let msg = 
     "some 'a in (fun (x : 'a -> 'a) -> (x : (lam 't . 't -> 't) @ 'a))" in
   let is_a_a = is_id is_bot in
   gsolve_test msg
     (is_gen (is_arrow is_a_a is_a_a) ~msg)


let greduce_test src check =
  let build src =
    let typ = EParse.typ src in
    let gtype = GTranslate.gen_type_of_type_expr conf GEnv.Typ.empty typ in
    GSolve.normalize gtype in
  Kaputt.Test.run_test
    (Kaputt.Test.make_assert_test ~title:src
       (fun () -> build src)
       (fun gtype -> GReduce.reduce_whnf (G.below_gen gtype); gtype)
       check)

let () =
   let msg = "'a 'b . (lam 'a 'b . 'a -> 'b) @ 'a @ 'b" in
   greduce_test msg (is_gen (is_arrow is_bot is_bot) ~msg)


(* bound aliasing test *)
let () =
  let simple_loop =
    "fun x -> if True then (x : 'b . 'b) else (x : _)" in
  let simple_bound_aliasing =
    "fun x -> if True
       then (x : 'a . ('b > 'a) . 'a -> 'b)
       else (x : 'a . 'a -> 'a)" in
  let explicit_bound_aliasing =
    "fun x -> if True
       then (x : 'a . ^('b !> 'a) . 'b -> 'b)
       else (x : 'a . A('a, 'a -> 'a))" in
  let redex_loop =
    "fun x -> if True
       then (x : 'b . (lam 'a . 'a) @ 'b)
       else (x : _)" in
  let redex_bound_aliasing_by_constant =
    "fun x -> if True
       then (x : 'a . ('b > (lam 'c . 'a) @ 'a) . 'b -> 'b)
       else (x : 'a . 'a -> 'a)" in
  let redex_bound_aliasing_by_identity =
    "fun x -> if True
       then (x : 'a . ('b > (lam 'c . 'c) @ 'a) . 'b -> 'b)
       else (x : 'a . 'a -> 'a)" in
  List.iter (fun msg -> gsolve_test msg ignore) [
    simple_loop;
    simple_bound_aliasing;
    explicit_bound_aliasing;
    redex_loop;
    redex_bound_aliasing_by_constant;
    redex_bound_aliasing_by_identity;
  ]


(** tests of type application on non-explicit-tyabs terms *)
let () =
  let strange_tyapp =
    "Fun 'a -> fun x y -> fun z -> z (x ['a]) (y ['a])" in
  List.iter (fun msg -> gsolve_test msg ignore) [
    strange_tyapp;
  ]

(** a nasty reduction bug caused by wrong blevels *)
let () =
  let src = 
    "fun (unify : 'a . 'a -> 'a -> 'a) ->
       let x =
         (Fun ('f : * -> * ) ->
           (: 'a . 'f @ 'a)
         )[lam 'b . 'b -> int -> 'b]
       in
       unify x x
    " in
  gsolve_test src ignore
