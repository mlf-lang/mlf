open Highlight
open Locations
open Format

type lexing_error =
  | InvalidChar of location * char
  | UnterminatedComment of location
  | UnterminatedString of location
  | InvalidDirective of location * string

type parsing_error =
  | Unclosed of (string * location) * string * (string * location)
  | ParseError of string * location

exception LexingError of lexing_error
exception ParsingError of parsing_error

let report_lexing_error ppf = function
  | InvalidChar (loc, c) ->
      print_loc ppf loc;
      fprintf ppf "Illegal character %s" (Char.escaped c);
  | UnterminatedComment loc ->
      print_loc ppf loc;
      fprintf ppf "Unterminated comment";
  | UnterminatedString loc ->
      print_loc ppf loc;
      fprintf ppf "Unterminated string";
  | InvalidDirective (loc, s) ->
      print_loc ppf loc;
      fprintf ppf "Invalid toplevel directive '%s'" s;
;;

let report_parsing_error ppf = function
  | ParseError (reason, loc) ->
      print_loc ppf loc;
      fprintf ppf "%s" reason
  | Unclosed ((opening, opening_loc), decl, (closing, closing_loc)) ->
      if String.length !Highlight.input_name = 0
      && Highlight.highlight_locations opening_loc ~loc2:closing_loc ppf
      then fprintf ppf "Syntax error: '%s' expected (while parsing %s), \
                   the highlighted '%s' might be unmatched" closing decl opening
      else begin
        fprintf ppf "%aSyntax error: '%s' expected@."
          print_loc closing_loc closing;
        fprintf ppf "%aThis '%s' might be unmatched"
          print_loc opening_loc opening;
      end

