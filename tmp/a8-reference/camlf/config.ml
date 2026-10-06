type flag =
    {
     name : string;
     (* should be unique *)
     short_descr : string;
     long_descr : string option;
     implies : flag list;
     (** the flags that should be implicitly changed when this one
         changes *)
    }

let flag name ?(implies=[]) short long =
  {
   name = name;
   implies = implies;
   short_descr = short;
   long_descr = long;
  }

module FlagSet = Set.Make(struct
  type t = flag
  let compare f1 f2 =
    String.compare f1.name f2.name
end)

module Conf = struct
  type state = FlagSet.t

  let is_set state flag =
    FlagSet.mem flag state
      
  let simple_set state flag =
    FlagSet.add flag state
  let simple_clear state flag =
    FlagSet.remove flag state

  (* set the flag as well as all its dependencies *)
  let cascade_set state flag =
    let rec set state flag =
      List.fold_left set (simple_set state flag) flag.implies in
    set state flag

  (* clear the flag, as well as all its reverse dependencies *)
  let cascade_clear state flag_to_clear =
    let set_to_clear = ref (FlagSet.singleton flag_to_clear) in
    let is_to_clear f = FlagSet.mem f !set_to_clear in
    let rec clear flag =
      if not (is_to_clear flag) then begin
        List.iter clear flag.implies;
        if List.exists is_to_clear flag.implies then
          set_to_clear := FlagSet.add flag !set_to_clear
      end in
    FlagSet.iter clear state;
    FlagSet.diff state !set_to_clear

  let test () =
    let f s li = flag ~implies:li s s None in
    let a = f "a" [] in
    let b = f "b" [a] in
    let c = f "c" [b] in
    let d = f "d" [c] in
    let e = f "e" [d] in
    let (!) li =
      List.fold_right FlagSet.add li FlagSet.empty in
    
    let (=~) a b =
      FlagSet.compare a b = 0 in
    assert (simple_set ![a; e] c =~ ![a; c; e]);
    assert (simple_clear ![a; c; e] c =~ ![a; e]);
    assert (cascade_set ![a; e] c =~ ![a; b; c; e]);
    assert (cascade_clear ![a; c; e] c =~ ![a]);
    ()
      
  (* silent, continuous testing *)
  let () = test ()


  (* by default, set is cascading and clear is not *)
  let set ?(cascade=true) state flag =
    (if cascade then cascade_set else simple_set)
      state flag

  let clear ?(cascade=false) state flag =
    (if cascade then cascade_clear else simple_clear)
      state flag
end
include Conf

let default_conf = FlagSet.empty

