open GType

let implicit_dotted =
  Options.flag false (* true *) "--implicit_dotted"
    "Show implicit bindings in dotted lines"

let poly t =
  match edges t with
  | t' :: _ when eqrepr (bound t') t ->  true
  | _ -> false;;

type elem =
    Decl of string
  | Edge of gtype * gtype * edge_kind
  | Node of gtype
  | Cluster of gtype * elem list
and edge_kind =
  | Struct of int
  | Binding
  | Inst of instance_flag * GMeaning.constraint_meaning

let interior tg t =
  match binder t with
  | Undef -> assert false
  | Root -> true
  | Bound (_, t') -> blevel t' >= blevel tg

let cluster from t =
  if root t then from
  else if interior from t then from
  else
    match binder t with
    | Undef -> assert false
    | Root -> from
    | Bound (_, tg) ->
        let () = assert (gen_node tg) in
        tg

let id t = (U.find t).id;;

module D = Map.Make
    (struct
      type t = gtype
      let compare = GType.compare
    end);;

let decompose ?(proj=true) t =
  let visiting = new_status () in
  let visited = new_status () in
  let rec collect env from t =
    assert (gen_node from);

    let u = U.find t in
    if !(u.status) = visiting then raise (Cycle t);

    if !(u.status) =  visited then ()
    else

      let env' = if gen_node t then D.add t (ref []) env else env in
      let from' = if gen_node t then t else from in
      let collect = collect env' from' in

      let find t = D.find t env' in
      let add t e =
        try
          let c = find t in c := e::!c
        with Not_found ->
          assert (gen_node t);
          assert false
      in
      let c = cluster from t in
      add c (Node t);
      if root t then ()
      else add c (Edge (t, bound t, Binding));
      if gen_node t then
        List.iter
          (fun (ti, ti_flag, ti_meaning) ->
             let ci = bound ti in
             let cc = lcb c ci in
             assert (gen_node cc);
             assert (blevel cc <= blevel c);
             add cc (Edge (t, ti, Inst (ti_flag, ti_meaning))))
          (gen_info t).inst;
      Utils.iteri
        (fun i te ->
          let cc =
            if interior c te then c
            else lcb c (bound te) in
          assert (gen_node cc);
          assert (blevel cc <= blevel c);
          add cc (Edge (t, te, Struct i)))
        1
        u.edges;
      u.status := visiting;
      List.iter collect u.edges;
      if proj && gen_node t then () else
          List.iter collect (gen_info t).exist;
      u.status := visited;
      if gen_node t then
        let cl = !(find t) in
        let old = (D.find from env) in
        old :=  Cluster (t, List.rev cl) :: !old;
        () in
  let tenv = ref [] in
  let env = D.add t tenv D.empty in
  collect env t t;
  close_status visiting visited;
  List.rev !tenv

let print_header ?name buf =
  Printf.bprintf buf
    "digraph G {\n  \
    nodesep=0.55;\n  \
    node [fixedsize=\"false\", width=.45, height=.4];\n  \
    ordering=out;\n%s"
    (match name with None -> ""
      | Some name -> "label=\"" ^ name ^ "\";\n")
;;

let print_footer buf =
  Printf.bprintf buf "}\n\n";
;;

let emph_among li s =
  if List.exists (eqrepr s) li
  then Some "purple"
  else None

let node_color emph t =
  match emph t with
  | Some s -> s
  | None ->
      if gen_node t then if poly t then "pink" else "white"
      else
        if inert t then "cyan"
        else if rigid t || frozen t then "orange"
        else if locked t then "red"
        else if instantiable t then "green"
        else assert false

let flags_color = function
  | Flexible, Free -> "blue"
  | Flexible, Frozen -> "cyan1" (* darker than cyan *)
  | Rigid, Free -> "gray"
  | Rigid, Frozen -> "darkviolet" (* darker than gray *)

let name t = string_of_int (U.find t).id

let label ?(ids=false) t =
  let label_kind = function
    | K.Star -> ""
    | k -> Printf.sprintf " : %s" (K.string_of_kind ~verbatim:true k) in
  let label = match constr t with
    | Constant c ->
        begin match c with
        | Int -> "int"
        | Unit -> "unit"
        | Bool -> "bool"
        end
    | Bot _ -> "_"
    | Arrow -> "->"
    | Apply (_, _) -> "@"
    | Lambda (_, _) -> "lam"
    | Forall _ -> "F"
    | Gen (_, g) -> begin
      let module L = Locations in
      let prefix = match g.expr.L.obj with
        | `Root -> "root"
        | `Abs _ -> "abs"
        | `Let _ -> "let"
        | `Value _ -> "val"
        | `TyAbs _ -> "tyabs"
        | `TyApp _ -> "tyapp"
        | `App _ -> "app"
        | `Type _ -> "type"
        | `SomeTy _ -> "some"
        | `CoerceCt _ -> "coerce"
        | `Ct (_, _) -> "constant"
        | `BuiltinCt _ -> "builtin" in
      let tag, content =
        let loc = g.expr.L.loc in
        if not loc.L.loc_ghost && Options.use_source_labels
        then "", " " ^ String.escaped (L.string_of_loc loc)
        else "G ", "" in
      Printf.sprintf "%s[%s]%s" tag prefix content
    end in
  Printf.sprintf "%s%s%s"
    (if ids then Printf.sprintf "%d " (id t) else "")
    label
    (label_kind (kind_of_constr (constr t)))

let string_of_instance tg inst_flag meaning t =
  ignore meaning; (* TODO display meaning *)
  Printf.sprintf
    "  %s -> %s [color=%s,weight=10,style=%s%s%s];\n"
    (name tg) (name t)
    (if poly tg then "red" else "pink")
    (if poly tg then "bold" else "solid")
    (if true then "" else ",constraint=false")
    (match inst_flag with `Implicit -> "" | `Explicit -> ",label=E")

let default_none _ = None
let default_false _ = false
let draw_graph
    ?(ids=false)
    ?(emph=default_none)
    ?(hide=default_false)
    ?(proj=true) buf t =
  let color = node_color emph in
  let id t = string_of_int (U.find t).id in
  let name buf t = Printf.bprintf buf "n%d" (U.find t).id in
  let rec draw rank g =
    begin match g with

      | Decl _ -> ()

      | Cluster (tg, cl) ->
          Printf.bprintf buf "subgraph cluster_%s {\n" (id tg);
          let color =
            match rank mod 3 with
              | 0 -> "khaki"
              | 1 -> "bisque"
              | 2 ->  "aquamarine"
              | _ ->  "gold" in
          Printf.bprintf buf "bgcolor=%s;\n" color;
          List.iter (draw (rank + 1)) cl;
          Printf.bprintf buf "}\n";

      | Node t ->
          Printf.bprintf buf
            "  %a [label=\"%s\",shape=\"%s\",\
          style=\"filled,rounded\",fillcolor=%s];\n"
            name t
	    (label ~ids t)
            (if gen_node t then "box" else "ellipse")
            (color t);

      | Edge (t, t', Struct i) ->
          Printf.bprintf buf
            "  %a -> %a [label=\"\",group=\"struct\",weight=10,\
          arrowhead=%s,color=black%s,arrowtail=%s];\n"
            name t name t'
            (if i = 1 then "none" else "none")
            (if false then "" else ", dir=forward")
            (if gen_node t then "none" else if i = 1 then "dot" else "odot")

      | Edge (t, _t', Binding) ->
          begin
            match binder t with
              | Undef -> assert false
              | Root -> ()
              | Bound (flags, t') ->
                  let style =
                    if hide t then
                      if !implicit_dotted
                      then "dir=back,style=dotted,arrowtail=open"
                      else "dir=none,style=invisible"
                    else
                      let is_existential =
                        gen_node t' && List.exists (eqrepr t) (gen_info t').exist in
                      if is_existential
                      then (Printf.printf "Exist %s %s\n%!" (id t) (id t');
                            "dir=back,style=dashed")
                      else "dir=back" in
                  Printf.bprintf buf
                    "  %a -> %a [color=%s,%s];\n"
                    name t' name t
                    (flags_color flags)
                    style
          end
      | Edge (tg, t, Inst (inst_flag, meaning)) ->
          Buffer.add_string buf (string_of_instance tg inst_flag meaning t)
    end in
  let g = decompose ~proj:(proj) t in
  begin match g with
    | [ Cluster (_, _) as g  ] ->
        print_header buf;
        draw 0 g;
        print_footer buf
    | _ -> assert false;
  end;;


let print_gtype ?(ids=true) ?(emph=default_none) ?(proj=false) buf ?(other_roots=[]) t =
  let b1 = Buffer.create 100 and b2 = Buffer.create 100 in
  let color = node_color emph in
  let unseen visit t =
    Printf.bprintf b1
      "  %s [label=\"%s\", shape=\"%s\", style=\"filled,rounded\", fillcolor=%s];\n"
      (name t)
      (label ~ids t)
      (if gen_node t then "box" else "ellipse")
      (color t);
    let print_edge i t' =
      Printf.bprintf b1
        "  %s -> %s [%s,color=%s,style=%s,arrowhead=none%s];\n"
        (name t) (name t')
        "group=struct,dir=forward,weight=10"
        (if i = 1 then "black" else "black")
        (if gen_node t then "bold" else "solid")
        (match constr t with
           | Constant (Int | Bool | Unit) | Bot _ | Gen (_, _) -> ""
           | Arrow | Forall _ | Lambda (_, _) | Apply (_, _) ->
               ",tailport=" ^ if i = 1 then "sw" else "se") in
    Utils.iteri print_edge 1 (edges t);

    let print_exist t' =
      Printf.bprintf b1
        "  %s -> %s [weight=3,style=invisible,dir=none];\n"
        (name t) (name t') in
    if gen_node t then
      List.iter print_exist (gen_info t).exist;

    begin match binder t with
      | Undef -> assert false
      | Root -> ()
      | Bound (flags, t') ->
          (* visit t' might be useful in we went to t' by other_roots,
             and it is out of the graph (not in the main structure
             tree).  as happen for temporary nodes created by
             expansions and type reductions *)
          visit t';
          let is_existential =
            gen_node t' && List.exists (eqrepr t) (gen_info t').exist in
          (* if List.exists (eqrepr t) (U.find t').exist then () else *)
          Printf.bprintf b2
            "  %s -> %s [color=%s,style=%s];\n"
            (name t) (name t')
            (flags_color flags)
            (if gen_node t then "bold"
             else if is_existential then "dashed"
             else "solid")
      end;
      List.iter visit (edges t);
      if not proj && gen_node t then
        List.iter visit (gen_info t).exist in

    let status = GType.fresh_status () in
    List.iter
      (dps ~force_reentrant:true ~status ~acyclic:false unseen)
      (t :: other_roots);

  Printf.bprintf buf "subgraph cluster_graph {\n\n%a}\n\n%a\n" 
    Buffer.add_buffer b1 Buffer.add_buffer b2
;;


let print_inst b ?(other_roots=[]) t =
  let print_inst tg (t, inst_flag, meaning)  =
    Printf.bprintf b " %s" (string_of_instance tg inst_flag meaning t) in
  let unseen visit t =
    if gen_node t then begin
      List.iter (print_inst t) (gen_info t).inst;
      List.iter visit (gen_info t).exist;
    end in
  let status = GType.fresh_status () in
  List.iter
    (dps ~status ~acyclic:false unseen)
    (t :: other_roots)
;;


let print_constraint ?name ?ids ?emph ?proj buf ?other_roots t =
  print_header ?name buf;
  print_gtype ?ids ?emph ?proj buf ?other_roots t;
  print_inst buf ?other_roots t;
  print_footer buf;
;;

let v = ref 0
let dot_dir, dot_ext = "dot", "dot"
let sources = ref []

let generate_basename name_suffix =
  incr v;
  let name = match name_suffix with
  | None -> ""
  | Some suffix -> "_" ^ suffix in
  Printf.sprintf "%02d%s" !v name

let generate_path name_suffix =
  Filename.concat dot_dir
    (generate_basename name_suffix ^ "." ^ dot_ext)

let to_file ?name_suffix f =
  let buf = Buffer.create 1024 in
  let temp = generate_path name_suffix in
  let out = open_out temp in
  (try
     f buf;
     Buffer.output_buffer out buf;
     sources := temp :: !sources
   with Sys_error err -> prerr_endline err);
  close_out out

let dump ?name ?ids ?emph ?proj ?other_roots t =
  to_file ?name_suffix:name (fun buf ->
    print_constraint ?name ?ids ?emph ?proj buf ?other_roots t)

let root = ref None
let register_root tg = root := Some tg;;
let unregister_root() = root := None;;

let dump_from_root nodes =
  match !root with
  | None -> ()
  | Some tr -> dump ~emph:(nodes) tr

let drum 
    ?name_suffix
    ?ids ?emph ?hide ?proj
    ?other_roots t
    =
  let ignore = ignore in ignore hide;
  let print ch =
    print_constraint ?name:name_suffix
      ?ids ?emph ?proj ch
      ?other_roots t in
  let _ =  to_file ?name_suffix print in ()
  ;;

let printable_snapshot ?(name="gmlf_snapshot") ?ids ?emph ?proj ?other_roots t =
  let buf = Buffer.create 1024 in
  print_constraint ~name ?ids ?emph ?proj buf ?other_roots t;
  (fun ?name_suffix () ->
    let out = open_out (generate_path name_suffix) in
    Buffer.output_buffer out buf;
    close_out out)  

let concat() =
  let sources = List.rev !sources in
(*   let dot2svg src = *)
(*     let dest = Filename.chop_extension src ^ ".svg" in *)
(*     let r = Sys.command (Printf.sprintf "dot -Tsvg -o %s %s" dest src) in *)
(*     if r <> 0 then failwith "Dot error" in *)
(*   let () = List.iter dot2svg sources in *)
  if sources = [] then failwith "Dot error : no dot file found";
  let all_files = String.concat " " sources in
  let basename = Filename.concat dot_dir "mlf" in
  let cmd = Printf.sprintf "dot -Tps -o %s.eps %s" basename all_files in
  prerr_endline cmd;
  let r = Sys.command cmd in
  if r <> 0 then failwith "Dot error";
  let cmd = Printf.sprintf "mv %s.eps %s.ps" basename basename in
  let r = Sys.command cmd in
  if r <> 0 then failwith "Dot error"
;;

