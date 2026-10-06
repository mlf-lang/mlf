open ETypeConstructors
open EType
open UnknownconstrTypes
open EPrint
open Locations
open Format


type value = [`Value] Opaque.string_t
let s_value s : value = Opaque.string_t s
let value_s (t : value) = Opaque.t_string t

module ValueMap = Opaque.MapS (struct type t = [`Value]  end);;


(* This module defines the abstract syntax tree for the language
   of values and of toplevel expressions *)


(* Built-in constants corresponding to builtin constructions *)
type builtin_ct =
  | OpSeqNonUnit (* Sequence, type not constrained to unit *)
  | OpSeqUnit    (* Sequence, type     constrained to unit *)
  | OpIfThenElse (* If, then, else *)
  | OpIfThen     (* If, then, no else *)
  | OpFix (* Fixpoint operator *)
  | OpEq  (* Polymorphic equality *)
  | OpPlus (* plus on integers *)
  | OpMinus (* minus on integers *)

let print_builtin_ct ppf c = fprintf ppf "%s"
  (match c with
     | OpSeqNonUnit -> "#;"
     | OpSeqUnit -> "#();"
     | OpIfThenElse -> "#IfTE"
     | OpIfThen -> "#IfT"
     | OpFix -> "#fix"
     | OpEq -> "#eq"
     | OpPlus -> "#+"
     | OpMinus -> "#-")

(* Coercion : unified/existential variables, then the standard
  polymorphic/universal prefix and monotype *)
type quant_prefix = type_abstraction loc list
type bound_prefix = bound_abstraction loc list
type coercion = bound_prefix * expanded_polytype loc

(* Patterns for variables bindings *)
type pattern =
  | PatVar of value
  | PatCoerce of pattern loc * coercion loc
(*
  | PUple of 'a pattern list * loc
  | PCons of string * 'a pattern * loc
  | PCtCons of string * loc *)

(* Simple form of patterns for functions *)
type unconstrained_let_name = [ `Unconstrained of value loc ]
type constrained_let_name = [
  | `Constrained of (value loc * coercion loc) loc
  | unconstrained_let_name
]

(* Annotations for recursive function *)
type nonrecursive = [ `NonRec ]
type rec_flag = [ nonrecursive | `Rec ]


(* The languages of values is split into the values that can only
   appear in the source language and the values that can only appear
   in the core language which is the basis for the constraint
   generator (plus a common part)
*)

(* Common values *)
type type_var = ETypeConstructors.typevar
type type_expr = expanded_polytype
type type_abstraction = type_expr type_abstraction_
type bound_abstraction = type_expr bound_abstraction_

type 'a minimal_expr_ = [
  | `App of 'c * 'c
  | `Abs of value loc * 'c
  | `TyApp of 'c * type_expr loc
  | `CoerceCt of coercion loc
  | `SomeTy of bound_prefix * 'c
] constraint 'c = 'a loc

type 'a common_expr_ = [
  | 'a minimal_expr_
  | `Value of value
  | `Constr of constr_name
  | `Uple of 'c list
  | `Ct of value * constant_monotype
] constraint 'c = 'a loc


let ct_of_unit () =
  `Ct (s_value "()", `Constr (`Unit, []))
let unit_of_ct = function
  | `Ct (v, `Constr (`Unit, [])) ->
      assert (value_s v = "()");
      ()
  | _ -> invalid_arg "unit_of_ct"
        

let ct_of_int i =
  `Ct (s_value (string_of_int i), `Constr (`Int, []))
let int_of_ct = function
  | `Ct (v, `Constr (`Int, [])) ->
      begin
        try int_of_string (value_s v)
        with _ -> assert false
      end
  | _ -> invalid_arg "int_of_ct"

let ct_of_bool b =
  `Ct (s_value (if b then "True" else "False"), `Constr (`Bool, []))
