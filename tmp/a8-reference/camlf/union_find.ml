(** This module implements a simple and efficient union/find algorithm.
    See Robert E. Tarjan, ``Efficiency of a Good But Not Linear Set
    Union Algorithm'', JACM 22(2), 1975. *)

(** The abstraction defined by this module is a set of points,
    partitioned into equivalence classes. With each equivalence class,
    a piece of information, of abstract type ['a], is associated; we
    call it a descriptor.

    A point is implemented as a cell, whose (mutable) contents consist
    of a single link to either information about the equivalence class,
    or another point. Thus, points form a graph, which must be acyclic,
    and whose connected components are the equivalence classes. In
    every equivalence class, exactly one point has no outgoing edge,
    and carries information about the class instead. It is the class's
    representative element.

    Information about a class consists of an integer weight (the number
    of elements in the class) and of the class's descriptor. *)

type 'a point = {
    mutable link: 'a link;
    mutable info: 'a;
  }

and 'a link =
  | Info of 'a info
  | Link of 'a point

and 'a info = {
    mutable weight: int;
    mutable descriptor: 'a;
  }

(** [fresh desc] creates a fresh point and returns it. It forms an
    equivalence class of its own, whose descriptor is [desc]. *)
let fresh desc = 
   { link = Info { weight = 1; descriptor = desc };
     info = desc; }

(** [repr point] returns the representative element of [point]'s
    equivalence class. It is found by starting at [point] and following
    the links. For efficiency, the function performs path compression
    at the same time. *)
let rec repr point =
  match point.link with
  | Link point' ->
      let point'' = repr point' in
      if point'' != point' then
	(* [point''] is [point']'s representative element. Because we
	   just invoked [repr point'], [point'.link] must be [Link
	   point'']. We write this value into [point.link], thus
	   performing path compression. Note that this function never
	   performs memory allocation. *)
	point.link <- point'.link;
      point''
  | Info _ -> point

(** [find point] returns the descriptor associated with [point]'s
    equivalence class. *)
let rec find point = match point.link with
  | Info info -> info.descriptor
  | Link point -> find (repr point)

let sync t = t.info <- find t;;

let info point = point.info

(** [union point1 point2] merges the equivalence classes associated
    with [point1] and [point2] into a single class whose descriptor is
    that originally associated with [point2].

    The fact that [point1] and [point2] do not originally belong to the
    same class guarantees that we do not create a cycle in the graph.

    The weights are used to determine whether [point1] should be made
    to point to [point2], or vice-versa. By making the representative
    of the smaller class point to that of the larger class, we
    guarantee that paths remain of logarithmic length (not accounting
    for path compression, which makes them yet smaller). *)
let union ?(update=(fun ~keep:_ ~lose:_ -> ())) ~keep:point_k ~lose:point_l () =
  let point_k = repr point_k
  and point_l = repr point_l in
    if point_k != point_l then
    match point_k.link, point_l.link with
      | Info info_k, Info info_l ->
          update ~keep:info_k.descriptor ~lose:info_l.descriptor;
          let weight_k = info_k.weight
          and weight_l = info_l.weight in
            if weight_k >= weight_l then
	      (point_l.link <- Link point_k;
	       info_k.weight <- weight_k + weight_l)
            else
              (point_k.link <- Link point_l;
               info_l.weight <- weight_l + weight_l;
               info_l.descriptor <- info_k.descriptor
              )
      | _, _ ->
          assert false (* [repr] guarantees that [link] matches [Info _]. *)

(** [equivalent point1 point2] tells whether [point1] and [point2]
    belong to the same equivalence class. *)
let equivalent point1 point2 =
  repr point1 == repr point2

(** [redundant] maps all members of an equivalence class, but one, to
    [true]. *)
let redundant = function
  | { link = Link _ } -> true
  | { link = Info _ } -> false
