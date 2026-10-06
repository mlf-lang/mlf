module S = Kaputt.Specification

type expr = AST.source_expr Locations.loc
let alpha_equiv = GAst.source_alpha_equiv

let alpha_equiv_is_reflexive : (expr, unit) S.t =
  { S.precond = S.always
  ; S.postcond = (fun (a, ()) -> alpha_equiv a a) }

let alpha_equiv_is_symmetric : (expr * expr, unit) S.t =
  { S.precond = (fun (a, b) -> alpha_equiv a b)
  ; S.postcond = (fun ((a, b), ()) -> alpha_equiv b a) }

let alpha_equiv_is_transitive : (expr * expr * expr, unit) S.t =
  { S.precond = (fun (a, b, c) -> alpha_equiv a b && alpha_equiv b c)
  ; S.postcond = (fun ((a, _b, c), ()) -> alpha_equiv a c) }

let print_parse_involution : (expr -> expr) * (expr, expr) S.t =
  let expr_printer = AST.source_expr_to_string in
  let expr_parser = EParse.expr in
  let parse_print t = expr_parser (expr_printer t) in
  parse_print,
  S.implies' S.always (fun t -> expr_printer t = expr_printer (parse_print t))

let parse_print_same : (expr -> expr) * (expr, expr) S.t =
  let parse_print t = EParse.expr (AST.source_expr_to_string t) in
  parse_print,
  S.implies S.always
    (fun (t, t') -> AST.noloc_expr t = AST.noloc_expr t')

