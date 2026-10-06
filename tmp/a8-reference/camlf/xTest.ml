open XAst
open Xmlf_generators
open Kaputt

let conf = Config.default_conf

let test title test_func test_check =
  Test.run_test
    (Test.make_assert_test ~title
       (Test.return ()) test_func test_check);
  ignore (test_func ());
  flush_all ()

let all_pairs ?eq ?printer li =
  let check_pair ((a, msg), b) =
    Assertion.equal ?eq ?prn:printer ?msg a b in
  List.iter check_pair li

let all_typ_pairs li = all_pairs ~printer:typ_printer li
let all_exp_pairs li = all_pairs ~printer:exp_printer li

open XAst.DSL

let free_var a =
  let var = XEnv.EVar.fvar a in
  let exp = `Var (`F var) in
  var, exp, of_exp exp

let free_tvar tau =
  let tvar = XEnv.TVar.fvar tau in
  let typ = TVar (`F tvar) in
  tvar, typ, of_typ typ

let vsigma,sigma,sigma' = free_tvar (Symbol.sigma ())
let vtau, tau, tau' = free_tvar (Symbol.tau ())
let vy,y,y' = free_var "y"
let vz,z,z' = free_var "z"


(** Typing tests *)
let verbose_typer env exp' =
  XTyper.verbose_typer env (to_exp exp')

let type_id =
  let alpha = tbind () in
  tbound alpha tbot (tarrow (tvar alpha) (tvar alpha))

let test_id_monomorphique () =
  (* let id = λ(x:τ) x *)
  let env = XEnv.toplevel ~ft:[vtau,TBot] ~fe:[] in
  let x = ebind () in
  let id = lam x tau' (evar x) in
  [verbose_typer env id, to_typ (tarrow tau' tau')]

let () =
  test "id_monomorphique"
    test_id_monomorphique all_typ_pairs

let boris_id =
  (* Λ(α≥⊥) λ(x:α) x *)
  let x, alpha = ebind (), tbind () in
  tyabs alpha tbot (lam x (tvar alpha) (evar x))

let test_id_polymorphique () =
  let type_id_fun = verbose_typer XEnv.empty boris_id in

  (* id[∀(≥▹τ); &] *)
  let env = XEnv.toplevel ~ft:[vtau,TBot] ~fe:[] in
  let id_tau = tycomp boris_id (of_tycomp (ty_app tau)) in
  let type_id_tau = verbose_typer env id_tau in

  let env = XEnv.toplevel ~ft:[vtau,TBot] ~fe:[vy,tau] in
  let id_y = app id_tau y' in
  let type_y = verbose_typer env id_y in

  [ type_id_fun, to_typ type_id;
    type_id_tau, to_typ (tarrow tau' tau');
    type_y, tau ]

let () =
  test "id_polymorphique"
    test_id_polymorphique all_typ_pairs

let boris_choose =
  let beta, x, y = tbind (), ebind (), ebind () in
  (* Λ(β≥⊥) λ(x:β) λ(y:β) x *)
  (* should be (if true then x else y), but we lack conditionals *)
  tyabs beta tbot (lam x (tvar beta) (lam y (tvar beta) (evar x)))

let boris_choose_id =
  let beta = tbind () in
  tyabs beta type_id
    (app
       (tycomp boris_choose (tyapp (tvar beta)))
       (tycomp boris_id (hyp beta)))

let boris_choose_id_mono_tycomp =
  let alpha = tbind () in
  (* ⅋; ∀(α≥) (∀(≥α); &) *)
  trans intro (outer alpha (trans (inner (tyapp (tvar alpha))) elim))

let boris_choose_id_mono_typ =
  let gamma' = tbind () in
  let gamma = tvar gamma' in
  tbound gamma' tbot (tarrow (tarrow gamma gamma) (tarrow gamma gamma))

let test_boris_choose_mono () =
  let beta' = tbind () in
  let beta = tvar beta' in
  List.map (fun (a, b) -> verbose_typer XEnv.empty a, to_typ b)
    [ boris_choose, tbound beta' tbot (tarrow beta (tarrow beta beta));
      boris_choose_id, tbound beta' type_id (tarrow beta beta);
      tycomp boris_choose_id boris_choose_id_mono_tycomp,
        boris_choose_id_mono_typ ]

let () =
  test "test_boris_choose_mono"
     test_boris_choose_mono all_typ_pairs


let test_environment_access_bug () =
  let alpha, beta, gamma, x = tbind (), tbind (), tbind (), ebind () in
  let test =
      (tyabs alpha tbot
         (tyabs beta (tvar alpha)
            (lam x (tvar beta)
               (tyabs gamma tbot (evar x))))) in
  let typ =
    tbound alpha tbot
      (tbound beta (tvar alpha)
         (tarrow (tvar beta)
          (tbound gamma tbot (tvar beta)))) in
  [verbose_typer XEnv.empty test, to_typ typ]

let () =
  test "test_environment_access_bug"
    test_environment_access_bug all_typ_pairs

(** Reduction test *)
let verbose_reducer ?type_check exp' =
  XReduce.verbose_reducer ?type_check (to_exp exp')

let test_reduction_1 () =
  let a =
    let alpha, x, y = tbind(), ebind(), ebind() in
      tyabs alpha sigma'
	(lam x
	   (tarrow (tvar alpha) (tvar alpha))
	   (lam y tbot
	      (app
		 (tycomp (evar y) (bot (tarrow (tvar alpha) (tvar alpha))))
		 (tycomp z' (hyp alpha))))) in
  let expected_result =
    let x, y = ebind (), ebind () in
      lam x (tarrow sigma' sigma')
	(lam y tbot
	   (app
	      (tycomp (evar y) (bot (tarrow sigma' sigma'))) z')) in
  [ verbose_reducer (tycomp a elim), to_exp expected_result ]

let () =
  test "test_reduction_1"
   test_reduction_1 all_exp_pairs

let test_reduction_2 ~type_check () =
  let alpha, x, y = tbind (), ebind (), ebind () in
  let int = ftvar "int" in
  ignore(verbose_typer XEnv.empty
	   (tycomp boris_choose_id boris_choose_id_mono_tycomp));
  List.map (fun (a, b) -> verbose_reducer ~type_check a, to_exp b)
  [ ( tycomp boris_choose_id (trans (inner (tyapp int)) elim),
      lam y (tarrow int int) (lam x int (evar x)) );

    ( tycomp boris_choose_id elim,
      lam y
	(tbound alpha tbot (tarrow (tvar alpha) (tvar alpha)))
	(tyabs alpha tbot (lam x (tvar alpha) (evar x))) );

    ( tycomp boris_choose_id boris_choose_id_mono_tycomp,
      tyabs alpha tbot
	(lam y
	   (tarrow (tvar alpha) (tvar alpha))
	   (lam x (tvar alpha) (evar x))) ) ]

let () =
  test "test_reduction_2 (exemples de boris : choose_id)"
    (test_reduction_2 ~type_check:false) all_exp_pairs

let () =
  test "test_reduction_2, with continuous type checking"
    (test_reduction_2 ~type_check:true) all_exp_pairs

let test_subst_tycomp_counterexamples () =
  let x = fevar "x" in
  let alpha, beta = tbind (), tbind () in
  let in_context = tyabs alpha tbot in
  let phi = hyp alpha in
  let name1 = "Λ(α≥⊥) (Λ(β≥⊥) x[α◃])[&] —λ⇝ Λ(α≥⊥) x[α◃]" in
  let exp1 =
    tycomp
      (tyabs beta tbot (tycomp x phi))
      elim in
  let reduced_exp1 = tycomp x phi in
  let name2 = "Λ(α≥⊥) (Λ(β≥⊥) x[α◃])[∀(≥ε)] —λ⇝ Λ(α≥⊥)Λ(β≥⊥) x[α◃]" in
  let exp2 =
    tycomp
      (tyabs beta tbot (tycomp x phi))
      (inner refl) in
  let reduced_exp2 = tyabs beta tbot (tycomp x phi) in
  let reduce = XReduce.reduce_context XReduce.reduce_lambda in
  ignore (name1, exp1, reduced_exp1);
  List.map (fun (name, exp, reduced_exp) ->
    (reduce (to_exp (in_context exp)), Some name),
    to_exp (in_context reduced_exp))
    [
     (* (name1, exp1, reduced_exp1); *)
     (name2, exp2, reduced_exp2);
    ]

let () =
  test "test_subst_tycomp_counterexamples"
   test_subst_tycomp_counterexamples all_exp_pairs

(** Translation tests *)
let verbose_translater ?(type_check=false) str =
  let log = Buffer.create 10 in
  Printf.bprintf log "Translating '%s'\n%!" str;
  let exp = EParse.expr str in
  let exp = GAst.desugar (AST.desugar exp) in
  let graph = GTranslate.type_of_expr conf GEnv.Global.empty exp in
  let xexpr = XTranslate.translate graph in
  Printf.bprintf log "\t%s\n%!" (XPrint.doc (XPrint.exp XEnv.empty xexpr));
  if type_check then begin
    try
      let typ = XTyper.type_eval XEnv.empty xexpr in
      Printf.bprintf log "\t: %s\n" (XPrint.doc (XPrint.typ XEnv.empty typ))
    with
      | XTyper.Type_error (env, error) ->
          Printf.bprintf log "%s\n"
            (XPrint.doc (XPrint.type_nonsequent env error))
      | XTyper.Tycomp_error (env, typ, tycomp) ->
          Printf.bprintf log "%s\n"
            (XPrint.doc (XPrint.tycomp_nonsequent env typ tycomp))
  end else Buffer.add_char log '\n';
  xexpr, Some (Buffer.contents log)

let test_translation_1 ?type_check () =
  let alpha, beta, gamma = tbind (), tbind (), tbind () in
  let x, y, z = ebind (), ebind (), ebind () in
  let (!!) = tvar in
  let (!?) = evar in
  let e_app0 = "fun x -> x" in
  let x_app0 = tyabs alpha tbot (lam x !!alpha !?x) in
  let e_app1 = "fun x y -> x y" in
  let x_app1 =
    tyabs alpha tbot
      (tyabs beta tbot
            (lam x (tarrow !!alpha !!beta)
               (lam y !!alpha
                  (app !?x !?y)))) in
  let e_app2 = "fun x y z -> x y z" in
  let x_app2 =
    tyabs alpha tbot
      (tyabs beta tbot
         (tyabs gamma tbot
            (lam x (tarrow !!alpha (tarrow !!beta !!gamma))
               (lam y !!alpha
                  (lam z !!beta
                     (app (app !?x !?y) !?z)))))) in
  List.map
    (fun (e_app, x_app) -> verbose_translater ?type_check e_app, to_exp x_app)
    [ e_app0, x_app0;
      e_app1, x_app1;
      e_app2, x_app2 ]

let () =
  test "test_translation_1 : various simple identities/applications"
    (test_translation_1 ~type_check:true) all_exp_pairs

let test_translation_2 ?type_check () =
  let alpha, beta, gamma = tbind (), tbind (), tbind () in
  let x, y = ebind (), ebind () in
  let (!!) = tvar in
  let (!?) = evar in
  let e_app1 = "fun x y -> y" in
  let x_app1 =
    tyabs alpha tbot
      (tyabs beta (tbound alpha tbot (tarrow !!alpha !!alpha))
         (lam x !!alpha
            (tycomp
               (tyabs gamma tbot
                  (lam y !!gamma !?y))
               (hyp beta)))) in
  let e_app2 = "fun x y -> x" in
  let x_app2 =
    tyabs alpha tbot
      (tyabs beta (tbound gamma tbot (tarrow !!gamma !!alpha))
         (lam x !!alpha
            (tycomp
               (tyabs gamma tbot
                  (lam y !!gamma !?x))
               (hyp beta)))) in
  List.map
    (fun (e_app, x_app) -> verbose_translater ?type_check e_app, to_exp x_app)
    [ e_app1, x_app1;
      e_app2, x_app2 ]

let () =
  test "test_translation_2 : unused variables"
    (test_translation_2 ~type_check:true) all_exp_pairs

let test_translation_3 ?type_check () =
  let alpha, beta, gamma, delta = tbind (), tbind (), tbind (), tbind () in
  let x, y, z = ebind (), ebind (), ebind () in
  let (!!) = tvar in
  let (!?) = evar in
  let e_app = "fun x y -> (fun z -> x) y" in
  let x_app =
    tyabs alpha tbot
      (tyabs beta (tbound beta tbot (tarrow !!beta !!alpha))
         (lam x !!alpha
            (tycomp
               (tyabs gamma tbot
                  (lam y !!gamma
                     (app
                        (tycomp
                           (tyabs delta tbot (lam z !!delta !?x))
                           (trans (inner (hyp gamma)) elim))
                        !?y)))
               (hyp beta)))) in
  List.map
    (fun (e_app, x_app) -> verbose_translater ?type_check e_app, to_exp x_app)
    [ e_app, x_app ]

let () =
  test "test_translation_3 : inner merge type computation"
    (test_translation_3 ~type_check:true) all_pairs

let test_translation_well_typed e_app () =
  let xexp, err = verbose_translater ~type_check:true e_app in
  if Xmlf_specifications.well_typed xexp then true
  else begin
    (match err with None -> ()
       | Some err -> print_endline err);
    false
  end

let () =
  let test_app n app =
    test (Printf.sprintf "test_translation_%d : %s" n app)
      (test_translation_well_typed app) Kaputt.Assertion.is_true in
  test_app 4 "(fun x -> x) (fun y -> y)";
  test_app 5 "(fun x -> x) (fun x -> x)"

let test_cycles () =
  List.map
    (fun e ->
       try
         let _ = verbose_translater e in
         false
       with
         | GType.Cycle _ -> true
         | GUnify.Errors.UnifError (_, GUnify.Errors.Cycle _, _) -> true)
    [ "fun x -> x x"
    (* ; "fun (x : 'a . 'a) -> x" *) ]

let () =
  test "test_translation_cycles" test_cycles
    (List.iter Kaputt.Assertion.is_true)

(** Specification-based testing *)
let () = Xmlf_generators.test_generators ()

let specification_test ?nb_runs title generator (func, spec) =
  let verbose_func x =
    try func x with exn ->
      Printf.printf "Test error:\n%s\nGuilty term :\n%!%s\n%!"
        (Printexc.to_string exn) (snd generator x);
      (* Printf.printf "Backtrace :\n%s\n%!" (Printexc.get_backtrace ()); *)
      raise exn in
  if nb_runs <> Some 0 then begin
    Kaputt.Test.run_test
      (Kaputt.Test.make_random_test ?nb_runs ~title
         generator verbose_func [spec]);
    flush_all ()
  end

let () =
  specification_test "subject reduction for xMLF"
    Xmlf_generators.exp_k
    Xmlf_specifications.subject_reduction


let test_subject_reduction_counterexamples () =
  (* randomly generated counter-examples, thanks to the specification test *)
  let term_1 =
    `TyAbs(
      XEnv.TVar.bind,
      XAst.TBot,
      `TyComp(
        `TyAbs(
          XEnv.TVar.bind,
          XAst.TVar(`B (XEnv.TVar.var 0)),
          `Lam(XEnv.EVar.bind, XAst.TBot, `Var(`B (XEnv.EVar.var 0)))
        ),
        XAst.Intro
      )
    ) in
  let term_2 =
    `TyAbs(
      XEnv.TVar.bind,
      XAst.TBot,
      `Let(
        XEnv.EVar.bind,
        `Lam(
          XEnv.EVar.bind,
          XAst.TVar(`B (XEnv.TVar.var 0)),
          `Var(`B (XEnv.EVar.var 0))
        ),
        `TyAbs(XEnv.TVar.bind, XAst.TBot, `Var(`B (XEnv.EVar.var 0)))
      )
    ) in
  let term_3 =
    `TyAbs(
      XEnv.TVar.bind,
      XAst.TBot,
      `TyComp(
        `TyAbs(
          XEnv.TVar.bind,
          XAst.TVar(`B (XEnv.TVar.var 0)),
          `Lam(XEnv.EVar.bind, XAst.TBot, `Var(`B (XEnv.EVar.var 0)))
        ),
        XAst.Inner(XAst.Intro)
      )
    )
  in
  let term_4 = `TyComp(
    `TyAbs(
      XEnv.TVar.bind,
      XAst.TBot,
      `Lam(
        XEnv.EVar.bind,
        XAst.TVar(`B (XEnv.TVar.var 0)),
        `TyComp(
          `TyAbs(
            XEnv.TVar.bind,
            XAst.TVar(`B (XEnv.TVar.var 0)),
            `Var(`B (XEnv.EVar.var 0))
          ),
          XAst.Outer(XEnv.TVar.bind, XAst.Hyp(`B (XEnv.TVar.var 0)))
        )
      )
    ),
    XAst.Elim) in
  [ term_1
  ; term_2
  ; term_3
  ; term_4 ]

