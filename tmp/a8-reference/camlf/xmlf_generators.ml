module G = Generator
open Common_generators

type scope =
  { exp : int;
    typ : int }

let closed_scope = { exp = 0; typ = 0 }

let open_e scope = { scope with exp = scope.exp + 1 }
let open_t scope = { scope with typ = scope.typ + 1 }

(** generator for (closed) xMLF types *)
let typ_ =
  let gen gen (fuel, scope) =
    G.choose_list
      (nullary ~cond:(scope.typ > 0) ~fuel
         (fun () ->
            G.bind (fun n -> G.return (XAst.TVar (`B (XEnv.TVar.var n))))
              (G.make_int 0 scope.typ))
       @ nullary' ~fuel XAst.TBot
       @ binary' ~fuel (gen, scope) (gen, scope)
         (fun sigma tau -> XAst.TArrow (sigma, tau))
       @ binary' ~fuel (gen, scope) (gen, open_t scope)
         (fun sigma tau -> XAst.TBound (XEnv.TVar.bind, sigma, tau))) in
  G.fix gen

let fixed_param_typ len = typ_ (len, closed_scope)
let param_typ len = G.bind fixed_param_typ (G.make_int 1 len)
let typ : XAst.typ G.gen = param_typ 100

(** generator for (closed) xMLF type computations *)
let tycomp_ =
  let gen gen (fuel, scope) =
    G.choose_list
      (nullary ~fuel ~cond:(scope.typ > 0)
         (fun () ->
            G.bind (fun n -> G.return (XAst.Hyp (`B (XEnv.TVar.var n))))
              (G.make_int 0 scope.typ))
       @ nullary' ~fuel XAst.Refl
       @ nullary' ~fuel XAst.Intro
       @ nullary' ~fuel XAst.Elim
       @ unary' ~fuel (gen, scope) (fun phi -> XAst.Inner phi)
       @ unary' ~fuel (gen, open_t scope)
         (fun phi -> XAst.Outer (XEnv.TVar.bind, phi))
       @ unary' ~fuel (typ_, scope)
         (fun sigma -> XAst.Bot sigma)
       @ binary' ~fuel (gen, scope) (gen, scope)
         (fun phi khi -> XAst.Trans (phi, khi))) in
  G.fix gen

let fixed_param_tycomp len = tycomp_ (len, closed_scope)
let param_tycomp len = G.bind fixed_param_tycomp (G.make_int 1 len)
let tycomp : XAst.tycomp G.gen = param_tycomp 100

