(* TODO
   - add tests (gtest, xtest) entry points
   - add an "#interact" directive for interactive graph resolution
*)


let global_conf = ref Config.default_conf

let interactive =
  Options.flag false (* true *)
    "--interactive" "Graphical interactive typechecking"
let () = Options.add_shortcut "-i" "--interactive"

let toplevel =
  Options.flag false (* true *)
    "--toplevel" "Toplevel : Read Eval Print Loop"
let () = Options.add_shortcut "-t" "--toplevel"

let () = Options.add_config_flag global_conf ~short:"-x" Config.xmlf
let () =
  List.iter (Options.add_config_flag global_conf)
    [
     Config.print_source;
     Config.print_desugared;
     Config.backtrace;
     Config.xmlf_backtrace;
     Config.gmlf_backtrace;
     Config.fail;
     Config.xmlf_reduce;
     Config.xmlf_reduce_verbose;
     Config.experimental_fomega;
    ]

let () =
  let action () =
    global_conf :=
      (* we first enable the xmlf_utf8 dependencies *)
      Config.set ~cascade:true !global_conf Config.xmlf_utf8;
    global_conf :=
      Config.clear !global_conf Config.xmlf_utf8 in
  Options.add "--no-xmlf_utf8" (Arg.Unit action)
    "disable UTF8 printing of xMLF terms (default xmlf_utf8 option)"

let () = Options.add_config_flag global_conf Config.dot

let from_stdin =
  Options.flag false (* true *) "-" "Read expression from stdin"

let implicit_bindings =
  Options.flag false (* true *) "--implicit_bindings" "Omit implicit edges"

let cmdline_examples = ref []
let files = ref []
let register accu s = accu := s::!accu
let register_name s =
  try
    register cmdline_examples (s, List.assoc s !Examples.predefined)
  with Not_found ->
    Printf.eprintf "No expressions registered under name %s\n" s
let register_expr e =
  cmdline_examples := ("_", e) :: !cmdline_examples
let print_env env =
  List.iter
    (function n, e -> Printf.printf "val %s = %s\n\n" n e)
    env
let register_list() = print_env !Examples.predefined
let register_filter pat =
  let re = Str.regexp pat in
  let matches (s, _e) =
    try let _ = Str.search_forward re s 0 in true with Not_found -> false in
  let smaller = List.filter matches  !Examples.predefined in
  Examples.predefined := smaller;;
let register_all() =
  cmdline_examples := List.rev_append !Examples.predefined !cmdline_examples


let more_options =
    [
     (* selecting examples *)
     "-use", Arg.String register_name,
     "<NAME>	Typecheck predefined expression registered as <NAME>";
     "-all", Arg.Unit register_all,
     "	Typecheck all filtered predefined expressions";
     "-list", Arg.Unit register_list,
     "	List predefined expression";
     "-filter", Arg.String register_filter,
     "<STRING>	Filter predefined definitions whose name matches <STRING>";
     "-expr", Arg.String register_expr,
     "<EXPR>	Typecheck expression <EXPR>";

     (* debugging *)
     "-stepping", Arg.Set GSolve.stepping, "stepping";
     "-trace_solve", Arg.Set GSolve.trace_solve, "trace_solve";
     "-print-all",
        Arg.Unit (fun () ->  GPrint.options := GPrint.All :: !GPrint.options),
        "print with all options";
   ]


let () =
  let default_option = register files in
  let default_message =
    "Usage: ./main.byte <options> <files>\n\
      where <options> are:" in
  Arg.parse
    (more_options @ (* Animate.options @ *) Options.all())
      default_option default_message;
  if !GSolve.dot_constraint then
    global_conf := Config.set !global_conf Config.dot;
  ()

