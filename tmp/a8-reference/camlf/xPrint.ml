(* Printer implementation :

   To handle a correct (but sparse) placement of parenthesis, we rely
   on nesting levels.  Care must be taken to ensure coherence between
   level for different AST (types, expressions..), because in some
   printing situations, we use types inside expressions.

   Subtlety : printers use two printer functions for subterms :
   print_foo and print_foo'.  The print_foo' version is the
   level-aware version : it will insert parenthesis if needed.  The
   print_foo version never protect an inner subterm. It is still used
   form subterms appearing at positions that do not need
   protection. For example, the TBound printer is "∀(%s>=%s) %s". The
   last %s needs level-aware printing, but not the two first, wich are
   already enclosed by parenthesis.
*)

open XAst

module P = struct
  include Pprint
  let cat = (^^)
  let string =
    fancy (fun s -> String.fold_left (fun n c -> if Char.code c land 0xc0 = 0x80 then n else n + 1) 0 s)
  let join li = List.fold_right cat li empty
  let indent_len = ref 2
  let nesti = nest !indent_len
  let seqi = seq !indent_len
  let groupi doc = group (nesti doc)
  let thinspace = ifflat empty space
  module Operators2 = struct
    let (!^) = Operators.(!^)
    let (^^) = Operators.(^^)
    let (^^^) x y = x ^^ space ^^ y
    let (^-^) x y = x ^^ nesti (break0 ^^ y)
    let (^--^) x y = group (x ^^ nesti (break1 ^^ y))
  end
end
open P.Operators2


module S = Symbol
let sym s = P.string (s ())

(* Printing environment : assign names (free variables) to De Bruijn
   Indices *)
type env = (XEnv.TVar.free_var, XEnv.EVar.free_var) XEnv.t

let level_symbol = 0
let level_application = 1
let level_unary = 2
let level_sequence = 3
let level_arrow = 4

let make_printer curr_level level print env term =
  let result = print env term in
  if level term <= curr_level then result
  else P.group (P.parens result)

let make_homo_printer curr_term level =
  make_printer (level curr_term) level

let level_typ = function
  | TBot | TVar _ | TConst _ -> level_symbol
  | TBound (_, _, _) -> level_unary
  | TArrow (_, _) -> level_arrow

(* Print environments assign names to bind variables : we consider
   those names "free" in the environment *)
let print_free_evars env  =
  XEnv.free_evars env @ XEnv.BE.fold (fun _  v li -> v :: li) env.XEnv.be []
let print_free_tvars env =
  XEnv.free_tvars env @ XEnv.BT.fold (fun _  v li -> v :: li) env.XEnv.bt []

let generic_print_var finder printer env var =
  let name = match var with
    | `F x -> x
    | `B x -> finder x env in
  printer name

let print_free_var x = P.string (x : XEnv.EVar.free_var :> string)
let print_free_tvar alpha = P.string (alpha : XEnv.TVar.free_var :> string)

let print_var env = generic_print_var XEnv.BE.find print_free_var env.XEnv.be
let print_tvar env = generic_print_var XEnv.BT.find print_free_tvar env.XEnv.bt

let print_quant quant alpha op bound =
  P.groupi (quant ^^ P.parens
              (P.group
                 ((alpha ^^ P.thinspace ^^ op)
                  ^^ P.break0 ^^ P.nesti bound)))
let print_forall alpha sigma =
  print_quant (sym S.forall) alpha (sym S.geq) sigma

let print_builtin : builtin -> _ = function
  | `Unit -> P.string "#()"
  | `Int n -> P.string (string_of_int n)
  | `Bool b -> P.string (if b then "#True" else "#False")
  | `If -> P.string "#if"
  | `EqInt -> P.string "#="
  | `Fix -> P.string "#fix"
  | `Arith_op op ->
      P.string
        (match op with
        | `Plus -> "#+"
        | `Minus -> "#-")

let print_tconst = function
  | `Int -> P.string "#int"
  | `Unit -> P.string "#unit"
  | `Bool -> P.string "#bool"

