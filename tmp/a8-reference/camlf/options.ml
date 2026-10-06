(** This modules allows to add options to the command line
   in different modules way *)

let options = ref [];;

let all () = List.rev !options;;

let add option_name action man =
  options := (option_name, action, man) :: !options;;

let add_shortcut short_name long_name =
  let (_, action, _) =
    let ok (name, _, _) = (name = long_name) in
    try List.find ok !options
    with _ -> failwith "add_shortcut" in
  add short_name action (Printf.sprintf "short for %s" long_name)


(** A special case: flag options *)
let flag init option_name message =
  let r = ref init in
  add option_name
    (if init then Arg.Clear r else Arg.Set r)
    message;
  r;;

(** Another special case: debug options (init value is false). *)
let debug option_name message =
  let r = ref false in
  add option_name (Arg.Set r) message;
  (fun s -> if !r then prerr_endline s);;

(** global options *)
let inline_types =
   flag true "--inline_types" "inline types";;

let sequence_has_type_unit =
   flag true "--sequence_has_type_unit" "sequence has type unit";;

let minimize_parentheses = 
   flag true "--minimize_parentheses" "minimize parentheses";;

let use_source_labels = false || true

(** Config flag options *)
let add_config_flag conf_ref ?short flag =
  let action flag =
    conf_ref := Config.set !conf_ref flag in
  add
    ("--" ^ flag.Config.name)
    (Arg.Unit (fun () -> action flag))
    flag.Config.short_descr;
  begin match short with
    | None -> ()
    | Some short ->
      add_shortcut short ("--"^flag.Config.name)
  end
    
