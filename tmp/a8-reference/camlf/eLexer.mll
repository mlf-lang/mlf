{
  open Lexing
  open EParser
  open SyntaxErrors

  let keywords = [
    "fun", FUN;
    "lam", LAMBDA;
    "Fun", FFUN;
    "let", LET;
    "in", IN;
    "if", IF;
    "then", THEN;
    "else", ELSE;
    "val", VAL;
    "type", TYPE;
    "some", SOME;
    "of", OF;
(*    "match", MATCH;
    "with", WITH;*)
    "rec", REC
  ]

  let directives = [
    "include", INCLUDE;
    "global", GLOBAL;
    "local", LOCAL;
    "", LOCAL;
    "help", HELP;
  ]

  let newline lexbuf =
    lexbuf.lex_curr_p <- { lexbuf.lex_curr_p with
                             pos_lnum = lexbuf.lex_curr_p.pos_lnum + 1;
                             pos_bol =  lexbuf.lex_curr_p.pos_cnum;
                         }

  let in_comment = ref false


(* included from ocaml lexer.mll *)
let in_pattern () = not !in_comment
let string_buff = Buffer.create 256
let reset_string_buffer () = Buffer.clear string_buff
let store_string_char c = Buffer.add_char string_buff c
let get_stored_string () = Buffer.contents string_buff
let char_for_backslash = function
    'n' -> '\n'
  | 't' -> '\t'
  | 'b' -> '\b'
  | 'r' -> '\r'
  | c   -> c

let warning lexbuf msg =
  let p = Lexing.lexeme_start_p lexbuf in
  Printf.eprintf "ocamllex warning:\nFile \"%s\", line %d, character %d: %s.\n"
    p.Lexing.pos_fname p.Lexing.pos_lnum
    (p.Lexing.pos_cnum - p.Lexing.pos_bol + 1) msg;
  flush stderr

let decimal_code  c d u =
  100 * (Char.code c - 48) + 10 * (Char.code d - 48) + (Char.code u - 48)

let char_for_hexadecimal_code d u =
  let d1 = Char.code d in
  let val1 = if d1 >= 97 then d1 - 87
             else if d1 >= 65 then d1 - 55
             else d1 - 48
  in
  let d2 = Char.code u in
  let val2 = if d2 >= 97 then d2 - 87
             else if d2 >= 65 then d2 - 55
             else d2 - 48
  in
  Char.chr (val1 * 16 + val2)

let incr_loc lexbuf delta =
  let pos = lexbuf.Lexing.lex_curr_p in
  lexbuf.Lexing.lex_curr_p <- { pos with
    Lexing.pos_lnum = pos.Lexing.pos_lnum + 1;
    Lexing.pos_bol = pos.Lexing.pos_cnum - delta;
  }
;;


}

let newline = ('\n' | '\r' | "\r\n" "\n\r")
let any_ident_char = ['0'-'9'  'a'-'z'  'A'-'Z'  '_'  '\'']
(* included from lexer.mll *)
let backslash_escapes =
  ['\\' '"' '\'' 'n' 't' 'b' 'r']

rule token = parse
| [' ' '\t']+
    { token lexbuf }
| newline
    { newline lexbuf;
      token lexbuf }

| "(*"
    { in_comment := true;
      comment [Locations.curr_loc lexbuf] lexbuf;
      token lexbuf }

| ['a'-'z'] any_ident_char* as s
    { try List.assoc s keywords
      with Not_found -> LIDENT s }

| "A" { A }

| ['A'-'Z'] any_ident_char* as s
    { try List.assoc s keywords
      with Not_found -> UIDENT s }

| '#' (['a'-'z' '_' '.']* as s)
    { try List.assoc s directives
      with Not_found ->
        raise (LexingError (InvalidDirective (Locations.curr_loc lexbuf, s))) }

| '\'' (['a'-'z']+ as s)
    { QUOTELIDENT s }

| ['0'-'9']+ as i
    { INT (int_of_string i) }

| '_'
    { UNDER }
| ':'
    { COLON }
| ','
    { COMMA }
| ';'
    { SEMI }
| ";;"
    { SEMISEMI }
| '.'
    { DOT }

| '>'
    { GREATER }
| '='
    { EQUAL }
| '*'
    { STAR }
(*| '\\'
    { FUN }*)
| '|'
    { PIPE }
| '!'
    { BANG }
| '^'
    { CIRCUMFLEX }

| '+'
    { PLUS }
| '-'
    { MINUS }

| "->"
    { ARROW }
| "@"
    { AROBASE }

| '('
    { LPAREN }
| ')'
    { RPAREN }
| '['
    { LBRACKET }
| ']'
    { RBRACKET }
| eof
    { EOF }
| '"'
    { reset_string_buffer();
      string (Locations.curr_loc lexbuf) lexbuf;
      STRING (get_stored_string()) }
| _
    { raise (LexingError (InvalidChar (Locations.curr_loc lexbuf,
                                       Lexing.lexeme_char lexbuf 0))) }

and comment l = parse
| "*)"
    { match l with
        | [] -> assert false
        | [_] -> in_comment := false
        | _ :: q -> comment q lexbuf
    }
| "(*"
    { comment (Locations.curr_loc lexbuf :: l) lexbuf }
| newline
    { newline lexbuf;
      comment l lexbuf }
| eof { in_comment := false;
        raise (LexingError (UnterminatedComment (List.hd l))) }
| _
    { comment l lexbuf }


(* included from ocaml lexer.mll *)
(* String parsing comes from the compiler lexer *)
and string loc = parse
    '"'
    { () }
   | '\\' ("\010" | "\013" | "\013\010") ([' ' '\009'] * as spaces)
    { incr_loc lexbuf (String.length spaces);
      string loc lexbuf }
  | '\\' (backslash_escapes as c)
    { store_string_char(char_for_backslash c);
      string loc lexbuf }
  | '\\' (['0'-'9'] as c) (['0'-'9'] as d) (['0'-'9']  as u)
    { let v = decimal_code c d u in
      if in_pattern () && v > 255 then
       warning lexbuf
        (Printf.sprintf
          "illegal backslash escape in string: `\\%c%c%c'" c d u) ;
      store_string_char (Char.chr v);
      string loc lexbuf }
 | '\\' 'x' (['0'-'9' 'a'-'f' 'A'-'F'] as d) (['0'-'9' 'a'-'f' 'A'-'F'] as u)
    { store_string_char (char_for_hexadecimal_code d u) ;
      string loc lexbuf }
  | '\\' (_ as c)
    {if in_pattern () then
       warning lexbuf
        (Printf.sprintf "illegal backslash escape in string: `\\%c'" c) ;
      store_string_char '\\' ;
      store_string_char c ;
      string loc lexbuf }
  | eof
    { raise (LexingError (UnterminatedString loc)) }
  | '\010'
    { store_string_char '\010';
      incr_loc lexbuf 0;
      string loc lexbuf }
  | _ as c
    { store_string_char c;
      string loc lexbuf }
