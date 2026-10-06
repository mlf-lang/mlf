open Animate
open Main

let () =
  let phrases = phrases () in
  (* does not allow dependencies at the moment *)
  if !Animate.state_file <> "" then
    let st = Animate.state_from_file !Animate.state_file in
    let st = Animate.restore_state st in
    Animate.show [] st
  else
    let exprs = List.map source_expr_of_phrase phrases in
    match List.rev (Utils.flatten_option exprs) with
    | [] ->
        let env = Examples.examples in
        let str = "fun x y -> x y" in
        let state = Animate.state_of_expr env (EParse.expr str) str in
	Animate.show env state
    | last :: _ ->
	let str = AST.source_expr_to_string last in
	let state = Animate.state_of_expr [] last str in
	Animate.show [] state
