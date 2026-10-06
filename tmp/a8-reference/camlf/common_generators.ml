(** Common functions for term/tree generators (gMLF or xMLF) *)
module G = Generator

let maybe p f = if p then [f ()] else []

(* Copied from xmlf_generators : to factorize ? *)
let nullary ~fuel ?(cond=true) f =
  maybe (cond && fuel = 0) f
let nullary' ~fuel ?cond x =
  nullary ~fuel ?cond (fun () -> G.return x)

let unary ~fuel ?(cond=true) (a, x) f =
  maybe (cond && fuel > 0) (fun () -> G.bind f (a (fuel - 1, x)))
let unary' ~fuel ?cond (a, x) f =
  unary ~fuel ?cond (a, x) (fun va -> G.return (f va))

let binary ~fuel ?(cond=true) (a, x) (b, y) f =
  maybe (cond && fuel > 0)
    (fun () ->
       G.bind' (G.split_int (fuel - 1))
         (fun (fuel_a, fuel_b) ->
            G.bind' (a (fuel_a, x))
              (fun va -> G.bind (f va) (b (fuel_b, y)))))
let binary' ~fuel ?cond (a, x) (b, y) f =
  binary ~fuel ?cond (a, x) (b, y) (fun va vb -> G.return (f va vb))
(* enf of xmlf copy *)
