(** This module implements a simple and efficient union/find algorithm.
    See Robert E. Tarjan, ``Efficiency of a Good But Not Linear Set
    Union Algorithm'', JACM 22(2), 1975. *)

(** The abstraction defined by this module is a set of points,
    partitioned into equivalence classes. With each equivalence class,
    a piece of information, of abstract type ['a], is associated; we
    call it a descriptor. *)
type 'a point

(** [fresh desc] creates a fresh point and returns it. It forms an
    equivalence class of its own, whose descriptor is [desc]. *)
val fresh: 'a -> 'a point

(** [find point] returns the descriptor associated with [point]'s
    equivalence class. *)
val find: 'a point -> 'a
(** [info point] returns the original descriptor associated with [point]'s. *)
val sync: 'a point -> unit
val info: 'a point -> 'a

(** [union f point1 point2] merges the equivalence classes associated
    with [point1] and [point2] into a single class. If the descriptors
    of [point1] and [point2] were [d1] and [d2], the descriptor of the
    result is [f d1 d2]. *)
val union: ?update:(keep:'a -> lose:'a -> unit) ->
  keep:'a point -> lose:'a point -> unit -> unit

(** [equivalent point1 point2] tells whether [point1] and [point2]
    belong to the same equivalence class. *)
val equivalent: 'a point -> 'a point -> bool

(** [redundant] maps all members of an equivalence class, but one, to
    [true]. *)
val redundant: 'a point -> bool

(** [repr point] returns the representative element of [point]'s
    equivalence class, meaning that for any other [point'] such
    that [equivalent point point'] is true, [repr point'] returns
    the same result as [repr point] *)
val repr : 'a point -> 'a point