let () =
  test "test_subject_reduction counterexamples"
    test_subject_reduction_counterexamples
    (List.iter (Xmlf_specifications.manual_test Xmlf_specifications.subject_reduction))

let () =
  (* This test is a big failure for now : it fails at even finding
     a well-typed gMLF term; it is disabled while the easier test
     below is in progress *)
  specification_test "erase(translate(a)) = a"
    ~nb_runs:0
    Gmlf_generators.exp_k
    Xmlf_specifications.type_erasure

let () =
  (* do not work on subtle terms such has the well-typed elaboration
     of (fun x -> x x) *)
  if false then
    specification_test "well_typed a => well_typed (translate(erase(a)))"
      Xmlf_generators.exp_k
      Xmlf_specifications.well_typed_erase

let translate str =
  let exp = GAst.desugar (AST.desugar (EParse.expr str)) in
  let graph = GTranslate.type_of_expr conf GEnv.Global.empty exp in
  let () = GSolve.solve_all graph in
  XTranslate.translate graph

let test_well_typed_erase_counterexamples () =
  List.map translate
    [ "let x = fun y -> y in x"
    ; "(fun x -> x) (fun x -> x)"
    ; "let x = (fun y -> y) (fun y -> y) in x"
    ; "(fun x y -> y) (let x = fun x -> x in x)" ]

