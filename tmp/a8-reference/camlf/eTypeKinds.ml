let fprintf = Printf.fprintf

type kind =
  | Star
  | Arrow of kind * kind

let level_star = 0
let level_arrow = 1

let level = function
  | Star -> level_star
  | Arrow (_, _) -> level_arrow

open Format

(* verbatim boolean must be true when the output need to be parsable
   back with eParser (no UTF8 fancy) *)
let rec print_kind ~verbatim ppf = function
  | Star -> fprintf ppf "%s"
      (if verbatim then "*" else Symbol.star ())
  | Arrow (k, k') ->
      fprintf ppf "%a %s %a"
        (print_kind' level_arrow ~verbatim) k
        (if verbatim then "->" else Symbol.arrow ())
        (print_kind' (level_arrow + 1) ~verbatim) k'
and print_kind' lvl ~verbatim ppf t =
  if level t >= lvl then
    fprintf ppf "(%a)" (print_kind ~verbatim) t
  else
    fprintf ppf "%a" (print_kind ~verbatim) t

let string_of_kind ~verbatim kind =
  Format.flush_str_formatter
    (print_kind ~verbatim (Format.str_formatter) kind)