let rec print_typ env (typ : typ) =
  let print_typ' =
    make_homo_printer typ level_typ print_typ in
  match typ with
  | TConst t -> print_tconst t
  | TVar t -> print_tvar env t
  | TArrow (sigma, tau) ->
      P.infix (S.arrow ())
	(* arrow is right associative : decrease the level on the left *)
	(make_printer (level_arrow - 1) level_typ print_typ env sigma)
	(print_typ' env tau)
  | TBound (alpha, sigma, tau) ->
      (* when encountering a binder :
	 - generate a fresh name for the bound variable
	 - bind the variable to the name in the printing environment *)
      let alpha' = XEnv.TVar.fresh_var (print_free_tvars env) in
      let env' = XEnv.add_tvar alpha alpha' env in
      print_forall (print_free_tvar alpha') (print_typ env sigma)
      ^--^ print_typ' env' tau
  | TBot -> sym S.bot

let level_tycomp = function
  | Refl | Elim | Intro | Hyp _ -> level_symbol
  | Bot _ | Inner _ | Outer (_, _) -> level_unary
  | Trans (_, _) -> level_sequence

let rec print_tycomp env (tycomp : tycomp) =
  let print_tycomp' =
    make_homo_printer tycomp level_tycomp print_tycomp in
  match tycomp with
  | Trans(Inner(Bot sigma), Elim) -> print_typ env sigma
    (* special case for the derived "type application" computation *)
  | Refl -> sym S.epsilon
  | Bot sigma -> sym S.tycomp_bot ^^ print_typ env sigma
  | Hyp alpha -> print_tvar env alpha ^^ sym S.tycomp_hyp
  | Inner phi -> print_forall P.empty (print_tycomp' env phi)
  | Outer (alpha, phi) ->
      let alpha' = XEnv.TVar.fresh_var (print_free_tvars env) in
      let env' = XEnv.add_tvar alpha alpha' env in
      print_forall (print_free_tvar alpha') P.empty ^--^ print_tycomp env' phi
  | Elim -> sym S.elim
  | Intro -> sym S.intro
  | Trans (phi, khi) ->
      P.group (P.infix_com ";" (print_tycomp' env phi) (print_tycomp' env khi))

let level__exp : 'a _exp -> int = function
  | `Var _ -> level_symbol
  | `TyComp (_, _) -> level_symbol
  | `App (_, _) | `Builtin _ -> level_application
  | `Lam (_, _, _) | `TyAbs (_, _, _) | `Let (_, _, _) -> level_unary

let print__exp level_exp print_exp env (exp : _ _exp) =
  let print_exp' =
    make_printer (level__exp exp) level_exp print_exp in
  match exp with
  | `Var x -> print_var env x
  | `Builtin (b, ty) -> print_builtin b ^^ P.braces (print_typ env ty)
  | `Lam (x, sigma, a) ->
      let x' = XEnv.EVar.fresh_var (print_free_evars env) in
      let env' = XEnv.add_evar x x' env in
      print_quant
        (sym S.lambda) (print_free_var x') P.colon (print_typ env sigma)
      ^--^ print_exp' env' a
  | `App (a1, a2) -> print_exp' env a1 ^--^ print_exp' env a2
  | `TyAbs (alpha, sigma, a) ->
      let alpha' = XEnv.TVar.fresh_var (print_free_tvars env) in
      let env' = XEnv.add_tvar alpha alpha' env in
      print_quant (sym S._Lambda)
        (print_free_tvar alpha') (sym S.geq) (print_typ env sigma)
      ^--^ (print_exp' env' a)
  | `TyComp (a, phi) ->
      P.group (print_exp' env a ^^ P.break0 ^^ P.brackets (P.groupi (print_tycomp env phi)))
  | `Let (x, a, a') ->
      let x' = XEnv.EVar.fresh_var (print_free_evars env) in
      let env' = XEnv.add_evar x x' env in
      P.group ((!^"let" ^^^ print_free_var x'
                ^^^ sym S.eq ^-^ print_exp env a ^^^ !^"in")
               ^^ P.break1 ^^ print_exp' env' a')

let rec print_exp env (exp : exp) = print__exp level__exp print_exp env exp
let print_typexp env (typexp : typexp) = print__exp level_typ print_typ env typexp

(** Conversion from any environment to a printing environment : create
    fresh free variables to give name to bound variables, and forget
    expression variable contextes.

    Assuming fresh_var is deterministic, it should always produce the
    same names for the same environment, and names shouldn't change
    when you extend the environment *)
open XEnv

let printing_env (env : ('a, 'b) XEnv.t) : env =
  let rebuild fresh_var add =
    let fold_fun binder _ (value_env, used_vars) =
      let name = fresh_var used_vars in
      (add binder name value_env, name :: used_vars) in
    fold_fun in
  { ft = FT.mapi (fun alpha _ -> alpha) env.ft;
    fe = FE.mapi (fun x _ -> x) env.fe;
    bt = fst (BT.fold (rebuild TVar.fresh_var BT.add) env.bt (BT.empty, []));
    be = fst (BE.fold (rebuild EVar.fresh_var BE.add) env.be (BE.empty, []));
    be_contextes = BE.empty }

let print_env env =
  let print_list li =
    P.seqi P.empty P.empty P.empty (P.comma ^^ P.break1) P.empty li in
  let assoc connector key value = P.group (key ^^ connector ^^ value) in
  let get_fenv connector fold kprint vprint subenv =
    let print k v = assoc connector (kprint k) (vprint XEnv.empty v) in
    List.rev (fold (fun k v li -> print k v :: li) subenv []) in
  let printed_env = printing_env env in
  let get_benv connector map print print_name fold printable_benv =    
    let print_value printable_context value =
      print (map snd printable_context) value in
    let rev_fold_fun _ (value, name) context li =
      assoc connector (print_name name) (print_value context value) :: li in
    List.rev (fold rev_fold_fun printable_benv []) in    
  let print_bt context = print_typ {printed_env with bt = context} in
  let print_be context = print_typ {printed_env with be = context} in
  let mix _ value name = (value, name) in
  let geq, col = sym S.geq, P.colon in
  ignore (mix, print_be, print_bt, get_benv, printed_env);
  print_list
    (get_fenv geq FT.fold print_free_tvar print_typ env.ft
     @ get_fenv col FE.fold print_free_var print_typ env.fe
     @ get_benv geq BT.map print_bt print_free_tvar BT.contextual_fold
               (BT.zip mix env.bt printed_env.bt)
     @ get_benv col BE.map print_be print_free_var BE.contextual_fold
               (BE.zip mix env.be printed_env.be))

let sequent env subject prop =
  (env ^^^ sym S.turnstile) ^--^
    ((subject ^^^ P.colon) ^--^ prop)

let nonsequent env subject =
  (env ^^^ sym S.negated_turnstile ^--^ subject)

(** High-level printers *)
let doc ?(compact=false) ?(len=80) ?(offset=0) document =
  let buf = Buffer.create 100 in
  (if compact then P.Buffer.compact else P.Buffer.pretty 1. len)
    buf (P.indent offset document);
  Buffer.contents buf

let env e = print_env e
let typ env typ = print_typ (printing_env env) typ
let tycomp env tycomp = print_tycomp (printing_env env) tycomp
let typexp env typexp = print_typexp (printing_env env) typexp
let exp env exp = print_exp (printing_env env) exp

let type_sequent env exp typ =
  let penv = printing_env env in
  sequent (print_env env) (print_exp penv exp) (print_typ penv typ)

let type_nonsequent env error =
  let penv = printing_env env in
  nonsequent (print_env env) (print_typexp penv error)

let tycomp_sequent env phi sigma sigma' =
  let penv = printing_env env in
  sequent (print_env env) (print_tycomp penv phi)
    (print_typ penv sigma ^^^ sym S.leq ^^^ print_typ penv sigma')

let tycomp_nonsequent env phi sigma =
  let penv = printing_env env in
  nonsequent (print_env env)
    ((print_tycomp penv phi ^^^ P.colon) ^--^
       (print_typ penv sigma ^^^ sym S.leq ^^^ P.string "..."))



(** Caml code printers *)
module ML = struct
  let tbind _alpha = P.string "XEnv.TVar.bind"
  let ebind _x = P.string "XEnv.EVar.bind"

  let var mod_name get_var var =
    let f name = P.string ("XEnv." ^ mod_name ^ "." ^ name ^ " ") in
    match var with
    | `F _ ->
        P.string "`F " ^^ P.parens (f "fvar" ^^ get_var var)
    | `B _ ->
        P.string "`B " ^^ P.parens (f "var" ^^ get_var var)

  let tvar : XEnv.TVar.var -> _ = var "TVar"
    (function
       | `F v -> Pprint.ML.string (v : XEnv.TVar.free_var :> string)
       | `B v -> Pprint.ML.int (v : XEnv.TVar.bound_var :> int))
  let evar : XEnv.EVar.var -> _ = var "EVar"
    (function
       | `F v -> Pprint.ML.string (v : XEnv.EVar.free_var :> string)
       | `B v -> Pprint.ML.int (v : XEnv.EVar.bound_var :> int))

   let tconst = function
     | `Int -> P.string "`Int"
     | `Unit -> P.string "`Unit"
     | `Bool -> P.string "`Bool"

  let builtin = function
    | `Unit -> P.ML.string "`Unit"
    | `Int i -> P.ML.string "`Int" ^^ P.parens (P.ML.int i)
    | `Bool b -> P.ML.string "`Bool" ^^ P.parens (P.ML.bool b)
    | `EqInt -> P.ML.string "`EqInt"
    | `Fix -> P.ML.string "`Fix"
    | `If -> P.ML.string "`If"
    | `Arith_op op ->
        P.ML.string "`Arith_op"
        ^^ P.ML.string
             (match op with
             | `Minus -> "`Minus"
             | `Plus -> "`Plus")

  let rec typ =
    let constr name = P.ML.variant "typ" ("XAst." ^ name) 0 in
    function
      | TVar alpha -> constr "TVar" [tvar alpha]
      | TConst t -> constr "TConst" [tconst t]
      | TArrow (sigma, tau) -> constr "TArrow" [typ sigma; typ tau]
      | TBound (alpha, sigma, tau) ->
          constr "TBound" [tbind alpha; typ sigma; typ tau]
      | TBot -> constr "TBot" []

  let rec tycomp =
    let constr name = P.ML.variant "tycomp" ("XAst." ^ name) 0 in
    function
      | Refl -> constr "Refl" []
      | Bot sigma -> constr "Bot" [typ sigma]
      | Hyp alpha -> constr "Hyp" [tvar alpha]
      | Inner phi -> constr "Inner" [tycomp phi]
      | Outer (alpha, phi) -> constr "Outer" [tbind alpha; tycomp phi]
      | Elim -> constr "Elim" []
      | Intro -> constr "Intro" []
      | Trans (phi, khi) -> constr "Trans" [tycomp phi; tycomp khi]

  let rec exp =
    let constr name = P.ML.variant "exp" name 0 in
    function
      | `Var x -> constr "`Var" [evar x]
      | `Builtin (b, ty) -> constr "`Builtin" [builtin b; typ ty]
      | `Lam (x, sigma, a) -> constr "`Lam" [ebind x; typ sigma; exp a]
      | `App (a, b) -> constr "`App" [exp a; exp b]
      | `TyAbs (alpha, sigma, a) -> constr "`TyAbs" [tbind alpha; typ sigma; exp a]
      | `TyComp (a, phi) -> constr "`TyComp" [exp a; tycomp phi]
      | `Let (x, a, b) -> constr "`Let" [ebind x; exp a; exp b]

  let typ (t : typ) =
    P.group (P.parens (P.infix ":" (typ t) (P.string "XAst.typ")))
  let tycomp (t : tycomp) =
    P.group (P.parens (P.infix ":" (tycomp t) (P.string "XAst.tycomp")))
  let exp (t : exp) =
    P.group (P.parens (P.infix ":" (exp t) (P.string "XAst.exp")))
end