let () =
  test "test_well_typed(erase(a))_counterexamples"
    test_well_typed_erase_counterexamples
    (List.iter (fun t -> Kaputt.Assertion.is_true (Xmlf_specifications.well_typed t)))

let () =
  (* do not work on subtle terms such has the well-typed elaboration
     of (fun x -> x x) *)
  if false then
  specification_test "well_typed a => erase(t) = erase(translate(erase(t)))"
    Xmlf_generators.exp_k
    Xmlf_specifications.erase_translate_is_identity

let test_annotation_counterexamples () =
    List.map translate
      [ "fun (x : some 'a in 'a) -> x"
      ; "fun (x : some 'a in 'a) y -> x y"
      ; "fun (x : 'a . 'a -> 'a) -> x x"
      ; "fun x -> (x : 'a . 'a -> 'a) x"
      ; "fun (x : 'a . 'a -> 'a -> 'a) -> x x x"
      ; "fun (x : some 'b in 'a . 'a -> 'b) -> x"
      ; "fun (x : 'a . 'a -> 'a -> 'a) -> x x x"
      ; "fun (x : some 'b in 'b) (y : some 'a 'b in 'b -> 'a) -> y x" ]

let () =
  test "annotation examples"
    test_annotation_counterexamples
    (List.iter (fun t -> Kaputt.Assertion.is_true (Xmlf_specifications.well_typed t)))

