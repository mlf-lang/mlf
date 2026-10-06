(* external identity : 'a -> 'a = "%identity" *)
let identity x = x

type 'a int_t = int
let int_t = identity
let t_int = identity
let any_int = identity

let add = ( + )
let sub = ( - )
let mul = ( * )
let div = ( / )
let neg = ( ~- )

let successor = succ
let predecessor = pred
let increment = incr

let print_int_t = print_int

type 'a string_t = string
let string_t = identity
let t_string = identity
let any_string = identity

let concat = ( ^ )
let concat_list = String.concat

let print_string_t = print_string


module SetS_ = Set.Make(String)
module SetS (X: sig type t end) : Set.S with type elt = X.t string_t = SetS_

module MapS_ = Map.Make(String)
module MapS (X: sig type t end) : Map.S with type key = X.t string_t = MapS_
