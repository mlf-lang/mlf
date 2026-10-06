(** Opaque types for [int] and [string].
This module provides a convenient way to convert [int] or [string] types
to abstract types.

Motivation: type [int] may be used for representing several kinds of 
data. Confusion is easy, so we often need to make it abstract, 
while keeping:
- the functions that used to work with type [int]
- efficiency
- no creation of specific modules

This solution was suggested by Jacques Garrigue.
What the user has to do is [open Opaque] and then
use a type parameter to define
the specialized version of [int] or [string].
We will write the type declarations as
[type port = [`Port] int_t] or [type date = [`Date] int_t].
Data is converted with the [int_t] and [t_int] polymorphic 
functions as in [let port : port = int_t 0].

@author Martin Jambon *)

(** {6 Opaque [int]s } *)

type 'a int_t
(** data of type ['a int_t] has the same internal representation
   as type [int]. *)

val int_t : int -> 'a int_t
val t_int : 'a int_t -> int
val any_int : 'a int_t -> 'b int_t
(** [int_t], [t_int] and [any_int] are type conversion functions. *)


val add : 'a int_t -> 'a int_t -> 'a int_t
val sub : 'a int_t -> 'a int_t -> 'a int_t
val mul : 'a int_t -> 'a int_t -> 'a int_t
val div : 'a int_t -> 'a int_t -> 'a int_t
val neg : 'a int_t -> 'a int_t
(** [add], [sub], [mul], [div] and [neg] are the equivalents
  of [( + )], [( - )], [( * )], [( / )] and [( ~- )]. *)

val successor : 'a int_t -> 'a int_t
val predecessor : 'a int_t -> 'a int_t
val increment : 'a int_t ref -> unit
(** [successor], [predecessor] and [increment] are the equivalents
  of [( + )], [( - )], [( * )], [( / )] and [( ~- )]. *)

val print_int_t : 'a int_t -> unit


(** {6 Opaque [string]s } *)

type 'a string_t
(** data of type ['a string_t] has the same internal representation
   as type [string]. *)

val string_t : string -> 'a string_t
val t_string : 'a string_t -> string
val any_string : 'a string_t -> 'b string_t
(** [int_string], [t_string] and [any_string] are type conversion functions. *)

val concat : 'a string_t -> 'a string_t -> 'a string_t
val concat_list : string -> 'a string_t list -> 'a string_t
(** [concat] and [concat_list] are equivalents of [( ^ )] 
and [String.concat]. *)

val print_string_t : 'a string_t -> unit


module SetS :
  functor (X : sig type t end) ->
    sig
      type elt = X.t string_t
      type t
      val empty : t
      val is_empty : t -> bool
      val mem : elt -> t -> bool
      val add : elt -> t -> t
      val singleton : elt -> t
      val remove : elt -> t -> t
      val union : t -> t -> t
      val inter : t -> t -> t
      val diff : t -> t -> t
      val compare : t -> t -> int
      val equal : t -> t -> bool
      val subset : t -> t -> bool
      val iter : (elt -> unit) -> t -> unit
      val fold : (elt -> 'a -> 'a) -> t -> 'a -> 'a
      val for_all : (elt -> bool) -> t -> bool
      val exists : (elt -> bool) -> t -> bool
      val filter : (elt -> bool) -> t -> t
      val partition : (elt -> bool) -> t -> t * t
      val cardinal : t -> int
      val elements : t -> elt list
      val min_elt : t -> elt
      val max_elt : t -> elt
      val choose : t -> elt
      val split : elt -> t -> t * bool * t
    end



module MapS :
  functor (X : sig type t end) ->
    sig
      type key = X.t string_t
      type +'a t
      val empty : 'a t
      val is_empty : 'a t -> bool
      val add : key -> 'a -> 'a t -> 'a t
      val find : key -> 'a t -> 'a
      val remove : key -> 'a t -> 'a t
      val mem : key -> 'a t -> bool
      val iter : (key -> 'a -> unit) -> 'a t -> unit
      val map : ('a -> 'b) -> 'a t -> 'b t
      val mapi : (key -> 'a -> 'b) -> 'a t -> 'b t
      val fold : (key -> 'a -> 'b -> 'b) -> 'a t -> 'b -> 'b
      val compare : ('a -> 'a -> int) -> 'a t -> 'a t -> int
      val equal : ('a -> 'a -> bool) -> 'a t -> 'a t -> bool
    end
