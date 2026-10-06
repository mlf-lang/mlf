open Format

(* (free) type variables *)
type typevar = [`TypeVar] Opaque.string_t
let s_typevar s : typevar = Opaque.string_t s
let typevar_s (c : typevar) = Opaque.t_string c
module TypeVarSet = Opaque.SetS(struct type t = [`TypeVar] end)
module TypeVarMap = Opaque.MapS(struct type t = [`TypeVar] end)

(* Name of type constructors *)
type typeconstr_name = [`TypeConstr] Opaque.string_t
let s_typeconstr s : typeconstr_name = Opaque.string_t s
let typeconstr_s (t : typeconstr_name) = Opaque.t_string t
module TypeConstrMap = Opaque.MapS(struct type t = [`TypeConstr] end)

(* Name of the constructors for inductive types *)
type constr_name = [`Constr] Opaque.string_t
let s_constr s : constr_name = Opaque.string_t s
let constr_s (c : constr_name) = Opaque.t_string c
module ConstrSet = Opaque.SetS(struct type t = [`Constr] end)
module ConstrMap = Opaque.MapS(struct type t = [`Constr] end)

(* constructors kinded arity *)
type kind = ETypeKinds.kind

type 'a constructor = {
  constr_name: constr_name;
  constr_args: 'a list;
}

type user_type_desc = {
  typeconstr_name: typeconstr_name;
  typeconstr_name_id: int;
  typeconstr_arity: int;
  typeconstr_is_poly: bool;
}

let equal_user_typedesc c1 c2 =
  c1.typeconstr_name = c2.typeconstr_name &&
  c1.typeconstr_name_id = c2.typeconstr_name_id

(* If new types are added, do not forget to update find_type_same_name
   in TypingEnv *)
type init_ct_typeconstr = [ `Unit | `Int | `Bool ]
type overridable_typeconstr = [ init_ct_typeconstr | `User of user_type_desc ]
type typeconstr =
  [ `Arrow
  | `Uple of int
  | overridable_typeconstr ]
type unresolved_typeconstr = [ typeconstr | `PConstr of typeconstr_name ]

let typeconstr_is_poly : typeconstr -> bool = function
  | `Arrow | `Uple _ | `Unit | `Int | `Bool -> false
  | `User c -> c.typeconstr_is_poly

(* Used for type constructors resolution *)
let typeconstr_name = function
   | `Unit -> s_typeconstr "unit"
   | `Int -> s_typeconstr "int"
   | `Bool -> s_typeconstr "bool"
   | `Uple _ -> s_typeconstr "*"
   | `User u -> u.typeconstr_name
   | `PConstr s -> s
   | `Arrow -> s_typeconstr "->"
   | `App -> s_typeconstr "@"

let string_of_typeconstr ?remap:(f = fun s -> s)
    (c : unresolved_typeconstr) = 
  match c with
    | `Unit | `Int | `Bool | `Uple _ as t ->
        f (typeconstr_s (typeconstr_name t))
    | `User u ->
        f (if u.typeconstr_name_id = 0 then
             typeconstr_s u.typeconstr_name
           else
             Printf.sprintf "%s.%d"
               (typeconstr_s u.typeconstr_name) u.typeconstr_name_id)
    | `PConstr s -> f (typeconstr_s s)
    | `Arrow -> "->"

let arity : typeconstr -> int = function
  | `Arrow
  | `Unit | `Int | `Bool -> 1
  | `User u -> u.typeconstr_arity
  | `Uple n -> n

