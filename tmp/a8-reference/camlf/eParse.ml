open AST
open EType
open Locations
open Format

(* Utilitary functions for creating parsing input *)
let input_from_string src = Lexing.from_string src

let input_from_file_option file =
  let name, chan =
    match file with
    | Some filename ->
        filename, open_in filename
    | None -> "", stdin in
  let lexbuf = Lexing.from_channel chan in
  lexbuf.Lexing.lex_curr_p <- { 
    Lexing.pos_fname = name; 
    Lexing.pos_lnum  = 1;
    Lexing.pos_bol   = 0; 
    Lexing.pos_cnum  = 0
  };
  let source =
    match file with
    | Some filename -> File (filename, lexbuf)
    | None -> Stdin lexbuf in
  lexbuf, source

(* wrapper handling the !Locations.loc_source state
   during parsing *)
let with_source source f =
  let old_source = get_source () in
  Utils.protect
    ~before:(fun () -> set_source source)
    f
    ~finally:(fun () -> set_source old_source)
    ()

(** Parsing functions (wrappers around eparser.mly parsers) *)
let parse_from_string parsing_fun src =
  let input = input_from_string src in
  try
    with_source (String src)
      (fun () -> parsing_fun ELexer.token input)
  with e ->
    ErrorsHandling.report_error err_formatter e;
    raise e
;;

let expr = parse_from_string EParser.expr_

let typ = parse_from_string EParser.polytype_

let phrase_of_named_string (id, str) =
    let id = { obj = s_value id; loc = loc_of_string id; } in
    let exp = expr str in
    let p = AST.Val (`NonRec, `Unconstrained id, exp) in
    { obj = p; loc = exp.loc; }

let file src =
  let input, source = input_from_file_option src in
  try
    with_source source
      (fun () -> EParser.expr_ ELexer.token input)
  with e ->
    ErrorsHandling.report_error err_formatter e;
    raise e
;;

let phrases src =
  let input, source = input_from_file_option src in
  try
    with_source source
      (fun () -> EParser.phrases_ ELexer.token input)
  with e ->
    ErrorsHandling.report_error err_formatter e;
    raise e
;;

let toplevel_phrase token lexbuf =
  (* no error reporting : it is handled by the toploop, wich is aware
     of lexing errors etc. *)
  with_source (Toplevel lexbuf)
    (fun () -> EParser.toplevel_phrase token lexbuf)
