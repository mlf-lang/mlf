(** Syntactic representation of types and expressions *)

open GType
open Locations

(* type input = File of string | String of string *)
(* type location = { input : input; left : int; right : int; } *)

(* type type_var = string *)
(* type expr_var = string *)
(* (\* type 'a loc = { loc : location; exp : 'a } *\) *)

(* type 'a loc = 'a Locations.loc  *)

(* type type_expr = *)
(*   | All of type_var * bool * type_expr * type_expr *)
(*   | Arrow of type_expr * type_expr *)
(*   | Bot  *)
(*   | Type_var of type_var *)

(* type expr = *)
(*   | Var of expr_var  *)
(*   | Fun of expr_var * annot loc option * exp *)
(*   | App of exp * exp *)
(*   | Let of expr_var * exp  * exp *)
(*   | Annot of annot loc *)
(* and exp = expr loc *)
(* and annot = type_var list * type_exp *)
(* and type_exp = type_expr loc *)


module G =
  Map.Make
    (struct
      type t = gtype
      let compare t1 t2 =
        assert (gen_node t1 && gen_node t2);
        GType.compare t1 t2
    end);;

type graphic_constraint = {
  nodes : gtype list;
  root : gtype;
  type_to_expr : GAst.expr Locations.loc G.t;
}
