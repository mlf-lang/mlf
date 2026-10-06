open Kaputt.Generator

type 'a gen = random -> 'a
type 'a printer = 'a -> string

val to_kaputt : 'a gen -> 'a printer -> 'a t
val kaputt_gen : 'a t -> 'a gen
val kaputt_prn : 'a t -> 'a printer

(** 'a gen is a functor *)
val map : ('a -> 'b) -> 'a gen -> 'b gen
val map' : 'a gen -> ('a -> 'b) -> 'b gen

(** 'a gen is applicative *)
val app : ('a -> 'b) gen -> 'a gen -> 'b gen
val app' : 'a gen -> ('a -> 'b) gen -> 'b gen

val pure : ('a -> 'b) -> ('a -> 'b) gen

(** 'a gen is a monad *)
val return : 'a -> 'a gen
val bind : ('a -> 'b gen) -> 'a gen -> 'b gen
val bind' : 'a gen -> ('a -> 'b gen) -> 'b gen
val join : 'a gen gen -> 'a gen

(** parametrized fixpoints *)
val fix : (('a -> 'b gen) -> ('a -> 'b gen)) -> 'a -> 'b gen

(** Value generators and combinators *)
val split_int : int -> (int * int) gen
val make_char : char -> int -> char gen
val lowercase : char gen
val uppercase : char gen

(* adapted from Kaputt.Generator *)
val unit : unit gen
val make_int : int -> int -> int gen
val string : int gen -> char gen -> string gen
val bool : bool gen

val select_list : 'a list -> 'a gen
val choose_list : 'a gen list -> 'a gen