let test_tyabs_counterexamples () =
    List.map
      (fun t -> Xmlf_specifications.well_typed (translate t))
      [ "Fun 'a -> fun (x : 'a) -> x"
      ; "(Fun 'b -> fun (x : 'b) -> x)['a . 'a -> 'a]" 
      ; "fun x -> x['a . 'a -> 'a]" ]

let () =
  test "tyabs examples"
    test_tyabs_counterexamples (List.iter Kaputt.Assertion.is_true)


(** Builtin tests *)
let concat_log log log' = match log, log' with
| t, None | None, t -> t
| Some t, Some t' -> Some (t ^ t')

let verbose_translate_and_reduce ?type_check exp_str =
  let exp, log = verbose_translater ?type_check exp_str in
  let reduced_exp, log' = verbose_reducer ?type_check (of_exp exp) in
  reduced_exp, concat_log log log'

let test_simple_builtins () =
  let unit = `Unit, TConst `Unit in
  let int n = (`Int n, TConst `Int) in
  let bool b = (`Bool b, TConst `Bool) in
  List.map
    (fun (exp_str, result) ->
      verbose_translate_and_reduce exp_str,
      `Builtin result)
    [
     "()", unit;
     "2 + 3", int 5;
     "3 - 2 - 1", int 0;
     "0 = 0", bool true;
     "1 = 2", bool false;
     "if True then 1 else 2", int 1;
     "if False then 1 else 2", int 2;
    ]

let () =
  test "test simple builtins (unit, int, arith_ops, bool, if)"
    test_simple_builtins all_exp_pairs

let test_fix () =
  let str1 = "let rec f x = f x in f" in
  let computed_type1 =
    let reduced_exp, log =
      verbose_translate_and_reduce ~type_check:true str1 in
    let reduced_type, log' =
      verbose_typer XEnv.empty (of_exp reduced_exp) in
    reduced_type, concat_log log log' in
  let known_type1 =
    tbound_h tbot (fun alpha ->
      tbound_h tbot (fun beta ->
        tarrow alpha beta)) in
  [ (computed_type1, to_typ known_type1) ]

let () =
  test "test fix"
    test_fix all_typ_pairs
