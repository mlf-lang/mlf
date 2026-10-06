open GType

(* printing *)

let string_of_constr : constr -> string =
  function
  | Constant c ->
      begin match c with
      | Int -> "int"
      | Bool -> "bool"
      | Unit -> "unit"
      end
  | Bot _ -> Symbol.bot ()
  | Arrow -> Symbol.arrow ()
  | Apply (_, _) -> "@"
  | Lambda (_, _) -> Symbol.lambda ()
  | Forall _ -> Symbol.forall ()
  | Gen (_, _) -> "G"

let string_of_symbol symbol =
  string_of_constr symbol.constr

type option = All
let options = ref []
let enable opt = List.mem opt !options || List.mem All !options

let print_node namer k t =
  let name = namer (id t) in
  let bound =
    match binder t with
      | Undef -> "?"
      | Root -> ""
      | Bound (_, t') -> Printf.sprintf "@%s" (namer (id t')) in
  let flag =
    let context =
      if not (enable All) then ""
      else
        if instantiable t then "+"
        else if inert t then "."
        else "-" in
    let flex = if rigid t then "-" else "+" in
    context ^ flex in
  k name flag bound (string_of_symbol (node t))


let print_gtype ?acyclic ?namer:n out : gtype -> unit =
  let namer =
    match n with
      None -> Utils.namer()
    | Some n -> n in
  let print_node =
    print_node namer
      (Printf.sprintf "%s%s%s:%s")in
  let seen g =
    Printf.bprintf out "%s" (namer (id g)) in
  let unseen visit t =
    let visit _out = visit in
    begin match edges t with
      [ t1; t2; ] ->
        Printf.bprintf out "(%a %s %a)"
          visit t1 (print_node t) visit t2
    | [ t1; ] ->
        Printf.bprintf out "(%s %a)" (print_node t) visit t1
    | [] ->
        Printf.bprintf out "%s" (print_node t)
    | _ -> assert false
    end;
  in
  let status = GType.fresh_status () in
  dps ?acyclic ~seen ~status unseen
;;

let print_list f left before after right out l =
  Format.fprintf out "@;@[<hov 2>%s" left;
  List.iter
    (fun x ->
      Format.fprintf out before;
      f out x;
      Format.fprintf out "%s@;" after)
    l;
  Format.fprintf out "%s@]" right;;

let emap _g = raise Not_found;;

let draw_gtype ?exist:(all=true) ?namer:n out t =
  let namer =
    match n with
      None -> Utils.namer()
      | Some n -> n in
  let print_node =
    print_node namer
      (Format.fprintf out "@[<hov 2>%s%s%s:%s@,%a@]")in
  let seen t =
    Format.fprintf out "%s" (namer (id t)) in
  let unseen visit t =
    let visit _out = visit in
    let print_expr out t =
      let module L = Locations in
      match constr t with
      | Gen (_, {expr = {L.loc = {L.loc_ghost = false} as loc}}) ->
          Format.fprintf out "<%s>" (L.string_of_loc loc)
      | _ -> () in
    let print_symbol _out t =
      print_node t print_expr t in
    begin match edges t with
      [ t1; t2; ] ->
        Format.fprintf out "@[(%a@;%a@;%a)@]"
          visit t1 print_symbol t visit t2
      | [ t1; ] ->
          Format.fprintf out "(%a@;%a)"
            print_symbol t
            visit t1
      | [] ->
          Format.fprintf out "%a" print_symbol t
      | _ -> assert false
    end;
    if all && gen_node t then
      begin
        begin match (gen_info t).inst with
           | [] -> ()
           | l ->
             let get_node (node, _flag, _meaning) = node in
             print_list visit " [" " => " " |" "]" out (List.map get_node l)
        end;
        begin match (gen_info t).exist with
           | [] -> ()
           | l -> print_list visit " [" " " ";" "]" out l
        end;
      end
  in
  Format.printf "@[";
  dps ~seen unseen t;
  Format.printf "@]\n%!";
;;