(** generator for (closed) xMLF expressions *)
let exp_ scope =
  let gen gen (fuel, scope) =
    (* There is a risk of fuel exhaustion if we use it when
       scope.exp > 0 : when we reach fuel = 0, there is no nullary
       constructor available, as the only nullary exp constructor is
       the bound variable.

       Therefore :
       - the only constructor allowed when fuel = 1 is lambda, with
       a 0-fuel type
       - when using 'binary', we must ensure that the split doesn't
       leave the exp part with 0 fuel; to do that, we reduce the
       amount of fuel to split by the number of 'exp' recursive
       calls ('need' parameter), and independently give each of them
       one more fuel ('more_fuel' function) *)
    if scope.exp = 0 && fuel = 1 then
      let typ = typ_ (0, scope) in
      let exp = gen (fuel - 1, open_e scope) in
      G.bind' typ
        (fun sigma ->
           G.bind' exp
             (fun a -> G.return (`Lam (XEnv.EVar.bind, sigma, a))))
    else
      let binary'' ?(need=0) ?(cond=true) x =
        let cond, fuel =
          if scope.exp > 0 then cond, fuel
          else
            (* we reserve 'need' supplementary fuel to ensure completion *)
            cond && fuel >= need, fuel - need in
        binary' ~cond ~fuel x in
      let more_fuel gen =
        if scope.exp > 0 then gen (* no need for more fuel *)
        else fun (fuel, scope) -> gen (fuel + 1, scope) in
      G.choose_list
        (nullary ~fuel ~cond:(scope.exp > 0)
           (fun () ->
              G.bind (fun n -> G.return (`Var (`B (XEnv.EVar.var n))))
                (G.make_int 0 scope.exp))
         @ binary'' ~need:0 (typ_, scope) (gen, open_e scope)
           (fun sigma a -> `Lam (XEnv.EVar.bind, sigma, a))
         @ binary'' ~need:2 (more_fuel gen, scope) (more_fuel gen, scope)
           (fun a b -> `App (a, b))
         @ binary'' ~need:1 (more_fuel gen, scope) (gen, open_e scope)
           (fun a b -> `Let (XEnv.EVar.bind, a, b))
         @ binary'' ~need:1 (typ_, scope) (more_fuel gen, open_t scope)
           (fun sigma a -> `TyAbs (XEnv.TVar.bind, sigma, a))
         @ binary'' ~need:1 (more_fuel gen, scope) (tycomp_, scope)
           (fun a phi -> `TyComp (a, phi))) in
  G.fix gen scope

let fixed_param_exp len = exp_ (len, closed_scope)
let param_exp len = G.bind fixed_param_exp (G.make_int 1 len)
let exp : XAst.exp G.gen = param_exp 100


(** Kaputt generators (with printer) *)
let typ_printer typ = XPrint.doc (XPrint.typ XEnv.empty typ)
let typ_k = G.to_kaputt typ typ_printer

let tycomp_printer tycomp = XPrint.doc (XPrint.tycomp XEnv.empty tycomp)
let tycomp_k = G.to_kaputt tycomp tycomp_printer

let exp_printer exp = XPrint.doc (XPrint.exp XEnv.empty exp)
let exp_k = G.to_kaputt exp exp_printer


(** Compact printers : extract ML source terms out of AST values *)
let typ_source_printer typ = XPrint.doc ~compact:true (XPrint.ML.typ typ)
let typ_k_source = G.to_kaputt typ typ_source_printer

let tycomp_source_printer tycomp = XPrint.doc ~compact:true (XPrint.ML.tycomp tycomp)
let tycomp_k_source = G.to_kaputt tycomp tycomp_source_printer

let exp_source_printer exp = XPrint.doc ~compact:true (XPrint.ML.exp exp)
let exp_k_source = G.to_kaputt exp exp_source_printer

(** generator check : each fixed-size generator produces terms of the given size *)
module KG = Kaputt.Generator
module KS = Kaputt.Specification
module KT = Kaputt.Test

let param_generator_test
    ?title ?nb_runs ?classifier ?random_src (min_len, max_len)
    (param_gen : int -> 'a G.gen) (size : 'a -> int) (printer : 'a -> string) =
  let generator : (int * 'a) G.gen =
    G.bind' (G.make_int min_len (max_len + 1))
      (fun n -> G.map (fun t -> (n, t)) (param_gen n)) in
  let func (n, t) = (n, size t) in
  let spec : (int * 'a, int * int) KS. t =
    KS.implies'
      (fun (n, _t) -> KS.is_pos_int n)
      (fun (n, s) -> n = s) in
  let prn = Kaputt.Utils.make_string_of_tuple2 string_of_int printer in
  KT.make_random_test ?title ?nb_runs ?classifier ?random_src
    (G.to_kaputt generator prn) func [spec]

let test_generators () =
  KT.run_tests
    [ param_generator_test ~title:"xAst.typ generator size check"
        (0, 1000) fixed_param_typ XAst.size_typ typ_printer
    ; param_generator_test ~title:"XAst.tycomp generator size check"
      (0, 1000) fixed_param_tycomp XAst.size_tycomp tycomp_printer
    ; param_generator_test ~title:"XAst.exp generator size check"
      (1, 1000) fixed_param_exp XAst.size_exp exp_printer ];
  flush_all ()
