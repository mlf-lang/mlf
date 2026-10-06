%{
  open ETypeConstructors
  open EType
  open UnknownconstrTypes
  open AST
  open Locations
  open SyntaxErrors
  open Printf

  let error r (loc : unit loc) =
    raise (ParsingError (ParseError (r, loc_ loc.loc.loc_start loc.loc.loc_end)))

  let unclosed symb pos1 pos1' decl symb' pos2 pos2' =
    raise (ParsingError (Unclosed
             ((symb, loc_ pos1 pos1'), decl, (symb', loc_ pos2 pos2'))))

  let tvar =
    let c = Utils.counter 0 in
    (fun () -> s_typevar (Printf.sprintf "#%d" (c())))

  let desugar_type_prefix =
    List.fold_right
      (fun abs t -> `Forall (abs, t))

  let desugar_lambda_prefix =
    List.fold_right
      (fun abs t -> `Lambda (abs, t))

  let binding_flags_errormsg =
    EPrint.string_of_binding_flags

  let ct_constructors = function
    | ("True" | "False") as bool ->
        `Ct (s_value bool, `Constr (`Bool, []))
    | _ -> raise Not_found
%}


%token EOF

%token <string> LIDENT UIDENT QUOTELIDENT STRING
%token <int> INT
%token COMMA DOT COLON STAR SEMI SEMISEMI BANG CIRCUMFLEX
%token GREATER EQUAL
%token ARROW FUN FFUN LAMBDA LET IN REC SOME A
%token AROBASE
%token LPAREN RPAREN
%token LBRACKET RBRACKET
%token IF THEN ELSE
%token VAL
%token TYPE OF
%token PIPE
%token PLUS MINUS
%token UNDER 
//%token MATCH WITH

(* Toplevel directives *)
%token INCLUDE
%token LOCAL GLOBAL
%token HELP

%nonassoc THEN       (* Dangling else *)
%nonassoc ELSE       (* cf. THEN   *)

%right    ARROW      (* Associativity in type declaration *)

%nonassoc below_SEMI (* cf. seq_expr_aux *)

%nonassoc SEMI   (* below EQUAL for (fun x -> a ; (b=c)) vs. (fun x -> a ; b)=c
                    above IN for let x = v in (v ; v)  vs. (let x = v in v) ; v
                    above ARROW for fun p -> (v ; v)  vs. (fun p -> v) ; v *)

%left     EQUAL      (* cf. IN *)
%left PLUS MINUS


%start <AST.type_expr Locations.loc> polytype_ monotype_
%start <AST.source_expr Locations.loc> expr_
%start <AST.phrase Locations.loc list> phrases_
%start <AST.phrase Locations.loc> toplevel_phrase
%start <AST.source_expr Locations.loc> int_

%type <AST.source_expr> expr simple_expr
%type <EType.UnknownconstrTypes.expanded_polytype> simple_monotype monotype polytype

%%

%inline separated_list_mintwo(separator, X):
| x = X; separator; l = separated_nonempty_list(separator, X)
    { x :: l }

%inline paren(X):
| LPAREN; x = X; RPAREN
    { x }

%inline list_option(X):
| { [] }
| x = X  { x }

%inline l(X):
x = X { loc x $startpos(x) $endpos(x) }

%inline lerror:
e = l(error) { e }

local_unif_vars:
| SOME vars = l(bound_abstraction)+ IN
    {
      let explicit = function
        | {obj=(_, `Bound ((_, Explicit), _))} -> true
        | _ -> false in
      if List.exists explicit vars then
        error
          "only implicit variables are allowed in \"some .. in\""
          (loc () $startpos(vars) $endpos(vars))
      else vars }
| SOME bound_abstraction+ e = lerror
    { error "\"in\" expected to close a \"some 'a 'b ..\" construction" e }
| SOME e = lerror
    { error "type abstractions expected after \"some\"" e }

coercion:
| t = l(polytype) { ([], t) }
| vars = local_unif_vars t = l(polytype) { (vars, t) }

%inline coerced(X):
| LPAREN x = l(X) COLON t = l(coercion) RPAREN { (x, t) }
| LPAREN X COLON e = lerror
    { error "type expected after \":\" in coercion" e }

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%% Kinds %%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

kind:
| STAR { ETypeKinds.Star }
| k1 = kind ARROW k2 = kind { ETypeKinds.Arrow (k1, k2) }

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%% Types %%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%inline type_constructor:
| v = LIDENT
    { `PConstr (s_typeconstr v) }

%inline real_type_variable:
| v = QUOTELIDENT
    { s_typevar v }

%inline type_variable:
| v = real_type_variable
    { v }

simple_monotype:
| LPAREN m = polytype RPAREN
    { m }
| v = type_variable
    { `Var v }
| UNDER
    { `Bottom }
| t = type_constructor
    { `Constr (t, []) }
(* Type constructor with a single parameter *)
| m = simple_monotype; t = type_constructor
    { `Constr (t, [m]) }
(* Type constructor with at least two parameters *)
|  args = paren(separated_list_mintwo (COMMA, polytype)); t = type_constructor
    { `Constr (t, args) }
//Errors
| LPAREN e = lerror
    { error "type or polytype bound expected (after '(' )" e }
| paren(separated_list_mintwo (COMMA, polytype)); e = lerror
    { error "type constructor expected after type constructor arguments" e }

monotype:
| m = simple_monotype { m }
(* type of an uple *)
| l = separated_list_mintwo(STAR, simple_monotype)
    { `Constr (`Uple (List.length l), l) }
//Errors
| simple_monotype STAR e = lerror
    { error "type expected (after \"t *\")" e }

%inline sep_bound:
| BANG GREATER
    { Flex, Explicit }
| BANG EQUAL
    { Rigid, Explicit }
| GREATER
    { Flex, Implicit }
| EQUAL
    { Rigid, Implicit }


(* We distinguish "bound abstractions" of the form (α ≥ σ) and "kind
    abstractions" (α : κ). When bound abstraction only are expected
    (eg. "some .. in"), a simple variable 'a is considered to mean
    (α ≥ ⊥). When a kind abstraction is expected (eg. type-level "fun
    .. -> .." ), the simple variable means (α : κ). When both are
    expected, (α ≥ ⊥) takes the precedence, but actually in those
    contexts both constructions have the same meaning.

    The grammar is thus split between bound abstractions and kind
    abstractions, but also between "short" (simple variable) and
    "long" forms for each construction.
*)

(** There is a slight conflict between `long_type_abstraction` and `monotype`:
    - "LPAREN real_type_variable" is also prefix of `monotype`

    It is not a big problem as we have ending tokens to disambiguate
    the different constructions :
    (LPAREN real_type_variable sep_bound) cannot be a monotype. The
    only place were there could be a conflict is thus the error
    productions.

*)
long_bound_abstraction:
| alpha = real_type_variable BANG
    { (alpha, `Bound ((Flex, Explicit), `Bottom)) }
| LPAREN alpha = real_type_variable flags = sep_bound sigma = polytype RPAREN
    { alpha, `Bound(flags, sigma) }
//Errors
(* LPAREN real_type_variable lerror is spotted in 'monotype' already*)
| LPAREN real_type_variable s = sep_bound e = lerror
    { error
        (sprintf "type expected after \"('a %s\" (in bound of quantified type)"
           (binding_flags_errormsg s)) e }

short_bound_abstraction:
| alpha = real_type_variable
    { (alpha, `Bound ((Flex, Implicit), `Bottom)) }

bound_abstraction:
| b = short_bound_abstraction { b }
| b = long_bound_abstraction { b }

long_kind_abstraction:
| LPAREN alpha = real_type_variable COLON kind = kind RPAREN
    { alpha, `Kind kind }
//Errors
| LPAREN real_type_variable COLON e = lerror
    { error "kind expected after \"('a :\" (in bound of quantified type)" e }

short_kind_abstraction:
| alpha = real_type_variable
    { alpha, `Kind ETypeKinds.Star }

kind_abstraction:
| k = short_kind_abstraction { k }
| k = long_kind_abstraction { k }

type_abstraction:
| b = short_bound_abstraction { (b :> type_abstraction) }
| k = long_kind_abstraction { (k :> type_abstraction) }
| b = long_bound_abstraction { (b :> type_abstraction) }

app_polytype:
| m = monotype { m }
(* Application type *)
| m1 = app_polytype AROBASE m2 = restricted_polytype(monotype)
    { `Apply (m1, m2) }

restricted_polytype(restricted_type):
| LAMBDA l = kind_abstraction+ DOT t = polytype
    { List.fold_right (fun abs t -> `Lambda (abs, t))  l t }
| CIRCUMFLEX abs = type_abstraction DOT m = polytype
    { let (v, bound) = abs in
      `Forall ((v, bound), `Abstraction(`Var v, m)) }
| l = type_abstraction+ DOT m = polytype
    { List.fold_right (fun abs t -> `Forall (abs, t))  l m }
| m = restricted_type { m }
//Errors
| type_abstraction+ DOT e = lerror
    { error "type expected after \".\" \ (in quantified type)" e }

polytype:
| t = restricted_polytype(app_polytype) { t }
(* Arrow type *)
| m1 = app_polytype ARROW m2 = polytype
    { `Constr (`Arrow, [m1; m2]) }
| A LPAREN m1 = polytype COMMA m2 = polytype RPAREN
    { `Abstraction (m1, m2) }
//Errors
| app_polytype ARROW e = lerror
    { error "type expected (after \"t -> \")" e }
(* TODO 'A' errors *)

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%% Patterns %%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%inline pattern_var:
| v = LIDENT
    { s_value v }

pattern:
| v = pattern_var
    { PatVar v }
| LPAREN p = pattern RPAREN
    { p }
| c = coerced(pattern)
    { PatCoerce (fst c, snd c) }
//Errors
| LPAREN e = lerror
    { error "pattern expected" e }
| LPAREN pattern e = lerror
    { error "\": t\" or ')' expected" e }

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%% Values %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

simple_expr:
| i = INT
    { AST.ct_of_int i }
| v = LIDENT
    { (`Value (s_value v)) }
| c = UIDENT
    { try ct_constructors c 
      with Not_found -> `Constr (s_constr c) }
| LPAREN e = expr RPAREN
    { e }
| LPAREN RPAREN
    { AST.ct_of_unit () }
| c = coerced(expr)
    { let (e, t) = c in `Coerce (e, t) }
| LPAREN l = uple_elements RPAREN
    { `Uple l }
| LPAREN l = seq_expr2 RPAREN
    { l }
| LPAREN COLON t = l(coercion) RPAREN
    { `CoerceCt t }
//Errors
| LPAREN e = lerror
    { error "expression or ')' expected" e }
| LPAREN expr e = lerror
    { error "':', ',', ';' or ')' expected" e }

tyapp_expr:
(* TODO use coercion to allow some .. in instead of only polytype
   here; maybe 'coercion' should be renamed to 'unif_type' or any
   other more neutral name *)
| e = l(tyapp_expr) LBRACKET sigma = l(polytype) RBRACKET
    { `TyApp(e, sigma) }
| e = simple_expr { e }
//Errors
| tyapp_expr LBRACKET polytype e = lerror
    { error "']' expected" e }
| tyapp_expr LBRACKET e = lerror
    { error "type expected" e }

app_expr:
| e = l(tyapp_expr)
    { [e] }
| e = l(tyapp_expr)  q = app_expr
    { e :: q}

expr:
| e = tyapp_expr
    { e }
| FUN l = l(pattern)+ ARROW e = seq_expr
    { `SeqAbs (l, e) }
| FFUN l = l(type_abstraction)+ ARROW e = seq_expr
    { `SeqTyAbs (l, e) }
| e = l(tyapp_expr) l = app_expr (* l(simple_expr)+ *)
    { `SeqApp (e, l) }
| LET r = rec_flag v = constrained_let_name
    p = l(pattern)* EQUAL e1 = seq_expr IN e2 = seq_expr
    { let e1 =
        if p = [] then e1 else loc (`SeqAbs(p, e1)) $startpos(p) $endpos(e1)
      in `Let (r, (v, e1), e2) }
| vars = local_unif_vars e = seq_expr { `SomeTy (vars, e) }
| e1 = l(expr) EQUAL e2 = l(expr)
    { `Equal (e1, e2) }
| e1 = l(expr) PLUS e2 = l(expr)
    { `Plus (e1, e2) }
| e1 = l(expr) MINUS e2 = l(expr)
    { `Minus (e1, e2) }
| IF c = seq_expr THEN e = l(expr)
    { `IfThen (c, e) }
| IF c = seq_expr THEN e1 = l(expr) ELSE e2 = l(expr)
    { `IfThenElse (c, e1, e2) }
//Errors
| FUN e = lerror
    { error "pattern expected after fun" e }
| FUN pattern+ e = lerror
    { error "pattern or '->' expected after \"fun ...\"" e }
| LET e = lerror
    { error "variable or 'rec' expected after \"let\"" e }
| LET rec_flag constrained_let_name e = lerror
    { error "pattern or '=' expected after \"let v\"" e }
| LET rec_flag constrained_let_name l(pattern)* EQUAL e = lerror
    { error "expression expected after \"let v =\"" e }
| LET rec_flag constrained_let_name l(pattern)* EQUAL seq_expr e = lerror
    { error "'in' expected after \"let v = ...\"" e }
| LET rec_flag constrained_let_name l(pattern)* EQUAL seq_expr IN e = lerror
    { error "expression expected after \"let ... in\"" e }
| local_unif_vars e = lerror
    { error "expression expected after \"some ... in\"" e }
| IF e = lerror
    { error "expression expected after \"if\"" e }
| IF seq_expr THEN e = lerror
    { error "expression expected after \"if ... then\"" e }

constrained_let_name:
| v = l(pattern_var)
    { `Unconstrained v }
| c = coerced(pattern_var)
    { let (v, t) = c in `Constrained (loc (v, t) $startpos $endpos) }

seq_expr_aux:
| e = l(expr)  %prec below_SEMI (* fun p -> (v1 ; v2)  vs . (fun p -> v1) ; v2
                                  with the first v1 going through seq_expr *)
    { [], e }
| e = l(expr) SEMI l = seq_expr_aux
    { let l, e' = l in e :: l, e' }
//errors
//| expr e = lerror
//    { error "';' expected (in sequence of expressions)" e }
| expr SEMI e = lerror
    { error "'expression expected after ';' (in sequence of expressions)" e }

%inline seq_expr: r = seq_expr_aux
    { let l, e = r in
      if l = [] then e else loc (`Seq (l, e)) $startpos $endpos }

(* Sequences with at least two elements. Avoids a conflict
   because LPAREN expr RPAREN -> expr is valid (through simple_expr)
   with and without sequences *)
%inline seq_expr2:
| e = l(expr) SEMI l = seq_expr_aux
    { let l, e' = l in `Seq (e :: l, e') }
| expr SEMI e = lerror
    { error "'expression expected after ';' (in sequence of expressions)" e }


(* For uples *)
uple_elements:
| e1 = l(expr) COMMA e2 = l(expr)
    { [e1;e2] }
| e = l(expr) COMMA l = uple_elements
    { e :: l }
//errors
| expr COMMA expr e = lerror
    { error "',' or ')' expected (in uple)" e }
| expr COMMA e = lerror
    { error "expression expected (in uple)" e }

rec_flag:
|     { `NonRec }
| REC { `Rec }


//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%% Type declaration %%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%inline constr_name:
| c = UIDENT
    { s_constr c }

constructor_decl:
| c = l(constr_name)
    { (c, []) }
| c = l(constr_name) OF args = separated_nonempty_list(STAR, l(simple_monotype))
    { (c, args) }
//errors
| UIDENT OF e = lerror
    { error "'*' separated sequence of simple types expected after 'of'" e }

constructors_decls:
| PIPE? l = l(separated_nonempty_list(PIPE, constructor_decl))
    { l }
//errors
| PIPE e = lerror
    { error "constructor declaration expected after '|'" e }

type_parameters:
| v = real_type_variable
    { [v] }
| LPAREN l = separated_nonempty_list(COMMA, real_type_variable) RPAREN
    { l }
//errors
| LPAREN e = lerror
    { error "type variable expected (in type parameters)" e }

%inline type_name:
| t = LIDENT
    { s_typeconstr t }

type_decl_prefix:
| TYPE p = l(list_option(type_parameters)) t = l(type_name) EQUAL
    { t, p }
//errors
| TYPE e = lerror
    { error "type name or type parameters expected after \"type\"" e }
| TYPE type_parameters e = lerror
    { error "type name expected after type parameters" e }
| TYPE list_option(type_parameters) type_name e = lerror
    { error "'=' expected after type name (in type declaration)" e }
| type_decl_prefix e = lerror
    { error "type or '|' or constructor declaration expected" e }


inductive_declaration:
| p = type_decl_prefix l = constructors_decls
    { p, l }

alias_declaration:
| p = type_decl_prefix t = l(polytype)
    { p, t }

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%% Module phrases %%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

phrase:
| e = phrase_expr
| e = phrase_val
| e = phrase_type
| e = phrase_directive 
    { e }

%inline phrase_expr:
| e = seq_expr
    { Expr e }

%inline phrase_val:
| VAL r = rec_flag v = constrained_let_name l = l(pattern)* EQUAL e = seq_expr
    { let e = if l = [] then e
      else loc (`SeqAbs (l, e)) $startpos(l) $endpos(e) in
      Val (r, v, e) }
//Errors
| VAL e = lerror
    { error "variable or 'rec' expected after \"val\"" e }
| VAL rec_flag LIDENT e = lerror
    { error "variable or '=' expected after \"val ...\"" e }

%inline phrase_type:
| i = inductive_declaration
    { let t, c = i in Inductive (t, c) }
| a = alias_declaration
    { let t, t' = a in Alias (t, t') }

directive_option:
| PLUS opt = LIDENT { (opt, true) }
| MINUS opt = LIDENT { (opt, false) }

help_command_item:
| item = LIDENT { item }
| STAR { "*" }
| INCLUDE { "#include" }
| GLOBAL { "#global" }
| LOCAL { "#local" }
| HELP { "#help" }

%inline phrase_directive:
| INCLUDE file = STRING
    { Include file }
| GLOBAL option = directive_option
    { Global option }
| LOCAL option = directive_option phr = l(phrase)
    { Local (option, phr) }
| HELP command = list(help_command_item)
    { Help command }
//errors
| INCLUDE e = lerror
    { error "File path (\"foo/bar\") expected after #include" e }
| GLOBAL e = lerror
    { error "Option (+foo or -bar) excepted after #global" e }
| LOCAL e = lerror
    { error "Option (+foo or -bar) excepted after #local or #" e }
| LOCAL directive_option e = lerror
    { error "Toplevel phrase expected after local option setting" e }
| HELP list(help_command_item) e = lerror
    { error "Help command expected after #help" e }

(** Disambiguation work on phrase and optional double-semicolons :

    The usual approach is to say that, given that most phrases begin
    with unambiguous keywords (type, val, exception...),
    double-semicolons between phrases are optional.  This creates
    ambiguities with the rule with non-distinguishables beginning
    keywords, ie. `expr' : `val x = a <expr>' may be
    `val x = a;; <expr>' or `val x = (f <expr>)'

    With the #help toplevel directive, things get even worse : at the
    syntax level, all lists of LIDENT are accepted as help
    commands. `#help type void'might be `#help type void;;' or
    `#help;; type void'.

    The solution is to allows only some couples of phrases not to be
    separated by semicolons : (val, val) would be allowed, while (val,
    exp) would require an explicit double-semicolon separator.

    Due to historical details of the grammar specification (and
    possibly to a directional bias of LR parsers), this is done from
    right to left : for each kind of phrase (expr, val, type,
    directive), we specify what kind of phrase is allowed to be
    present _before_ with only an optional double-semicolon.

    For example, phrases_before_expr represent the phrases legal
    before expressions. To avoid the formerly mentioned ambiguity
    (wich may happen for types and directives as well), all phrases
    before expr end with a mandatory double-semicolon.

    The 'val' and 'type' cases are the same : all phrases may happen
    before (thanks to the distinguishing keyword), except directives
    (#help issue).

    Finally, all phrases may happen before directives, but
    expressions. This is not currently the case, but expressions may
    gain syntax such as `foo#bar' (Objective Caml method passing) that
    would conflict with the #directive syntax.

    Remark : an alternative solution would be to request that
    directive phrases always end with semicolons. This is not
    practical due to the nested nature of the #local directive :
    `#+foo #-bar #+bar <phrase>;;' would have to be written
    `#+foo #-bar #+bar <phrase>;; ;; ;; ;;'.

    Note : in the toplevel, no such discussion arises, as all phrases
    must be terminated by double-semicolon to ensure interactivity
    (one can't afford to wait on the not-yet-written next token for
    disambiguation !).
*)

phrases:
| p = phrases_before_expr e = l(phrase_expr) SEMISEMI?
| p = phrases_before_val e = l(phrase_val) SEMISEMI?
| p = phrases_before_type e = l(phrase_type) SEMISEMI?
| p = phrases_before_directive e = l(phrase_directive) SEMISEMI?
    { e :: p }

phrases_before_expr:
| { [] }
| p = phrases_before_expr e = l(phrase_expr) SEMISEMI
| p = phrases_before_val e = l(phrase_val) SEMISEMI
| p = phrases_before_type e = l(phrase_type) SEMISEMI
| p = phrases_before_directive e = l(phrase_directive) SEMISEMI
    { e :: p }

%inline phrases_but_directive:
| { [] }
| p = phrases_before_expr e = l(phrase_expr) SEMISEMI?
| p = phrases_before_val e = l(phrase_val) SEMISEMI?
| p = phrases_before_type e = l(phrase_type) SEMISEMI?
| p = phrases_before_directive e = l(phrase_directive) SEMISEMI
    { e :: p }

phrases_before_val:
| p = phrases_but_directive
    { p }

phrases_before_type:
| p = phrases_but_directive
    { p }

%inline phrases_but_expr:
| { [] }
| p = phrases_before_expr e = l(phrase_expr) SEMISEMI
| p = phrases_before_val e = l(phrase_val) SEMISEMI?
| p = phrases_before_type e = l(phrase_type) SEMISEMI?
| p = phrases_before_directive e = l(phrase_directive) SEMISEMI?
    { e :: p }

phrases_before_directive:
| p = phrases_but_expr
    { p }



int: i = INT  { `Ct (s_value (string_of_int i), `Constr (`Int, [])) }
int_: i = l(int) EOF { i }

toplevel_phrase:
| e = l(phrase) SEMISEMI { e }
| EOF { raise End_of_file }

//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%% Entry points %%%%%%%%%%%%%%%%%%%%%%%
//%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

expr_: e = seq_expr EOF { e }
| e = lerror { error "beginning of expression expected" e }
monotype_: t = l(monotype)  EOF { t }
polytype_: t = l(polytype)  EOF { t }
phrases_ :
| l = phrases EOF { List.rev l }
| EOF { [] }