let bool_of_ct = function
  | `Ct (v, `Constr (`Bool, [])) ->
      begin
        match value_s v with
        | "True" -> true
        | "False" -> false
        | _ -> assert false
      end
  | _ -> invalid_arg "bool_of_ct"

let equal_ct (v1, t1) (v2, t2) =
  v1 = v2 && t1 = t2

(* source only expressions *)
type 'a source_expr_ = [
  | 'a common_expr_
  | `Coerce of 'c * coercion loc
  | `SeqApp of 'c * 'c list
  | `SeqAbs of pattern loc list * 'c
  | `SeqTyAbs of quant_prefix * 'c
  | `IfThenElse of 'c * 'c * 'c
  | `IfThen of 'c * 'c
  | `Equal of 'c * 'c
  | `Plus of 'c * 'c
  | `Minus of 'c * 'c
  | `Seq of 'c list * 'c
] constraint 'c = 'a loc
type 'a source_let = [
  `Let of rec_flag * (constrained_let_name  * 'a loc) * 'a loc
]

(* typing only expressions *)
type 'a desugared_expr_ = [
  | `BuiltinCt of builtin_ct
  | `TyAbs of type_abstraction loc * 'c
] constraint 'c = 'a loc

type 'a typing_let_ = [
  `Let of nonrecursive * (unconstrained_let_name * 'c) * 'c
] constraint 'c = 'a loc

type 'a typing_expr_ = [
  | 'a common_expr_
  | 'a desugared_expr_
  | 'a typing_let_
]

type typing_expr = typing_expr typing_expr_

type source_expr = [
  | source_expr source_expr_
  | source_expr source_let
]

(* The set of all values. Used only by the pretty-printer *)
type expr = [
  | expr source_expr_
  | expr desugared_expr_
  | expr source_let
]


let builtin v = Locations.noloc (`BuiltinCt v)
let var_pat v = { v with obj = PatVar v.obj }

let let_dest v e1 e2 : typing_expr =
  `Let (`NonRec, (`Unconstrained v, e1), e2)

let rec desugar : source_expr loc -> typing_expr loc = fun e_loc ->
  let e' = match e_loc.obj with
    (* Unchanged *)
    | `Value _ | `Constr _ | `CoerceCt _ | `Ct _ as v -> v

    (* Recursively desugared *)
    | `App (e1, e2) -> `App (desugar e1, desugar e2)
    | `Abs (v, e) -> `Abs (v, desugar e)
    | `Uple l -> `Uple (List.map desugar l)
    | `TyApp (e, sigma) -> `TyApp (desugar e, sigma)
    | `SomeTy (quants, e) -> `SomeTy (quants, desugar e)

    (* Translated to the application of a builtin constant *)
    | `Equal (e1, e2) -> (desugar_seq_app (builtin OpEq) [e1;e2]).obj
    | `Plus (e1, e2) -> (desugar_seq_app (builtin OpPlus) [e1;e2]).obj
    | `Minus (e1, e2) -> (desugar_seq_app (builtin OpMinus) [e1;e2]).obj
    | `IfThenElse (c, e1, e2) ->
        (desugar_seq_app (builtin OpIfThenElse) [c;e1;e2]).obj
    | `IfThen (c, e) ->
        (desugar_seq_app (builtin OpIfThen) [c;e]).obj

    (* Specific translation *)
    | `SeqTyAbs (l, e) -> (desugar_seq_tyabs l (desugar e)).obj
    | `SeqAbs (l, e) -> (desugar_seq_abs l (desugar e)).obj
    | `Coerce (p, t) -> desugar_coerce p t
    | `SeqApp (e, l) -> (desugar_seq_app (desugar e) l).obj
    | `Seq (l, r) -> (desugar_seq r l).obj

    (* Let *)
    | `Let (`NonRec, (`Unconstrained v, e1), e2) ->
        let_dest v (desugar e1) (desugar e2)

    (* let (v : t) = e in e'  --> let v = (e : t) in e ' *)
    | `Let (`NonRec, (`Constrained {obj = v, t}, e1), e2) ->
        let_dest v
          {e1 with obj = desugar_coerce { e1 with loc = v.loc } t}
          (desugar e2)

    (* let rec v = e in e'  --> let v = fix (fun v -> e) in e' *)
    | `Let (`Rec, (`Unconstrained v, e1), e2) ->
        let l = join v.loc e1.loc in
        let p = var_pat v in
        let_dest v {obj = desugar_fix p e1; loc = l} (desugar e2)

    (* let rec (v : t) = e in e' -->
         let v = fix (fun (v : t) -> e) in e' *)
    | `Let (`Rec, (`Constrained {obj = v, t; loc = locp}, e1), e2) ->
        let l = join locp e1.loc in
        let p = {obj = PatCoerce (var_pat v, t); loc = locp} in
        let_dest v {obj = desugar_fix p e1; loc = l} (desugar e2)
  in
  (* Desugaring is not supposed to change the locations. We
     restore a few locations, as some auxiliary functions can
     eat some parentheses or introduce ghost expressions *)
  { e_loc with obj = e' }

and desugar_fix p e =
  `App (builtin OpFix, desugar_seq_abs [p] (desugar e))

and desugar_coerce e t : typing_expr =
  `App ({ t with obj = `CoerceCt t }, desugar e)

