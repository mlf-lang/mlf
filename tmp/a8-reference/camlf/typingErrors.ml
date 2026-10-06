open EType
open ETypeConstructors
open ETypeKinds
open Locations
open Highlight
open Format

type type_expr = AST.type_expr

type typing_error =
  | UnboundVar of (*AST.value*) [`Value|`TypeVar] Opaque.string_t * location
  | UnknownTypeConstructor of typeconstr_name * location
  | UnknownInductiveConstructor of constr_name * location
  | IncorrectArity of typeconstr_name * int * int * location
  | IncorrectKind of wrong_kind * type_expr * location
  | NonDistinctParameters of typevar * location
  | NonDistinctConstructors of constr_name * location
  | UnboundTypeVar of typevar * location
  | MLFCoercionMLConstraint of UnknownconstrTypes.expanded_polytype * location
  | IncorrectSugarAnnotation of typeconstr_name * int * location

and wrong_kind = [
  | `Expect of kind * kind (* expected, real *)
  | `Apply of kind * kind (* function, argument *)
]

exception TypingError of typing_error

exception MLFTypeMLFExpansion

let typing_error e = raise (TypingError e)

let report_typing_error ppf error =
  begin match error with
  | UnboundVar (v, loc) ->
      print_loc ppf loc;
      fprintf ppf "Unbound var '%s'." ((*AST.value_s*) Opaque.t_string v)

  | UnknownTypeConstructor (c, loc) ->
      print_loc ppf loc;
      fprintf ppf "Unbound type constructor '%s'." (typeconstr_s c)

  | UnknownInductiveConstructor (c, loc) ->
      print_loc ppf loc;
      fprintf ppf "Unbound constructor '%s'." (constr_s c)

  | IncorrectArity (c, ac, au, loc) ->
      print_loc ppf loc;
      fprintf ppf "The type constructor %s expects %d argument(s) but is used with %d argument(s)." (typeconstr_s c) ac au

  | IncorrectKind (explanation, etype, loc) ->
      print_loc ppf loc;
      let print_kind = print_kind ~verbatim:true in
      begin match explanation with
      | `Expect (expected, real) ->
          fprintf ppf "The type %a, of kind %a, is used as kind %a."
            EPrint.print_type etype print_kind real print_kind expected
      | `Apply (func, arg) ->
          fprintf ppf "In the type application %a, function kind %a \
                       and argument kind %a are incompatible."
            EPrint.print_type etype print_kind func print_kind arg
      end

  | NonDistinctParameters (v, loc) ->
      print_loc ppf loc;
      fprintf ppf
        "The type variable '%s appears multiple times in this parameters declaration."
        (typevar_s v)

  | UnboundTypeVar (v, loc) ->
      print_loc ppf loc;
      fprintf ppf
        "The type variable '%s is unbound in this type declaration."
        (typevar_s v)

  | NonDistinctConstructors (c, loc) ->
      print_loc ppf loc;
      fprintf ppf
        "The constructor '%s' is defined more than once in this type declaration." (constr_s c)

  | MLFCoercionMLConstraint (_t, loc) ->
      print_loc ppf loc;
      fprintf ppf
        "Only ML type annotations (without universal quantification) are permitted in ML constraints"

  | IncorrectSugarAnnotation (c, arity, loc) ->
      print_loc ppf loc;
      fprintf ppf
        "This sugar annotation is incorrect, the type constructor %s has arity %d" (typeconstr_s c) arity
  end;
  fprintf ppf "\n%!"
