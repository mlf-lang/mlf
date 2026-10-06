module Options = struct
  type output =
    | LaTeX
    | Ascii
    | Unicode

  let output = ref Ascii
    
(*   (\* Generation of constraints *\) *)
(*   let shortcut_bottoms = ref true *)
(*   let shortcut_seqabs = ref true *)
(*   let shortcut_forall = ref true *)
(*   let rigid_right_coercions = ref false *)
(*   let solve_app_before_arg = ref false *)
(*   let sequence_has_type_unit = ref false *)
(*   let expand_types_from_env = ref false *)
(*   let native_recursion_typing = ref false *)


  (* Display *)
  (* Less parentheses in source code and types when not too ambiguous *)
  let minimize_parentheses = ref true

  (* Syntactic normal forms (for monomorphic parts) in solutions *)
  let normal_forms = ref true
  let show_mono_edges = ref true

  let common = [
    "-debug", Arg.Set Utils.show_debug, " (undocumented)";
  ]

end


module OptionsInteractives = struct
  (* Options concerning only interactive mode *)

  let inline_types = ref true

  (* Display of constraint graphs *)
  (* let unicode = ref false *)

  let inst_constrains_height = ref true
  let sort_edges = ref false
(*   let show_children_number = ref true *)
(*   let show_struct_end = ref false *)
  let print_nodes_id = ref false
  let gc_nodes = ref true

  let auto_unif_after_inst = ref false
  let reuse_last_scheme = ref true

  (* Cleaning of existential nodes *)
  let auto_remove_unconstrained = ref true

  (* Wf *)
  let check_at_each_step = ref true

  type elim_expand = Elim | Expand
  let elim_expand = ref Elim


  (* ML *)

  let ml_constraints = ref false
  let ml_expansion = ref false
end

(* open Constraints *)
(* open ConstraintsInteract *)
(* open GraphicTypes *)
(* open GraphicTypes.Nodes *)
open Options
open OptionsInteractives


let remove_implied_existentials = ignore

(* let compare_ids n s = *)
(*   nid n = s *)

(* let compare_ids_edges (s1, s2) (n1, n2) = *)
(*   (nid n1 = s1 && nid n2 = s2) || (nid n1 = s2 && nid n2 = s1) *)


(* (\* Constraints that can be freely marshalled *\) *)
(* type non_functional_constraint = { *)
(*   n_root: node; *)
(*   n_constraints: constraint_edge list; *)
(*   n_exists: node list; *)
(* } *)

