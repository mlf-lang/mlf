let conf = Config.default_conf

module S = Kaputt.Specification

let manual_test (func, spec) term =
  assert (spec.S.precond term);
  Kaputt.Assertion.is_true (spec.S.postcond (term, func term))

let bounded_spec size_func spec size_limit =
  let is_small_enough instance = size_func instance <= size_limit in
  { spec with S.precond = S.logand is_small_enough spec.S.precond }

let bisection_test ?(verbose=true) ?(nb_runs=100) ?classifier ?random_src
    title parametrized_generator size_func (func, spec) init_size =
  let module T = Kaputt.Test in
  let bounded_test size_limit =
    let nb_runs = nb_runs * init_size / size_limit in
    T.make_random_test ~title ~nb_runs ?classifier ?random_src
      (parametrized_generator size_limit)
      func [bounded_spec size_func spec size_limit] in
  let failure_witness size =
    match T.exec_test (bounded_test size) with
      | T.Report (_, _, _, counter_examples, _) ->
          counter_examples
      | T.Passed _
      | T.Failed _
      | T.Uncaught _
      | T.Exit_code _ -> assert false in
  let rec bisect start stop =
    if verbose then
      Printf.eprintf "bisect\t%d\t%d\n%!" start stop;
    if start = stop then
      (match failure_witness start with
         | [] -> bisect start stop
         | li -> start, li)
    else
      let mid = (start + stop) / 2 in
      match failure_witness mid with
        | [] -> bisect (mid + 1) stop
        | hd::tl ->
            if verbose then
              Printf.printf "Size %d counter-example (%d others found):\n%s\n"
                mid (List.length tl) (snd (parametrized_generator mid) hd);
            bisect start mid in
  if (failure_witness init_size) = []
  then failwith "Unable to verify failure for the initial size;
                 increase the number of runs ?";
  bisect 1 init_size


(** Subject reduction : if (Γ ⊢ a : σ) and (a ⇝ a'), then (Γ ⊢ a' : σ) *)

let well_typed : XAst.exp S.predicate =
  fun term ->
    try ignore (XTyper.type_eval ~verbose:false XEnv.empty term); true
    with XTyper.Type_error _ | XTyper.Tycomp_error _ -> false

let can_reduce : XAst.exp S.predicate =
  fun term ->
    try ignore (XReduce.reduce_step term); true
    with XReduce.No_reduction _ -> false

let same_type : (XAst.exp * XAst.exp) S.predicate =
  fun (a, b) ->
    let typ = XTyper.type_eval XEnv.empty in
    typ a = typ b

let subject_reduction =
  XReduce.reduce_step,
  S.implies
    (S.logand well_typed can_reduce)
    (S.logand (S.zip2 S.always well_typed) same_type)

let present_subject_reduction_counterexample term =
  let seq term = XPrint.doc
    (XPrint.type_sequent XEnv.empty term
       (XTyper.type_eval XEnv.empty term)) in
  Printf.printf "Subject reduction counter-example :\n%s\n%s\n%!"
    (seq term) (seq (XReduce.reduce_step term))

(* For use in the toplevel :

let _ =
  (fun size ->
   let module T = Kaputt.Test in
   let module XG = Xmlf_generators in
   let module XS = Xmlf_specifications in
   let gen = XG.use_compact_printer XPrint.ML.exp (XG.param_exp size) in
   let (func, spec) = XS.subject_reduction in
   T.exec_test (T.make_random_test ~nb_runs:1000 ~title:"subject reduction"
                  gen func [spec])) 10;;
*)


(** Type erasure : erase(translate(a)) = a *)
let type_erasure =
  let erase = XTranslate.erasure in
  let translate term =
    let exp = GAst.desugar (AST.desugar term) in
    let graph = GTranslate.type_of_expr conf GEnv.Global.empty exp in
    let do_warn = !GType.warn_dps in
    GType.warn_dps := false;
    let result = XTranslate.translate graph in
    GType.warn_dps := do_warn;
    result in
  let tried = ref 0 in
  let can_translate a =
    incr tried;
    if !tried mod 1000 = 0 then Printf.eprintf "Tried %d\n%!" (!tried / 1000);
    try ignore (translate a); true with _ -> false in
  let erase_translate_is_identity =
    { S.precond = can_translate;
      S.postcond = fun (a, a') ->
        GAst.alpha_equiv (GAst.desugar (AST.desugar a)) (erase a') } in
  translate, erase_translate_is_identity

(** well_typed t => well_typed (translate(erase(t))) *)
let well_typed_erase =
  let erase = XTranslate.erasure in
  let translate term =
    let graph = GTranslate.type_of_expr conf GEnv.Global.empty term in
    let do_warn = !GType.warn_dps in
    GType.warn_dps := false;
    let result = XTranslate.translate graph in
    GType.warn_dps := do_warn;
    result in
  (fun t -> translate (erase t)),
  S.implies' well_typed well_typed

(** well_typed t => erase(t) = erase(translate(erase(t))) *)
let erase_translate_is_identity =
  let erase = XTranslate.erasure in
  let translate term =
    let graph = GTranslate.type_of_expr conf GEnv.Global.empty term in
    let do_warn = !GType.warn_dps in
    GType.warn_dps := false;
    let result = XTranslate.translate graph in
    GType.warn_dps := do_warn;
    result in
  (fun t -> translate (erase t)),
  S.implies well_typed (fun (t, t') -> GAst.alpha_equiv (erase t) (erase t'))