(* Graphical Type inference *)
let gmlf ?name conf env ast =
  let ppf = Format.std_formatter in
  let () =
    if Config.is_set conf Config.print_source then
      AST.print_source_expr ppf ast in
  let core_exp = AST.desugar ast in
  let () =
    if Config.is_set conf Config.print_desugared then begin
      Format.fprintf ppf "desugared : @[%a@]"
        AST.print_expr (core_exp :> AST.expr Locations.loc)
    end
  in
  let exp = GAst.desugar core_exp in
  let graph = GTranslate.type_of_expr conf env exp in
  let root = graph.Expr.root in
  let () =
    if !Debug.after_gtranslate then
      Dot.drum ~name_suffix:"after_gtranslate" ~ids:true ~proj:false root in

  let () = GSolve.solve_all graph in
  let () =
    if !Debug.after_gsolve then
      Dot.drum ~name_suffix:"after_gsolve" ~ids:true ~proj:false root in

  let root' = GSolve.normalize root in
  let () = Print_type.print_type_expr ?name ppf (GType.below_gen root') in
  if Config.is_set conf Config.dot then
    begin
      if !GSolve.dot_constraint then Dot.drum ~proj:false root;
      let drum root =
        let inlining =
          let t0 = GType.below_gen root in
          Print_type.inline t0 in
        let emph t =
          if GType.gen_node t || GType.inert t then None
          else if  inlining t then Some "yellow"
          else None in
        let hide t = !implicit_bindings && inlining t in
        Dot.drum ~proj:true ~emph ~hide root in
      drum root;
      drum root'
    end;
  root

(* Translating the presolution to xMLF *)
let xmlf _conf root =
  let () =
    GType.invariant_all_nodes_invariants root XTranslate.rigidify root in
  if !Debug.after_rigidify then
    Dot.drum ~name_suffix:"after_rigidify" ~ids:true ~proj:false root;

  let translate_env = XTranslate.env_init root in
  Printf.printf "graph type :\n";
  let xtype = XAst.DSL.to_typ (XTranslate.translate_type translate_env root) in
  print_endline (XPrint.doc (XPrint.typ XEnv.empty xtype));

  let xexpr =
    let translate root =
      XTranslate.translate_expr translate_env (Locations.noloc root) in
    let expr = GType.invariant_no_new_node translate root in
    XSimplify.simplify (XAst.DSL.to_exp_debug expr) in
  if !Debug.after_xtranslate then
    Dot.drum ~name_suffix:"after_xtranslate"
      ~ids:true ~proj:false (GType.find_root root);

  Printf.printf "translated term :\n";
  print_endline (XPrint.doc (XPrint.exp XEnv.empty xexpr));

  Printf.printf "translation type :\n";
  let typ = XTyper.type_eval ~verbose:true XEnv.empty xexpr in
  print_endline (XPrint.doc (XPrint.typ XEnv.empty typ));
  xexpr

let xmlf_reduce conf xmlf =
  let reduced, msg =
    if not (Config.is_set conf Config.xmlf_reduce_verbose) then
      XReduce.reduce xmlf, None
    else XReduce.verbose_reducer xmlf in
  match msg with
  | Some msg -> print_endline msg
  | None ->
      Printf.printf "Reduction result :\n%s\n"
        (XPrint.doc (XPrint.exp XEnv.empty reduced))

(* Toplevel phrase evaluation *)
let type_of_exp ?name (conf, env) exp =
  let maybe_backtrace backtrace_condition f =
    if not (Config.is_set conf Config.backtrace || backtrace_condition)
    then f ()
    else
      let old_status = Printexc.backtrace_status () in
      let after_exn exn =
	let out = stdout in
        Printf.fprintf out "%s\n"
	  (Printexc.to_string exn);
        Printexc.print_backtrace out;
        flush out in
      Utils.protect
	~before:(fun () -> Printexc.record_backtrace true)
	f
	~after_exn
	~finally:(fun () -> Printexc.record_backtrace old_status)
	() in
  let compute_type () =
    let graph =
      maybe_backtrace (Config.is_set conf Config.gmlf_backtrace)
        (fun () -> gmlf ?name conf env exp) in
    let () =
      if Config.is_set conf Config.xmlf then
        let xmlf =
          maybe_backtrace (Config.is_set conf Config.xmlf_backtrace)
            (fun () -> xmlf conf graph) in
        if Config.is_set conf Config.xmlf_reduce then 
          xmlf_reduce conf xmlf in
    graph in
  let utf_status = !Symbol.use_utf in
  Utils.protect
    ~before:(fun () -> Symbol.use_utf := Config.is_set conf Config.xmlf_utf8)
    compute_type
    ~finally:(fun () -> Symbol.use_utf := utf_status)
    () 

let change_conf conf loc option value =
  let flag =
    try (Config.flag_of_string option)
    with Not_found ->
      let error = ToplevelErrors.Invalid_option (loc, option) in
      raise (ToplevelErrors.ToplevelError error) in
  (if value then Config.set else Config.clear) conf flag

(* global_conf, local_conf

   The toplevel has two different configuration scopes : global and
   local scope. The general idea is that the global changes affect all
   following phrases, while the local change affect only the current
   phrase.

   Configurations are immutable objects passed to and returned by
   check_and_bind (essentially a State monad), exactly like typing
   environments.

   A natural implementation would be the following : maintain one
   configuration through check_and_bind kinds, with global changes
   affecting the returned configuration, and the following semantic
   for #local <change> <phrase> :
   - add the change to the current configuration, as a new configuration
   - evaluate the phrase under the new configuration
   - return the former configuration back, effectively cancelling any local changes

   The issue is that this implementation would have an intuitively
   incorrect semantic if the <phrase> changes the global env :
      #local +foo (#global -bar)
   With this semantic, the global -bar changes would be effectively ignored.

   My solution is to use a different, slightly more complex
   implementation with two distinct scopes : a "global configuration"
   object, and a "local modification configuration *modifier*",
   ie. a function that changes the global configuration. Global
   changes are kept in the returned configuration, while changes to
   the local modifiers are dropped at the end of the phrase.
   
   The empty local configuration is thus the identity :
*)
let default_local_conf = fun global -> global

let rec check_and_bind (conf, env) p =
  let (!!) (global_conf, local_modifier) =
    local_modifier global_conf in
  let execute_phrase p = match p.Locations.obj with
    | AST.Expr exp ->
      let _ = type_of_exp (!!conf, env) exp in
      (conf, env)
    | AST.Val (r, let_name, body) ->
      let exp = AST.val_to_let r let_name body in
      let name = (AST.let_name let_name).Locations.obj in
      let g = type_of_exp ~name (!!conf, env) exp in
      let env' = GEnv.Global.add_exp name g env in
      (conf, env')
    | AST.Include file ->
      let phrases =
        try EParse.phrases (Some file) 
        with Sys_error _ ->
          let error = ToplevelErrors.File_not_found (p.Locations.loc, file) in
          raise (ToplevelErrors.ToplevelError error) in
      (* Note : In the #include case, the environment passed to evaluate the
         phrases of the included files is the global+local environment, and
         not only the global environment. For example, `#local +foo #include
         <file>` will apply the change +foo to all phrases of <file>. *)
      List.fold_left
        check_and_bind
        ((!!conf, default_local_conf), env)
        phrases
    | AST.Global (option, value) ->
      let global, local = conf in
      let global' = change_conf global p.Locations.loc option value in
      ((global', local), env)
    | AST.Local ((option, value), phrase) ->
      let global, local = conf in
      let local' conf =
        change_conf (local conf) p.Locations.loc option value in
      let ((global', _local''), env') =
        check_and_bind ((global, local'), env) phrase in
      ((global', local), env')
    | AST.Help command ->
      print_string (Tophelp.eval Tophelp.help command);
      flush stdout;
      (conf, env)
    | AST.Alias (_, _) | AST.Inductive (_, _) ->
      failwith "phrase not yet supported" in
  let could_fail = function
    | AST.Expr _ | AST.Val (_, _, _) -> true
    | AST.Include _ | AST.Help _
    | AST.Local (_, _) | AST.Global _ 
    | AST.Inductive _ | AST.Alias _ -> false in
  try
    let result = execute_phrase p in
    if Config.is_set !!conf Config.fail && could_fail p.Locations.obj then
      Printf.printf
        "Warning: the typing of this expression should have failed.\n\n%!";
    result
  with exn ->
    if Config.is_set !!conf Config.fail then
      Printf.printf
        "Expected failure (#+fail):\n%!";
    ErrorsHandling.report_error Format.std_formatter exn;
    (conf, env)
    

let rec source_expr_of_phrase p =
  match p.Locations.obj with
  | AST.Expr exp  -> Some exp
  | AST.Val (r, x, exp) -> Some (AST.val_to_let r x exp)
  | AST.Local (_, phrase) -> source_expr_of_phrase phrase
  | AST.Include _ | AST.Global _ | AST.Help _ -> None
  | AST.Alias (_, _) | AST.Inductive (_, _) -> assert false

let phrases() =
  List.concat
    [
     List.map EParse.phrase_of_named_string
        (List.rev !cmdline_examples);
      List.concat
        (List.rev_map (fun f ->  EParse.phrases (Some f)) !files);
      if !from_stdin then EParse.phrases None else [];
    ]
;;

let usage =
  "Toplevel loop for typing MLF declarations.
    Usage: toplevel [options]"

let done_nothing () =
  print_endline Tophelp.no_action_help

let main () =
  if !interactive then
    print_endline Tophelp.interactive_help
  else
    let phrases = phrases() in
    let conf, env =
      let conf = !global_conf, default_local_conf in
      let env = GEnv.Global.empty in
      List.fold_left check_and_bind (conf, env) phrases in
    if !toplevel then
      Toploop.loop
        Format.std_formatter
        ~init_env:(conf, env)
        ~init_msg:Tophelp.short_help
        ~parse_phrase:EParse.toplevel_phrase
        ~eval_phrase:check_and_bind
        ~report_error:ErrorsHandling.report_error
    else if phrases = [] then
      done_nothing ()
;;

let () =
  if Config.is_set !global_conf Config.dot then
    ignore (Sys.command "rm -f dot/*.dot");
  Utils.protect
    main
    ~after_exn:(ErrorsHandling.report_error Format.err_formatter)
    ~finally:(if Config.is_set !global_conf Config.dot then
                Dot.concat else ignore)
    ()
;;