and desugar_pattern (pat : pattern loc) r =
  match pat.obj with
    | PatVar v -> { obj = v; loc = pat.loc }, r
    | PatCoerce (p, t) ->
        let (v, r) = desugar_pattern p r in
        v, { obj = let_dest v
            { pat with obj = desugar_coerce { v with obj = `Value v.obj } t} r;
             loc = join pat.loc pat.loc (* TODO *) }

and desugar_seq_abs l r =
  let rec aux r = function
    | [] -> r
    | p :: q ->
        let v, t = desugar_pattern p r in
        let r = { obj = `Abs (v, t) ; loc = join p.loc r.loc } in
        aux r q
  in aux r (List.rev l)

and desugar_seq_tyabs tvars body : typing_expr loc =
  List.fold_right
    (fun tyabs body ->
       { obj = `TyAbs(tyabs, body)
       ; loc = join tyabs.loc body.loc })
    tvars body

and desugar_seq_app e l = desugar_seq_app_typing e (List.map desugar l)

and desugar_seq_app_typing e = function
  | [] -> e
  | e' :: q -> desugar_seq_app_typing { obj = `App (e, e');
                                        loc = join e.loc e'.loc } q

and desugar_seq r = function
  | [] -> desugar r
  | e :: q ->
      let seq = if !Options.sequence_has_type_unit
      then OpSeqUnit else OpSeqNonUnit in
      { (desugar_seq_app_typing (builtin seq) [desugar e; desugar_seq r q])
        with loc = join e.loc r.loc }

(* forget locations ; used in specifications :
   noloc . parse. print = noloc *)
let noloc e = { e with loc = dummy_loc }
let noloc_with e f = noloc {e with obj = f e.obj}

let rec noloc_expr : source_expr loc -> source_expr loc = fun e ->
  noloc_with e
    (function
       | `Value _ | `Constr _ | `CoerceCt _ | `Ct _ as v -> v
       | `App (e1, e2) -> `App (noloc_expr e1, noloc_expr e2)
       | `Abs (v, e) -> `Abs (v, noloc_expr e)
       | `Uple l -> `Uple (List.map noloc_expr l)
       | `TyApp (e, sigma) -> `TyApp (noloc_expr e, noloc sigma)
       | `SomeTy (q, e) -> `SomeTy (List.map noloc q, noloc_expr e)
       | `Equal (e1, e2) -> `Equal (noloc_expr e1, noloc_expr e2)
       | `Plus (e1, e2) -> `Plus (noloc_expr e1, noloc_expr e2)
       | `Minus (e1, e2) -> `Minus (noloc_expr e1, noloc_expr e2)
       | `IfThenElse (c, e1, e2) ->
           `IfThenElse (noloc_expr c, noloc_expr e1, noloc_expr e2)
       | `IfThen (c, e) -> `IfThen (noloc_expr c, noloc_expr e)
       | `SeqAbs (l, e) -> `SeqAbs (List.map noloc_patt l, noloc_expr e)
       | `SeqTyAbs (l, e) -> `SeqTyAbs (List.map noloc l, noloc_expr e)
       | `Coerce (p, t) -> `Coerce (noloc_expr p, noloc t)
       | `SeqApp (e, l) -> `SeqApp (noloc_expr e, List.map noloc_expr l)
       | `Seq (l, r) -> `Seq (List.map noloc_expr l, noloc_expr r)
       | `Let (rec_flag, (let_name, e1), e2) ->
           `Let (rec_flag, (noloc_let_name let_name, noloc_expr e1), noloc_expr e2)
    )
and noloc_patt : pattern loc -> pattern loc = fun p ->
  noloc_with p
    (function
       | PatVar v -> PatVar v
       | PatCoerce (p, t) -> PatCoerce (noloc_patt p, noloc t))
and noloc_let_name =
  function
    | `Constrained constr ->
        `Constrained (noloc_with constr (fun (s, t) -> (noloc s, noloc t)))
    | `Unconstrained v -> `Unconstrained (noloc v)
;;
(* (Any) expression to string *)
let located printer ppf {obj=v} = printer ppf v

let print_prefix ppf (q : bound_prefix) =
  Utils.print_list (located print_tyabs) " " ppf (q :> quant_prefix)

let print_coercion ppf (c : coercion loc) =
  match c.obj with
  | ([], t) -> located print_type ppf t
  | (inf, t) ->
      fprintf ppf "some %a. %a"
        print_prefix inf
        (located print_type) t

let rec print_pattern ppf p =
  match p.obj with
    | PatVar v -> fprintf ppf "%s" (value_s v)
    | PatCoerce (p, t) -> fprintf ppf
        "(%a : %a)" print_pattern p print_coercion t

let print_list_pattern = Utils.print_list print_pattern " "

let print_list_tyabs ppf li =
  Utils.print_list print_tyabs " " ppf
    (List.map (fun e -> e.obj) li)


module Level : sig
  type level
  val level_ct : level
  val level_app : level
  val level_equal : level
  val level_if : level
  val level_max : level

  val expr_level : expr -> level

  val levels_strictly_greater : level -> level -> bool
  val levels_equal : level -> level -> bool
end = struct
  type level = int

  let level_ct = 0
  let level_tyapp = 4
  let level_app = 5
  let level_equal = 10
  let level_plus_minus = 12
  let level_if = 15
  let level_seq = 20
  let level_max = 25

  let levels_strictly_greater = (>)
  let levels_equal = (=)

  let expr_level : expr -> level = function
    | `Value _ | `Constr _ | `Ct _ | `Uple _ |
          `Coerce _ | `CoerceCt _ | `BuiltinCt _ -> level_ct
    | `TyApp _ -> level_tyapp
    | `App _ | `SeqApp _ -> level_app
    | `Equal _ -> level_equal
    | `Plus _ | `Minus _ -> level_plus_minus
    | `IfThen _ | `IfThenElse _ -> level_if
    | `Seq _ -> level_seq
    | `Let _ | `SomeTy _
    | `Abs _ | `SeqAbs _
    | `TyAbs _ | `SeqTyAbs _ -> level_max
end
open Level


let debug_locations = ref false

let print_expr ppf (e : expr loc) =
  let mini = not !Options.minimize_parentheses in
  (* l is the level starting at which the expression will
     be parenthesize (if level e is strictly greater than l,
     or if level e = l and large is true) *)
  let rec expr ?(large=false) l () ppf e =
    let l' = expr_level e.obj in
    (* Shortcut function, which does the recursive call equal to
       the level of the current expression *)
    let expr ?(large=false) ?(level=l') () ppf e' =
      expr ~large level () ppf e'
    in
    if !debug_locations then fprintf ppf "@\n@[<hov 2>[%d-%d] "
      e.loc.loc_start.Lexing.pos_cnum e.loc.loc_end.Lexing.pos_cnum;
    let paren = levels_strictly_greater l' l || (large && levels_equal l' l) in
    if paren then fprintf ppf "(";
    (match e.obj with
      (* First level *)
      | `Value s | `Ct (s, _) -> fprintf ppf "%s" (value_s s)
      | `Constr c -> fprintf ppf "%s" (constr_s c)
      | `BuiltinCt c -> print_builtin_ct ppf c

      | `Uple l -> fprintf ppf "(%a)"
          (Utils.print_list (expr ~large:false ~level:level_app ()) ", ") l

      | `Coerce (e, t) -> fprintf ppf "(%a : %a)"
          (expr ()) e print_coercion t

      | `CoerceCt t -> fprintf ppf "(: %a)" print_coercion t

      (* Application *)
      | `TyApp (e, sigma) ->
            fprintf ppf "%a[%a]" (expr ()) e (located print_type) sigma
      | `App (e1, e2) -> fprintf ppf "%a %a"
            (expr ~large:mini ()) e1 (expr ~large:true ()) e2
      | `SeqApp (e, l) -> fprintf ppf "%a %a"
            (expr ~large:mini ()) e
            (Utils.print_list (expr ~large:true ()) " ") l

      (* Operators *)
      | `Equal (e1, e2) ->
          fprintf ppf "%a = %a"
            (expr ~large:true ()) e1 (expr ~large:true ()) e2

      | `Plus (e1, e2) ->
          fprintf ppf "%a + %a"
            (expr ~large:false ()) e1 (expr ~large:false ()) e2
      | `Minus (e1, e2) ->
          fprintf ppf "%a - %a"
            (expr ~large:false ()) e1 (expr ~large:true ()) e2


      (* Conditionals *)
      | `IfThenElse (c, e1, e2) ->
          fprintf ppf "if %a then %a else %a"
            (expr ~large:mini ()) c
            (expr ~large:true ()) e1 (expr ~large:true ()) e2
      | `IfThen (c, e) ->
          fprintf ppf "if %a then %a"
            (expr ~large:mini ()) c (expr ~large:true ()) e

      (* sequence of expressions *)
      | `Seq (l, r) ->
          fprintf ppf "%a; %a"
            (Utils.print_list (expr ~large:true ()) "; ") l
            (expr ~large:mini ()) r

      (* Delimited high-level constructions *)
      | `Let (frec, (p, e1), e2) ->
          let v, t = match p with
            | `Constrained {obj = v, t} -> v, Some t
            | `Unconstrained v -> v, None
          in
          let_to_string ppf frec v t e1 e2

      | `SomeTy (q, e) -> fprintf ppf "some %a in %a"
          print_prefix q (expr ()) e

      | `Abs (v, e) -> fprintf ppf "fun %s -> %a"
            (value_s v.obj) (expr ()) e
      | `SeqAbs (l, e) -> fprintf ppf "fun %a -> %a"
            print_list_pattern l (expr ()) e

      | `TyAbs (tyabs, e) -> fprintf ppf "Fun %a -> %a"
            print_tyabs tyabs.obj (expr ()) e
      | `SeqTyAbs (seq_tyabs, e) -> fprintf ppf "Fun %a -> %a"
            print_list_tyabs seq_tyabs (expr ()) e


    );
    if paren then fprintf ppf ")";
    if !debug_locations then fprintf ppf "@]";


  and let_to_string ppf isrec v t e1 e2 =
      let r = if isrec = `Rec then " rec" else ""
      and v ppf t = match t with
        | None -> fprintf ppf "%s" (value_s v.obj)
        | Some t -> fprintf ppf "(%s : %a)"
            (value_s v.obj) print_coercion t
      in
      match e1.obj with
        | `SeqAbs (l, e1) ->
            fprintf ppf "let%s %a %a = %a in %a"
              r v t print_list_pattern l
              (expr ~large:mini level_max ()) e1 (expr level_max ()) e2
        | _ ->
            fprintf ppf "let%s %a = %a in %a"
              r v t (expr ~large:mini level_max ()) e1 (expr level_max ()) e2
  in
  expr level_max () ppf e;
  Format.pp_print_newline ppf ()


let print_source_expr ppf e =
  print_expr ppf (e : source_expr loc :> expr loc)

let source_expr_to_string = Utils.format_into_string print_source_expr

let print_typing_expr ppf e =
  print_expr ppf (e : typing_expr loc :> expr loc)

let typing_expr_to_string = Utils.format_into_string print_typing_expr


(* ASTs for toplevel definitions *)

type type_decl = typeconstr_name loc * typevar list loc

type inductive_constr_decl = constr_name loc * type_expr loc list

type phrase =
  | Expr of source_expr loc
  | Val of rec_flag * constrained_let_name * source_expr loc
  | Inductive of type_decl * inductive_constr_decl list loc
  | Alias of type_decl * type_expr loc
  | Include of string
  | Global of directive_option
  | Local of directive_option * phrase loc
  | Help of string list
and directive_option = string * bool

let let_name : constrained_let_name -> _  = function
    `Unconstrained v | `Constrained { obj = v, _ } -> v

(* val <rec> <name> = <v>  —→ let <rec> <name> = <v> in <name> *)
let val_to_let r name v : source_expr loc =
  let name' = let_name name in
  { name' with obj =
      `Let (r, (name, v), { name' with obj = `Value name'.obj })}  