let xmlf =
  flag "xmlf" "Translate to xmlf."
    (Some
"
  When this configuration flag is set, typed gMLF expressions are
  translated into xMLF terms. If given in the command line, it applies
  to all registered expressions (selected examples, files
  parameters...). It also applies for each expression typed in the
  toplevel.

  For now, the generated xMLF terms are only printed and type-checked
  : it is not possible to manipulate them as values. They may play a
  more interessant role in the future; in particular, they can be
  reduced to produce xMLF values, giving MLF terms an operational meaning.

  xMLF translation does not yet cover the full MLFω language. The MLF
  language, as described in Boris Yakobowski's thesis, all have a
  translation, but explicit rigid polymorphism and Fω features require
  an extension of the original xMLF language wich is still to be done.

  Example :

    # #+xmlf fun (x : 'a . 'a -> 'a) -> x x;;
    ('a. 'a → 'a) → ('b. 'b → 'b)
    graph type :
    ∀(α≥∀(α≥⊥) (α → α)) (∀(β≥⊥) (β → β) → α)
    translated term :
    Λ(α≥∀(α≥⊥) (α → α))
      λ(x:∀(β≥⊥) (β → β))
        (let y =
          (Λ(β≥∀(β≥⊥) (β → β)) λ(y:∀(γ≥⊥) (γ → γ)) y)[&] x in
        y[∀(≥▹∀(β≥⊥) ∀(γ≥⊥) (β → γ)); ∀(≥∀(β≥) ∀(≥β◃); &); &] y)
        [α◃]
    translation type :
    ∀(α≥∀(α≥⊥) (α → α)) (∀(β≥⊥) (β → β) → α)
")
;;

let xmlf_utf8 =
  flag ~implies:[xmlf] "xmlf_utf8"
    "Use UTF8 symbols for concise printing of xMLF terms."
(Some
"
  Print translated xMLF terms (see flag 'xmlf') using UTF8 symbols
  such as ∀, ≥ and Λ, instead of the more verbose ASCII equivalents
  (‌\\/, >= and /\\). Note that there is no direct xMLF parser for the
  moment, so neither of the textual representation is parsable.

  Also settable through the XMLF_UTF8 environment value.

  Note : For debugging purposes, there is a XPrint.ML module wich
  prints the ocaml representaiton of a given xMLF AST in a directly
  evaluable form.

")
(* add utf8 by default *)
let default_conf =
  Conf.simple_set default_conf xmlf_utf8

let xmlf_reduce =
  flag ~implies:[xmlf] "xmlf_reduce"
    "Activate evaluation by reduction of translated xMLF terms"
(Some
"
  Use the reduction algorithm to evaluate translated xMLF terms (see
  flag 'xmlf'). Intermediary reduction steps may be displayed using
  the 'xmlf_reduce_verbose' falg.
")

let xmlf_reduce_verbose =
  flag ~implies:[xmlf_reduce] "xmlf_reduce_verbose"
    "Print intermediary reduction steps during xmlf reduction (see 'xmlf_reduce' flag)"
    None

let print_source =
  flag "print_source" "Print source term."
(Some
"
  Print eMLF source terms after parsing, and before desugaring. Useful
  for debugging either the parser or the printer.

")

let print_desugared =
  flag "print_desugared" "Print desugared source term."
(Some
"
  Print eMLF source terms after the desugaring process. Mostly useful
  to understand the graph generated by terms using coercions.

")

let backtrace =
  flag "backtrace" "Print backtraces for all exceptions."
(Some
"
  Print backtraces for exceptions occuring during the typing (and xMLF
  translation) process. Useful for typer debugging purposes.

  An issue with the exception handling is that there is no distinction
  between errors revealing bugs in the type engine, and errors simply
  generated by non-typable terms. For example, `fun x -> x x' is a
  non-typable term that will generate a perfectly genuine GUnify.Cycle
  error.

  It would be possible to differentiate exceptions generated by
  invariant breaking in the engine (wich are always signs of an
  internal bug), and non-typability bugs (wich are generally `good'
  errors), but some engine bugs cause erroneous non-typability, and it
  is therefore useful to also debug those.

")


 let xmlf_backtrace =
   flag "xmlf_backtrace" "Print xmlf translation backtraces."
(Some
"
  Print backtraces (see option `backtrace') for the exception
  generated during the xMLF translation process

  As those always denote internal error of the xMLF translation code
  (translation of well-typed gMLF must be well-typed xMLF terms), this
  flag is set by default.

")

let gmlf_backtrace =
  flag "gmlf_bactrace" "Print gMLF translation backtraces."
(Some
"
  Print backtraces (see option `backtrace') for the exception
  generated during the gMLF graph construction and solving process.

")

let fail =
  flag "fail" "Given phrases should generate errors."
(Some
"
  Should be set when evaluating phrases whose typing shouldn't
  succeed. Useful for negative tests : test that a given expresion
  *does not* type.

  The current effect of the flag is rather weak : if the given phrase
  fails, it still reports the error, and if it doesn't it only sends a
  warning, whereas a \"non-failure error\" may be more appropriate.

  Example :
    # #+fail fun x -> x;;
    'a. 'a -> 'a
    Warning: the typing of this expression should have failed.

")

let experimental_fomega =
  flag "experimental_fomega" "Activate yet experimental Higher-order Types (Fω) features."
(Some
"
   This flag activates in-type lambdas and applications :
         κ ::=                Kinds
             | ★              *
             | κ₁→κ₂          k -> k'
                              
         σ ::=                Types
             | ∀e(φ:κ)σ       ('f : * -> *) . (..)
             | λ(α≥σ)σ        lam 'a ('b > ..) ('c = ..) . (..)
             | λ(φ:κ)σ        lam ('f : * -> *) ('b > ..) . (..)
             | φ σ            'f @ 'a @ 'b
                              
         e ::=                Terms
             | Λ(α:κ)         Fun ('a : * -> *) -> ..

   For example : (lam 'a 'b . 'a -> 'b) @ int @ bool

   It is an experimental feature, as the implementation is not yet
   ready for general use.
"
)
   
let dot =
  flag "dot" "Generate some dot files during typing." None
   
let flag_list =
  [ fail
  ; print_source
  ; print_desugared
  ; xmlf
  ; xmlf_utf8
  ; xmlf_reduce
  ; xmlf_reduce_verbose
  ; backtrace
  ; xmlf_backtrace
  ; gmlf_backtrace
  ; dot
  ; experimental_fomega ]

let flag_assoc =
  List.map (fun flag -> flag.name, flag) flag_list

let flag_of_string name =
  List.assoc name flag_assoc
