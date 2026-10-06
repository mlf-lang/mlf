open Locations

(** "Meanings" are used to get decent error reports. The idea, which
    comes from Boris Yakobowksi's prototype, is to annotate all
    constraints in the graph with a "meaning", which is an
    explanation, in terms of the original source term, of what
    justifies this constraint. When a constraint fail, we use its
    recorded meaning to report the error.

    All instance arrows are annotated with "meaning". However, not all
    instances arrows are equal. In particular, due to the specifics of
    the constraint resolution order, some of these instance arrows
    should never raise an unification error. For example, the Abs
    instance, produced when translating a λ-abstraction, has now
    possibility of error when the constraints are resolved bottom-up :
    it always act on a (⊥) node.

    I'm not absolutely sure which constraints will result in
    errors. AppArg, AppCoerceApp and TyAppArg will be involved in
    errors. Abs, TyAbs and SomeIn should not. In the other cases, such
    as AppFun, it's not clear if there should never be an error in any
    circumstances, or if a non-semantic-impacting change to the
    resolution order may turn them into failure points.
*)

type constraint_meaning =
  (* a let-bound var *)
  | VarLet of var_locs

  (* a global var *)
  | VarVal of location

  (* a global type variable *)
  | VarTy of location

  (* abstraction: constraint on the return type *)
  | Abs of location

  (* application: function and argument constraints *)
  | AppFun of location
  | AppArg of location

  (* special case of application of a coercion *)
  | AppCoerceArg of location
  | AppCoerceFun of location

  (* type abstraction *)
  | TyAbs of location

  (* type application : function and argument constraints *)
  | TyAppFun of location
  | TyAppArg of location

  (* some .. in constraint on the return type *)
  | SomeIn of location

  (* body of a let *)
  | LetBody of location


and var_locs = {
  var_binding_loc : location;
  var_loc : location;
}

(* handle the AppCoerce special case *)
let app_arg (a1 : GAst.expr loc) a2 = match a1.obj with
  | `CoerceCt _ -> AppCoerceArg a2.loc
  | _ -> AppArg a2.loc
let app_fun (a1 : GAst.expr loc) _a2 = match a1.obj with
  | `CoerceCt _ -> AppCoerceFun a1.loc
  | _ -> AppFun a1.loc

open Highlight
open Format

let print_meaning ppf error =
  begin match error with
  | VarLet locs ->
    print_loc ppf locs.var_binding_loc;
    print_loc ppf locs.var_loc;
    fprintf ppf "When trying to type occurence of variable"
      
  | VarVal loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type occurence of global variable"

  | VarTy loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type occurence of global type variable"

  | Abs loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type a function"

  | TyAbs loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type a type abstraction"

  | AppFun loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type the function side of an application"

  | AppArg loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type the argument side of an application"

  | AppCoerceArg loc ->
    print_loc ppf loc;
    fprintf ppf "When typing the argument of a coercion";

  | AppCoerceFun loc ->
    print_loc ppf loc;
    fprintf ppf "When typing the coercion function";

  | TyAppFun loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type the abstraction side of a type application"

  | TyAppArg loc ->
    print_loc ppf loc;
    fprintf ppf "When trying to type the type side of a type application"

  | SomeIn loc ->
    print_loc ppf loc;
    fprintf ppf "When typing the expression after some .. in"

  | LetBody loc ->
    print_loc ppf loc;
    fprintf ppf "When typing the body of a let declaration"

  end;
  fprintf ppf "\n%!"