(* let from_constraint c = { *)
(*   n_root = c.root; *)
(*   n_constraints = c.constraints#get; *)
(*   n_exists = c.exists#get; *)
(* } *)

(* let to_constraint c = *)
(*   let sc = new Utils.store ~eq:equal_constraints () *)
(*   and se = new Utils.store ~eq:Nodes.equal () in *)
(*   sc#set c.n_constraints; *)
(*   se#set c.n_exists; *)
(*   { *)
(*     root = c.n_root; *)
(*     constraints = sc; *)
(*     exists = se; *)
(*   } *)


(* Code examples *)
let make_examples env =
  let max_name_length =
    let accu len (name, _) = max len (String.length name) in
    List.fold_left accu 0 env in
  let comment_name = Printf.sprintf "(* %s *)" in
  let comment_length = String.length (comment_name "") in
  let example (name, expr) =
    Printf.sprintf "%-*s %s"
      (max_name_length + comment_length) (comment_name name) expr in
  let res = List.map example env in
  res


(* (\* Gestion of state *\) *)


type state = {
  st_examples : string list; 
  st_expr : AST.source_expr Locations.loc;
  st_ct_expr: AST.typing_expr Locations.loc;
  st_type: Expr.graphic_constraint;
  st_expr_text: string;
  mutable st_instances:
    (GType.gtype
     * GType.instance_flag
     * GMeaning.constraint_meaning
     * GType.gtype) list;
  mutable st_id: int; (* state of the node ID counter *)
}

let state_of_expr env syntaxic_expr expr_str =
  let expr = AST.desugar syntaxic_expr in
  let conf = (* TODO *)
    Config.set Config.FlagSet.empty Config.experimental_fomega in
  let graph =
    GTranslate.type_of_expr conf GEnv.Global.empty (GAst.desugar expr) in
  {
    st_examples = make_examples env;
    st_expr = syntaxic_expr;
    st_ct_expr = expr;
    st_type = graph;
    st_expr_text = Utils.newline_to_space expr_str;
    st_id = !GType.last_id;
    st_instances = GSolve.find_all_instances graph
  }

type marshalled_state = [`MarshalledState] Opaque.string_t

let marshal_state (st : state) : marshalled_state =
  Opaque.string_t (Marshal.to_string st [Marshal.Closures])

let restore_state (s : marshalled_state) =
  (Marshal.from_string (Opaque.t_string s) 0 : state)

let state_to_file (st : marshalled_state) =
  let d = Unix.localtime (Unix.time ()) in
  let date = Printf.sprintf "%d-%02d-%02d_%02d:%02d:%02d.mlfdump"
    (d.Unix.tm_year + 1900) (d.Unix.tm_mon+1) d.Unix.tm_mday
    d.Unix.tm_hour d.Unix.tm_min d.Unix.tm_sec
  in
  let ch = open_out_bin date in
  Marshal.to_channel ch (st : marshalled_state) [];
  close_out ch

let state_from_file file : marshalled_state =
  let ch = open_in_bin file in
  let (st : marshalled_state) = (Marshal.from_channel ch) in
  close_in ch;
  st

(* Bug found in confluence mode *)
exception Bug of exn * (int * int) list

class box w st filesuffix env =
  let dot_filename = filesuffix ^ ".dot" in

  let box = GPack.vbox () in
  (* Packs the menu and the image-dropdown part *)
  let hbox = GPack.hbox ~packing:(box#add) () in
  let menu = GPack.vbox ~spacing:10 ~packing:(hbox#pack ~expand:false) () in
  (* Packs the image and the dropdown *)
  let box_image = GPack.vbox ~packing:(hbox#pack ~expand:true) () in

  let string_choose = "Choose or type expr..." in
  let lexprs = new Utils.store ~eq:(=) () in
  let () = lexprs#set st.st_examples in
  let combo_exprs = GEdit.combo
    ~popdown_strings:lexprs#get
    ~allow_empty:false
    ~enable_arrow_keys:true
    ~value_in_list:false
    ~packing:(box_image#pack ~expand:false)
    () in

  (* -q1 suppresses some useless warnings *)
  let dot = "dot -q1" in
  let odot = new Odot_view.box ~dot_program:dot ~filesuffix
    ~box_zoom:menu ~box_image:box_image () in

  let tooltips_controls = GData.tooltips () in
  let set_tooltip text ctrl =
    tooltips_controls#set_tip ~text ctrl#coerce;
    ctrl
  in
  let frame name =
    let frame = GBin.frame ~label:name ~packing:(menu#pack ~expand:false) () in
    GPack.vbox ~packing:frame#add ()
  in
  let button frame name tooltip =
    set_tooltip tooltip (GButton.button ~label:name ~packing:frame#add ())
  and option frame name tooltip =
    set_tooltip tooltip (GButton.check_button ~label:name ~packing:frame#add ())
  in
  let btreset =
    set_tooltip "Restart from scratch the solving of the current constraint"
      (GButton.button ~label:"Reset solving" ~packing:(menu#pack ~expand:false)
      ())
  in

  let fhistory = frame "History" in
  let fdisplay = frame "Display of graphs" in
  let fdisplaysols = frame "Display of solutions" in
(*   let finstantiation = frame "Instantiation edges" in *)
  let funif = frame "Auto-solving" in
(*   let fconfluence = frame "Confluence" in *)
(*   let fclean = frame "Existentials" in *)
(*   let fcheck = frame "Well-formedness" in *)
(*   let fconstraints = frame "Constraints generation" in *)

  let btprev = button fhistory "Prev" "Go back to the previous constraint" in
  let btnext = button fhistory "Next" "Go to the next constraint" in
  let btdump = button fhistory
    "Dump state" "Dump the current state into a file that can be reloaded later" in
(*   let chkchildren_number = option fdisplay "Show children number" *)
(*     "Show nodes children arities even when edges are sorted" in *)
(*   let chkstruct_end = option fdisplay "Show end of black ->" *)
(*     "Show an arrow at the end of structure edges. Useful for cyclic types"in *)
  let chkids = option fdisplay "Show Ids"
    "Show nodes id. Useful for error messages" in
  (* let chkmono = option fdisplay "Blank mono nodes" *)
  (*   "Display monomorphic nodes in white" in *)
  let chnf = option fdisplaysols "Syntactic normal forms"
    "Display solutions in syntactic normal forms (eliminate useless quantificattion)" in
  let chinline_poly = option fdisplaysols "Inline polytypes"
    "Expand polytypes inside monotypes according to the syntactic sugar" in

(*   let btclean = button fclean "Clean" *)
(*     "Remove unconstrained existential subparts" in *)
(*   let chkclean = option fclean "Auto clean" *)
(*     "Auto remove unconstrained existential subparts" in *)

(*   let btcheck = button fcheck "Check" *)
(*     "Check that the constraint is well-formed" in *)
(*   let chkcheck = option fcheck "Auto check" *)
(*     "Automatically perform well-formedness checks" in *)

(*   let chkautounif = option finstantiation "Unif after inst" *)
(*     "Automatically solve the unification edge resulting from the expansion of an instantiation edge" in *)

(*   let butelim = GButton.radio_button *)
(*     ~label:"Inst-Expand"  ~packing:finstantiation#add ~active:true () in *)

(*   let butexpand = GButton.radio_button ~group:butelim#group *)
(*     ~label:"Expansion"  ~packing:finstantiation#add () in *)
(*   let chkmlexpansion = option finstantiation "ML Expansion" *)
(*     "Perform ML expansion" in *)

  let btsolveone = button funif "Solve one" "" in
  let btsolveall = button funif "Solve all"
    "Try to solve all the remaining constraint edges" in
(*   let btconfluence = button fconfluence "Start" *)
(*     "Check confluence of the constraints solving strategy by solving constraints in a random order. Abort using Ctrl-C" in *)
(*   let adjustment_confluence = *)
(*     GData.adjustment ~lower:0. ~upper:100. ~step_incr:1. () in *)
(*   let _rangeconfluence = set_tooltip *)
(*     "Nb of edges solved at which confluence tests stop. 0 means never" *)
(*     (GRange.scale `HORIZONTAL *)
(*        ~adjustment:adjustment_confluence ~digits:0 ~value_pos:`RIGHT *)
(*        ~packing:(fconfluence#pack ~expand:false) ()) in *)

(*   let chkmlconstraints = option fconstraints "ML simplified constraints" *)
(*     "Generate ML simplified constraints, in which nodes are bount at let nodes" in *)
(*   let chksolvedbottoms = option fconstraints "Solved bottoms" *)
(*     "Solve constraints corresponding to variables during constraints generation" in *)
(*
  let chksolvedseqabs = option fconstraints "Solved seq. abstractions"
    "Solve constraints corresponding to sequence of abstractions during constraints generation" in
*)
(*   let chksolvedvalues = option fconstraints "Solved known values" *)
(*     "Remove the forall quantifier for known monomorphic values" in *)
(*  let chkrigid = option fconstraints "Rigid coercions" in *)
(*   let chkapp_before_arg = option fconstraints "Solve fun before arg" *)
(*     "In an application, solve the function before the argument" in *)

  let status = GMisc.statusbar ~packing:box#pack () in
  let status = status#new_context ~name:"Statusbar" in

  object (self)

    method box = box

    (* Current state. Note that st.st_constraints can have been
    changed by instantiation, unification... st_dump always contains
    a marshalled dump of st without any modification *)
    val mutable st = st
    val mutable st_dump = Opaque.string_t "" (* Set to a valid value in initializer *)


    (* Reloading of st according to st_dump *)
    method restore_state () =
      st <- restore_state st_dump;
      GType.last_id := st.st_id;

    method state_to_file () =
      state_to_file st_dump


    (* Gestion of the history *)
    val mutable prev = ([] : marshalled_state list)
    val mutable next = ([] : marshalled_state list)

    method back () = match prev with
      | [] -> ()
      | s :: q ->
          next <- st_dump :: next;
          prev <- q;
          st_dump <- s;
          self#restore_state ();
          self#refresh ();

    method next () = match next with
      | [] -> ()
      | s :: q ->
          prev <- st_dump :: prev;
          next <- q;
          st_dump <- s;
          self#restore_state ();
          self#refresh ();

    (* st has been changed by another function, we update the history
       and st_dump *)
    method add_history () =
      (* We test for the initial state *)
      if st_dump <> Opaque.string_t "" then (
        prev <- st_dump :: prev;
        next <- [];
      );
      st_dump <- marshal_state st

    (* Screen update with history update *)
    method refresh () =
      let win = w#misc#window in
      Gdk.Window.set_cursor win (Gdk.Cursor.create `WATCH);
      while Glib.Main.pending () do
        ignore (Glib.Main.iteration false);
      done;
      
      let emph =
	match st.st_instances with
	  | [] -> (fun _ -> None)
	  | (tg, _f, _m, t) :: _ ->
	      (fun t' ->
		 if GType.eqrepr tg t' || GType.eqrepr t t' then Some "purple"
		 else None) in
      let ids = !OptionsInteractives.print_nodes_id in
      let () =
        let buf = Buffer.create 1024 in
        Dot.print_constraint ~ids ~emph buf st.st_type.Expr.root;
        let ch = open_out dot_filename in
        Buffer.output_buffer ch buf;
        close_out ch in

      odot#refresh_image ();
      w#set_title ("MLF - Typing  " ^ st.st_expr_text);
(*       self#update_clean_button (); *)
      self#update_history_buttons ();
      self#update_solve_buttons ();

(*       if !check_at_each_step then self#wf_constraint (); *)

      self#update_status_solved;

      Gdk.Window.set_cursor win (Gdk.Cursor.create `LEFT_PTR);


    method update_status_solved =
      let c = st.st_type in
      status#pop ();
      if (* solved c *) false then (
	ignore c
(*         ignore (status#push *)
(*            ("Solved: " ^ Utils.format_into_string *)
(*               (SyntacticTypesPrinting.print_polytype ~sugar_env:self#sugar) *)
(*               (forall_printing c))) *)
      );


    method state_changed () =
      self#add_history ();
      self#refresh ();


    (* Parsing of the expr succeeded *)
    val mutable expr_ok = true

    method load_expr_success ?(expr=st.st_expr_text) ?(refresh=true) () =
      if expr <> "" then
        try
          let p = EParse.expr expr in
          if st.st_expr <> p || refresh then (
            st <- state_of_expr env p expr;
            remove_implied_existentials st.st_type;
            self#state_changed ();
            expr_ok <- true;
            lexprs#add_unique expr;
          );
          true
        with e ->
          let s = ErrorsHandling.error_to_string e in
          expr_ok <- false;
          status#pop ();
          ignore (status#push s);
          false
      else
        true

    method load_expr ?(expr=st.st_expr_text) ?(refresh=true) () =
      ignore (self#load_expr_success ~expr ~refresh ())


    (* Buttons update *)
    method update_solve_buttons () =
(*       let c = st.st_type in *)
(*       match c.constraints#getwith *)
(*         | [] -> *)
(*             btsolveone#misc#set_sensitive false; *)
(*             btsolveall#misc#set_sensitive false; *)
(*         | e :: _ -> *)
(*             btsolveone#misc#set_sensitive true; *)
(*             btsolveall#misc#set_sensitive true; *)
(*             let text = *)
(*               Printf.sprintf "Solve the edge %s" (edge_description e) in *)
(*             ignore (set_tooltip text btsolveone) *)
      match st.st_instances with
	| [] ->
	    btsolveone#misc#set_sensitive false;
	    btsolveall#misc#set_sensitive false;
	| (tg, f, m, t) :: _ ->
            btsolveone#misc#set_sensitive true;
            btsolveall#misc#set_sensitive true;
            ignore m; (* TODO use meaning explanation *)
            let text =
              Printf.sprintf "Solve the edge (%d -%s-> %d)"
                (GType.id tg)
                (match f with `Explicit -> "E" | `Implicit -> "")
                (GType.id t) in
            ignore (set_tooltip text btsolveone)	

(*     method update_clean_button () = *)
(*       let c = st.st_constraint in *)
(*       btclean#misc#set_sensitive *)
(*         (List.exists (interior_unconstrained c) c.exists#get) *)
(*       () *)

    method update_history_buttons () =
      btprev#misc#set_sensitive (prev <> []);
      btnext#misc#set_sensitive (next <> []);


    (* Auxiliary functions for inst and unif *)

(*     method funif = Unif.unif env *)

(*     method remove_all_unconstrained c = *)
(*       remove_all_unconstrained c; *)
(*       remove_implied_existentials c; *)

(*     method op_succeeded c = *)
(*       remove_implied_existentials c; *)
(*       if !auto_remove_unconstrained then ( *)
(*         self#remove_all_unconstrained c; *)
(*       ) *)

(*     method unif_aux c (n1, n2) = *)
(*       c.constraints#remove_matching equal_constraints' (n1, n2); *)
(*       self#funif (n1, n2); *)
(*       self#op_succeeded c; *)
(*       (\* we return true to signify that no exception has been raised *\) *)
(*       true *)

(*     method catch_unif_error f = *)
(*       try if f () then self#state_changed () *)
(*       with Unif.UnifError e | ConstraintsSolving.InferenceError (e, _) -> *)
(*         GToolbox.message_box "MLF" *)
(*           (Utils.format_into_string Unif.print_unif_error e); *)
(*         self#restore_state () *)


(*     method inst_expand_aux c e remove_edge = *)
(*       let { edge_nodes = (f, d); edge_meaning = m} = e *)
(*       and constraint_type = if !ml_expansion then ML else MLF in *)
(*       if remove_edge then decr_forall_count f; *)
(*       try *)
(*         let f' = *)
(*           expand_forall ~solve_easy_frontier:false ~constraint_type c e in *)
(*         let e' = (f', d) in *)
(*         if !auto_unif_after_inst then ( *)
(*           if remove_edge then *)
(*             c.constraints#remove_matching equal_constraints' (f, d); *)
(*           (\* Either unification succeeds (and return true) or it fails *)
(*              and raises an exception. Hence we can safely use its return *)
(*              value as our own. *\) *)
(*           self#unif_aux c e' *)
(*         ) else ( *)
(*           if remove_edge then *)
(*             c.constraints#replace_matching equal_constraints' (f, d) *)
(*               { edge_type = Unif; edge_meaning = m; edge_nodes = e'} *)
(*           else *)
(*             c.constraints#add *)
(*               {edge_type = Unif; edge_meaning = m; edge_nodes = e'}; *)
(*           self#op_succeeded c; *)
(*           true *)
(*         ) *)
(*       with TypingErrors.MLFTypeMLFExpansion -> *)
(*         GToolbox.message_box "MLF" *)
(*           "Cannot expand an MLF type using ML expansion"; *)
(*         self#restore_state (); *)
(*         false *)

(*     method expand_aux c e = *)
(*       self#inst_expand_aux c e false *)

(*     method inst_aux c e = *)
(*       let f = (fst e.edge_nodes) in *)
(*       if interior_unconstrained c ~skip:f f = false then ( *)
(*         GToolbox.message_box "MLF" "Cannot apply Inst-Expand to this edge: \ *)
(* the interior of the breakpoint is constrained"; *)
(*         false) *)
(*       else *)
(*         self#inst_expand_aux c e true *)


(*     (\* Wrappers for mouse interaction *\) *)

(*     method unif e = *)
(*       self#catch_unif_error *)
(*         (fun () -> self#unif_aux st.st_constraint e.edge_nodes) *)

(*     method inst_or_expand e = *)
(*       match !elim_expand with *)
(*         | Elim -> self#inst e *)
(*         | Expand -> self#expand e *)

(*     method inst e = *)
(*       self#catch_unif_error (fun () -> self#inst_aux st.st_constraint e) *)

(*     method expand e = *)
(*       self#catch_unif_error (fun () -> self#expand_aux st.st_constraint e) *)

(*     method raise_node n = *)
(*       let c = st.st_constraint in *)
(*       self#catch_unif_error (fun () -> raise_once c (self#unif_aux c) n) *)

(*     method remove_existential n = *)
(*       let c = st.st_constraint in *)
(*       if interior_unconstrained c n then ( *)
(*         remove_existential c n; *)
(*         remove_implied_existentials c; *)
(*         self#state_changed (); *)
(*       ) else *)
(*         GToolbox.message_box "MLF" *)
(*           "Cannot remove this existential node, it is constrained." *)

    method wf_constraint () =
      ()
(*       try ignore (Wf.correct st.st_constraint) *)
(*       with e -> GToolbox.message_box "MLF" *)
(*         ("Check failed: " ^ (Printexc.to_string e)); *)

(*     method solve_one () = *)
(*       let c = st.st_constraint in *)
(*       match c.constraints#get with *)
(*         | [] -> () *)
(*         | { edge_type = Unif } as e :: _ -> self#unif e *)
(*         | { edge_type = Inst; edge_nodes = (n1, _) } as e :: _ -> *)
(*             if interior_unconstrained ~skip:n1 c n1 then *)
(*               self#inst_or_expand e *)
(*             else *)
(*               GToolbox.message_box "MLF" "Badly ordered constraints: \ *)
(* the first constraint of the list has constraints underneath"; *)

    method solve_one () =
      match st.st_instances with
	| [] ->
	    GToolbox.message_box "MLF" "Nothing left to solve"
	| (tg, f, m, t) :: rest ->
	    try
	      GSolve.solve_inst tg (t, f, m);
	      st.st_instances <- rest;
	      self#state_changed ()
	    with exn -> GToolbox.message_box "MLF"
	      (Printf.sprintf "[Solving error] %s" (Printexc.to_string exn))
	       

    method solve_all () =
      try
	GSolve.solve_all st.st_type;
        st.st_instances <- [];
	self#state_changed ()
      with exn -> GToolbox.message_box "MLF"
	(Printf.sprintf "[Solving error] %s" (Printexc.to_string exn))

      

(*     method solve_all () = *)
(*       self#catch_unif_error *)
(*         (fun () -> ConstraintsSolving.solve ~env st.st_constraint; true) *)

    method clear_unconstrained () =
	 ()
(*       self#remove_all_unconstrained st.st_constraint; *)
(*       self#state_changed (); *)

(*     method expand_alias n = *)
(*       if Unif.expand_alias env n then self#state_changed () *)


(*     (\* Sugar environment, depending on the choice done in the interface *\) *)
(*     method sugar = *)
(*       if !inline_types then env.TypingEnv.sugar *)
(*       else SyntacticTypes.no_sugar *)


    (* Confluence tests *)

(*     method confluence_one c stop lvl list = *)
(*       if lvl > stop then raise Exit; *)
(*       if c.constraints#get = [] then ( *)
(*         self#remove_all_unconstrained c; *)
(*         Format.printf " %d constraints solved@.%a" lvl *)
(*           (SyntacticTypesPrinting.print_polytype ~sugar_env:self#sugar) *)
(*           (forall_printing ~nf:true c); *)
(*       ) *)
(*       else *)
(*         let i = Random.int (List.length c.constraints#get) in *)
(*         let e = List.nth c.constraints#get i in *)
(*         let n1, n2 = e.edge_nodes in *)
(*         let e' = nid n1, nid n2 in *)
(*         let r = match e.edge_type with *)
(*           | Unif -> *)
(*               list := e' :: !list; *)
(*               Format.printf ".%!"; *)
(*               self#unif_aux c e.edge_nodes *)
(*           | Inst -> *)
(*               if interior_unconstrained ~skip:n1 c n1 then ( *)
(*                 decr_forall_count n1; *)
(*                 c.constraints#remove e); *)
(*               self#expand_aux c e *)
(*         in *)
(*         if r then assert (Wf.correct c); *)
(*         self#confluence_one c stop (lvl + if r then 1 else 0) list *)

(*       let stop = if stop <= 0 then max_int else stop in *)
(*       Random.self_init (); *)
(*       Sys.set_signal Sys.sigint *)
(*         (Sys.Signal_handle (fun _ -> failwith "UserStop")); *)
(*       let list = ref [] in *)
(*       let rec aux () = *)
(*         (try *)
(*            self#restore_state (); *)
(*            let c = st.st_constraint in *)
(*            list := []; *)
(*            self#confluence_one c stop 0 list *)
(*          with *)
(*            | Exit -> *)
(*                if !elim_expand = Expand then ( *)
(*                  ConstraintsSolving.solve ~env st.st_constraint; *)
(*                  Format.printf " %a" *)
(*                    (SyntacticTypesPrinting.print_polytype ~sugar_env:self#sugar) *)
(*                    (forall_printing ~nf:true st.st_constraint)) *)
(*                else *)
(*                  Format.printf " Limit reached" *)
(*            | Unif.UnifError e -> Format.printf "%a" *)
(*                (Unif.print_unif_error ~output:Options.Ascii) e *)
(*            | Failure "UserStop" as e -> raise e *)
(*            | e -> raise (Bug (e, !list)) *)
(*         ); *)
(*         Format.printf "@.@."; *)
(*         aux () *)
(*       in try aux () *)
(*       with *)
(*         | Bug (e, l) -> *)
(*             self#restore_state (); *)
(*             let l, last = List.rev (List.tl l), List.hd l in *)
(*             self#replay_list l last; *)
(*             Sys.set_signal Sys.sigint Sys.Signal_default; *)
(*             GToolbox.message_box "MLF" *)
(*               (Printf.sprintf "%s\nNext faulty edge: %d-%d" *)
(*                  (Printexc.to_string e) (fst last) (snd last)) *)

(*         | Failure "UserStop" -> *)
(*             Format.printf "@.Interrupted@.@."; *)
(*             Sys.set_signal Sys.sigint Sys.Signal_default; *)
(*             self#restore_state (); *)

(*     method replay_list l _last = *)
(*       Format.printf "@.Error found, replaying@."; *)
(*       let c = st.st_type in *)
(*       let find_edge e = *)
(*         let comp_edges e { edge_nodes = e'} = compare_ids_edges e e' in *)
(*         List.find (comp_edges e) st.st_constraint.constraints#get *)
(*       in *)
(*       List.iter (fun e -> *)
(*                    let e = find_edge e in *)
(*                    ignore (match e.edge_type with *)
(*                       | Unif -> self#unif_aux c e.edge_nodes *)
(*                       | Inst -> self#inst_aux c e); *)
(*                    self#add_history (); *)
(*                 ) l; *)
(*       self#refresh (); *)


    (* Event handling *)

    method at_pos ?(all=false) x y : int list * int list * int list =
      ignore all;
(*       let c = st.st_constraint in *)
(*       let nodes, edges = odot#at_pos x y in *)
(*       let node_int s = int_of_string (String.sub s 1 (String.length s - 1)) in *)
(*       let edges = List.map (fun (s1, s2) -> (node_int s1, node_int s2)) edges *)
(*       and nodes = List.map node_int nodes in *)
(*       let filter f l = List.filter *)
(*         (fun e -> List.exists (fun e' -> f e e') l) in *)
(*       let comp_edges { edge_nodes = e'} e = compare_ids_edges e e' in ( *)
(*       (\* The "unique" remove existential nodes that have been merged *)
(*          and edges present more than once because control points are too *)
(*          near *\) *)
(*         Utils.unique equal_constraints *)
(*           (filter comp_edges edges c.constraints#get), *)
(*         Utils.unique Nodes.equal *)
(*           (filter compare_ids nodes c.exists#get), *)
(*         if all then *)
(*           Utils.unique Nodes.equal (filter compare_ids nodes (all_nodes c)) *)
(*         else *)
(*           [] *)
(*       ) *) 
      let c = st.st_type in
      let nodes, edges = odot#at_pos x y in
      let node_int s = int_of_string (String.sub s 1 (String.length s - 1)) in
      let edges = List.map (fun (s1, s2) -> (node_int s1, node_int s2)) edges
      and nodes = List.map node_int nodes in
      let filter f la lb = List.filter
        (fun a -> List.exists (fun b -> f b a) lb) la in
      ignore (c, edges, filter);
      (* filter (fun u n -> GType.id u = n) nodes st.st_type.Expr.nodes *)
      List.iter (Printf.printf "\t%d\n") nodes;
      [], nodes, []

    method on_left_click ~nodes ~edges =
      ignore (nodes, edges)
(*       match edges, nodes with *)
(*         | [], [] -> () *)
(*         | [{ edge_type = Unif } as e], _ -> self#unif e *)
(*         | [{ edge_type = Inst } as e], _ -> self#inst_or_expand e *)
(*         | [], [n] -> self#remove_existential n *)
(*         | _ :: _ :: _, _  -> *)
(*             GToolbox.message_box "MLF" "Ambiguity between two edges" *)
(*         | [], _ :: _ :: _ -> *)
(*             GToolbox.message_box "MLF" "Ambiguity between two nodes" *)


    method on_right_click ~edges ~nodes ~all_nodes =
      ignore (edges, nodes, all_nodes);
(*       let menu_exists_nodes = List.fold_left *)
(*         (fun menu n -> *)
(*            `I (Printf.sprintf "Remove existential node %d" (nid n), *)
(*                (fun () -> self#remove_existential n)) :: *)
(*              menu *)
(*         ) [] nodes *)
(*       and menu_all_nodes = List.fold_left *)
(*         (fun menu n -> *)
(*            `I (Printf.sprintf "Raise node %d" (nid n), *)
(*                (fun () -> self#raise_node n)) :: *)
(*            `I (Printf.sprintf "Try expanding the node %d" (nid n), *)
(*                (fun () -> self#expand_alias n)) :: *)
(*              menu *)
(*         ) [] all_nodes *)
(*       and menu_edges = List.fold_left *)
(*         (fun menu e -> *)
(*            let s = edge_description e in *)
(*            match e.edge_type with *)
(*              | Unif -> `I (Printf.sprintf "Unify %s" s, *)
(*                            (fun () -> self#unif e)) :: menu *)
(*              | Inst -> *)
(*                  `I (Printf.sprintf "Inst-Expand on %s" s, *)
(*                      (fun () -> self#inst e)) :: *)
(*                  `I (Printf.sprintf "Expansion test on %s" s, *)
(*                      (fun () -> self#expand e)) :: *)
(*                  menu *)
(*         ) [] edges *)
(*       in *)
(*       let entries = menu_exists_nodes @ menu_all_nodes @ menu_edges in *)
(*       if entries <> [] then *)
      (*         GToolbox.popup_menu ~entries ~button:3 ~time:Int32.zero *)
      let popup_node n =
	GToolbox.message_box "MLF" (Printf.sprintf "Node %d" n) in
      List.iter popup_node all_nodes


    method reset_program_dropdown =
      if expr_ok then (
        combo_exprs#set_popdown_strings (string_choose :: lexprs#get);
        combo_exprs#entry#set_text string_choose;
      )



    initializer

      ignore
	(odot#evt_box#event#connect#button_press ~callback:
	   (fun evt ->
              btreset#misc#grab_focus ();
              self#reset_program_dropdown;
              GdkEvent.get_type evt = `BUTTON_PRESS &&
	       (let x = int_of_float (GdkEvent.Button.x evt) in
		let y = int_of_float (GdkEvent.Button.y evt) in
	        match GdkEvent.Button.button evt with
	          | 1 ->
                      let edges, nodes, _ = self#at_pos x y in
                      self#on_left_click ~nodes ~edges;
                      true;
	          | 3 ->
                      let edges, nodes, all_nodes = self#at_pos ~all:true x y in
                      self#on_right_click ~nodes ~edges ~all_nodes;
                      true
	          | _ -> false
               )
	   ));

      ignore
	(let last_edge_msg = ref None in
         let dismiss_msg () = match !last_edge_msg with
           | None -> ()
           | Some m -> status#remove m in
         odot#evt_box#event#connect#motion_notify ~callback:
	   (fun evt ->
              let x = int_of_float (GdkEvent.Motion.x evt) in
	      let y = int_of_float (GdkEvent.Motion.y evt) in
              let win = w#misc#window in
              dismiss_msg ();
              (match self#at_pos x y with
                 | [e], [], _ ->
                     ignore e;
                     Gdk.Window.set_cursor win (Gdk.Cursor.create `HAND2);
(*                      last_edge_msg := Some *)
(*                        (status#push *)
(*                           (ConstraintsMeaning.fragment_from_meaning *)
(*                              st.st_expr_text e.edge_meaning)) *)
                 | [], [_], _ ->
                     Gdk.Window.set_cursor win (Gdk.Cursor.create `HAND2);
                 | _ ->
                     Gdk.Window.set_cursor win (Gdk.Cursor.create `LEFT_PTR);
              ); true
           ));

      odot#evt_box#event#add [`BUTTON_PRESS; `POINTER_MOTION];

      let button (bt : GButton.button) f =
        let f () = self#reset_program_dropdown; f () in
        ignore (bt#connect#clicked ~callback:f);
      and option (chk : GButton.toggle_button) ?(update=fun () -> ()) option =
        chk#set_active !option;
        ignore (chk#connect#toggled (fun () ->
                                       option:= not !option;
                                       self#reset_program_dropdown;
                                       update ();
                                    ));
      in

      button btprev self#back;
      button btnext self#next;
      button btdump self#state_to_file;
      (* option chkheight ~update:self#refresh inst_constrains_height; *)
      (* option chksort ~update:self#refresh sort_edges; *)
(*       option chkchildren_number ~update:self#refresh show_children_number; *)
(*       option chkstruct_end ~update:self#refresh show_struct_end; *)
      option chkids ~update:self#refresh print_nodes_id;
      (* option chkmono ~update:self#refresh gc_nodes; *)
      option chnf ~update:(fun () -> self#update_status_solved) normal_forms;
      option chinline_poly ~update:(fun () -> self#update_status_solved)
        inline_types;
(*       button btclean self#clear_unconstrained; *)
(*       option chkclean auto_remove_unconstrained; *)
(*       button btcheck self#wf_constraint; *)
(*       option chkcheck check_at_each_step; *)
(*       option chkautounif auto_unif_after_inst; *)
(*       option chkmlexpansion ml_expansion; *)
      button btsolveone self#solve_one;
      button btsolveall self#solve_all;
(*       button btconfluence (fun () -> self#confluence *)
(*                              (int_of_float adjustment_confluence#value)); *)

(*       chkmlconstraints#set_active !ml_constraints; *)
(*       ignore (chkmlconstraints#connect#toggled *)
(*                 (fun () -> *)
(*                    self#reset_program_dropdown; *)
(*                    ml_constraints:= not !ml_constraints; *)
(*                    if self#load_expr_success () = false then ( *)
(*                      ml_constraints:= not !ml_constraints; *)
(*                      chkmlconstraints#set_active !ml_constraints; *)
(*                    ))); *)
(*       option chksolvedbottoms ~update:self#load_expr shortcut_bottoms; *)
(*      option chksolvedseqabs ~update:self#load_expr shortcut_seqabs; *)
(*       option chksolvedvalues ~update:self#load_expr shortcut_forall; *)
(*      option chkrigid ~update:self#load_expr rigid_right_coercions; *)
(*       option chkapp_before_arg ~update:self#load_expr solve_app_before_arg; *)
      button btreset self#load_expr;

(*       ignore (butelim#connect#toggled (fun () -> elim_expand := Elim)); *)
(*       ignore (butexpand#connect#toggled (fun () -> elim_expand := Expand)); *)

      combo_exprs#entry#set_text string_choose;
      ignore (combo_exprs#entry#connect#changed
                (fun () -> let expr = combo_exprs#entry#text in
                 if expr <> string_choose then
                   self#load_expr ~refresh:false ~expr ();
                )
             );

      ignore (combo_exprs#entry#event#connect#focus_in
                (fun _ ->
                   if combo_exprs#entry#text = string_choose then
                     combo_exprs#entry#set_text "";
                   false)
             );

      self#add_history ();
      self#refresh ();
  end

let show env st =
  ignore (GMain.Main.init ());
  let w = GWindow.window ~width:700 ~title: "MLF" () in
  w#misc#realize ();
  let b = new box w st "mlfdot" env in
  w#add b#box#coerce;
  ignore (w#connect#destroy GMain.Main.quit);
  w#show ();
  GMain.Main.main ();
;;

let state_file = ref ""
let prg = ref ""

let options = 
  [
   (* "-unicode", Arg.Set unicode, "Use Unicode type constructors"; *)
   "-load", Arg.Set_string state_file, "Reload a dumped state";
 ]

