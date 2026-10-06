module G = Generator
open Common_generators

let value_printer = Opaque.t_string
let exp_printer = AST.source_expr_to_string
let loc_printer e = exp_printer e.Locations.obj

let loc e = { Locations.obj = e; Locations.loc = Locations.dummy_loc }

(** generator for gMLF syntaxic expressions *)
let var : AST.value G.gen =
  G.map Opaque.string_t
    (G.string (G.make_int 1 4) G.lowercase)

let exp_ env =
  let gen gen (fuel, env) : AST.source_expr Locations.loc G.gen =
    G.map loc begin
      (* See Xmlf_generators.exp_ comment for the fuel exhaustion
         risk *)
      if env = [] && fuel = 1 then
        G.bind' var
          (fun v ->
             G.map' (gen (fuel - 1, v :: env)) (fun e -> `Abs(loc v, e)))
      else
        let binary'' ?(need=0) ?(cond=true) x =
          let cond, fuel =
            if env <> [] then cond, fuel
            else
              (* we reserve 'need' supplementary fuel to ensure completion *)
            cond && fuel >= need, fuel - need in
        binary' ~cond ~fuel x in
      let more_fuel gen =
        if env <> [] then gen (* no need for more fuel *)
        else fun (fuel, scope) -> gen (fuel + 1, scope) in
      G.bind' var 
        (fun fresh_var ->
           G.choose_list
             (nullary ~fuel ~cond:(env <> [])
                (fun () -> G.map' (G.select_list env) (fun v -> `Value v))
              @ unary' ~fuel (gen, fresh_var :: env)
                (fun e -> `Abs (loc fresh_var, e))
              @ binary'' ~need:2 (more_fuel gen, env) (more_fuel gen, env)
                (fun a b -> `App (a, b))
              @ binary'' ~need:1 (more_fuel gen, env) (gen, fresh_var :: env)
                (fun a b ->
                   `Let (`NonRec, (`Unconstrained (loc fresh_var), a), b))))
    end in
  G.fix gen env

let fixed_param_exp len = exp_ (len, [])
let param_exp len = G.bind fixed_param_exp (G.make_int 1 len)
let exp = param_exp 5

let exp_printer = AST.source_expr_to_string
let exp_k = G.to_kaputt exp exp_printer

