(** We use De Bruijn indices to represent binders. Algorithms from the
   "Engineering Formal MetaTheory" paper, wich describes the "locally
   nameless" representation :
   - free variables have names
   - bound variables use De Bruijn indices
*)

(** Generic vars; we use a functor to produce different var types, in
   order not to mix type variables and expression variables *)
module type VarS = sig
  type free_var = private string
  val fvar : string -> free_var
  val fresh_var : free_var list -> free_var
  (** assert (is_fresh (fresh_var used_vars) used_vars)) *)

  type bound_var = private int

  val zero : bound_var 
  val var : int -> bound_var

  (** binders carry no information, they're here so that bindings are
      explicit in the AST : (Lam of EVar.binder * typ * expr) *)
  type binder = private unit
  val bind : binder

  type scope = private int
  val scope : int -> scope
  (* a scope is a difference between two binder for example, when
     going from λx.λy.F(x,y) to just F(x,y), we enter two binders (x
     and y) and thus have scope 2 (morally, [y; x]) *)

  val zero_s : scope

  val open_ : binder -> scope
  (** scope +1 : to be used when entering a lexical scope *)
  val close_ : binder -> scope
  (** scope -1 : to be used when leaving a lexical scope *)

  val add : scope -> scope -> scope

  val open_s : binder -> scope -> scope
  val close_s : binder -> scope -> scope
  (** {open_close v s} (resp. close_s) is a shortcut for
      {add s (open_ v)} (resp. close_) *)

  val shift : scope -> scope:scope -> bound_var -> bound_var
  (** change the bound var by the given scope difference, if the
      variable is not local is the given ~scope.
   
      Raise an error if the result is negative : be careful tu
      substitue 'zero' away before using 'close_'. 
   *)

  val is_hole : bound_var -> scope:scope -> bool
  (** is the given bound_var the variable just outside the scope ? *)

  type var = [ `B of bound_var | `F of free_var ]
end

module type VarNames = sig
  (* I'm not proud of the delay (unit -> ..) in the
     preferred_var_names function.  

     The reason why it's there is that the type var names depend on
     a runtime configuration option : do we use UTF8 var names or
     ASCII var names ?

     It would be better to rewrite this part of the code. More
     generally, the whole "giving global names to De Bruijn indices is
     an environment question" idea smells.
   *)

  val preferred_var_names : unit -> string array
end

module MakeVar (T : VarNames) : VarS = struct
  type bound_var = int
  let zero = 0
  let one = 1
  let var k = k

  let eq = (=)

  type free_var = string
  let fvar str = str
  let is_fresh var used_vars = not (List.mem var used_vars)

  (* choose a variable name among the preferred_var_names, possibly
     appending a numerical suffix, to ensure the name is fresh with
     respect to the given used variables *)
  let fresh_var used_vars =
    let preferred_var_names =
      (* ensure non-empty array *)
      match T.preferred_var_names () with
	| [| |] -> [| "var" |]
	| names -> names in
    let module Local = struct
      exception Correct of string
    end in
      try
	let suffix = ref 1 in
	let test var =
	  let name =
	    if !suffix = 1 then var
	    else var ^ string_of_int !suffix in
	    if is_fresh name used_vars then raise (Local.Correct name) in
	  while true do
            Array.iter test preferred_var_names;
	    incr suffix
	  done;
	  assert false
      with Local.Correct name -> fvar name

  let fresh_var used_vars =
    let var = fresh_var used_vars in
    assert (is_fresh var used_vars);
    var

  type binder = unit
  let bind = ()

  type scope = int
  let scope k = k
  let zero_s = 0

  let open_ () = 1
  let close_ () = -1

  let add = (+)

  let open_s () k = k+1
  let close_s () k = k-1

  let is_local k ~scope = k < scope
  let shift diff ~scope k =
    if is_local k ~scope then k
    else
      (assert (k + diff >= 0);
       k + diff)

  let is_hole k ~scope = (k = scope)

  type var = [ `B of bound_var | `F of free_var ]
end

module TVarNames = struct
  let preferred_var_names () =
    [| Symbol.alpha (); Symbol.beta (); Symbol.gamma (); Symbol.delta () |]
end
module EVarNames = struct
  let preferred_var_names =
    let tab = [| "x"; "y"; "z" |] in
    fun () -> tab
end

module TVar : VarS = MakeVar(TVarNames)
module EVar : VarS = MakeVar(EVarNames)


(** Environments

    There are environments for both expression and type variables.
    Moreover, we have for each variables two kind of environments :

    - free variables environment : the global environment for
    primitive (free variables), wich is not expected to change
    during term traversal (no "add" method, only of_list)

    - bound variables environment : the local environment to the
    DeBruijn-indexed term. Evolves as we enter the binding structure
    of a term to explore its subterms.
*)
module MakeFreeEnv (V : VarS) : sig
  type +'a t
  val empty : 'a t

  val find : V.free_var -> 'a t -> 'a
  val of_list : (V.free_var * 'a) list -> 'a t

  val map : ('a -> 'b) -> 'a t -> 'b t
  val mapi : (V.free_var -> 'a -> 'b) -> 'a t -> 'b t
  val fold : (V.free_var -> 'a -> 'b -> 'b) -> 'a t -> 'b -> 'b
end = struct
  module OrderedFreeVars = struct
    type t = V.free_var
    let compare a b = String.compare (a : t :> string) (b : t :> string)
  end
  include Map.Make(OrderedFreeVars)
  let of_list pairs = List.fold_right (fun (k,v) -> add k v) pairs empty
end

module MakeBoundEnv (V : VarS) : sig
  type +'a t
  val empty : 'a t

  val find : V.bound_var -> 'a t -> 'a
  val add : V.binder -> 'a -> 'a t -> 'a t

  val map : ('a -> 'b) -> 'a t -> 'b t
  val mapi : (V.binder -> 'a -> 'b) -> 'a t -> 'b t
  val fold : (V.binder -> 'a -> 'b -> 'b) -> 'a t -> 'b -> 'b

  val zip : (V.binder -> 'a -> 'b -> 'c) -> 'a t -> 'b t -> 'c t
    (** correlate two bound env; used when printing an environment, to
        correlate the printing environment (names for bound variables)
        and the typing environment (values for bound variables) *)

  val contextual_fold : (V.binder -> 'a -> 'a t -> 'b -> 'b) -> 'a t -> 'b -> 'b
    (** fold the bound env, giving for each element its own binding
        env (the tail of the list). Used in printing environments. *)

  val depth : 'a t -> V.scope
    (** depth (height) of an environment; used to calculate how much
        to shift the topmost bindings (eg. free variables) *)
    
  val scope_diff : 'a t -> 'a t -> V.scope
    (** scope difference between two contextes, used to shift a bound
        value by the correct value when accessing its variable in
        a deeper context *)
end = struct
  (* The bound variable environment is a stack : correspondance is
     maintained between De Bruijn indices and position in the env. For
     example, the first binding in the list correspond to
     the bound var 0. When you enter a binder, you push a new binding
     on the stack, and all previous binding positions increase by 1,
     matching the De Bruijn indices in the subterm.

     Getting the binding for a var k is like (List.nth k env), except
     that we use the Var.zero, Var.open_ abstraction instead of numerical
     indices.
  *)
  type 'a t = (V.binder * 'a) list
  let empty = []

  let find var env =
    let rec find_ scope = function
      | [] -> raise Not_found
      | (binder, value) :: rest ->
	  if V.is_hole ~scope var then value
	  else find_ (V.open_s binder scope) rest in
    find_ V.zero_s env

  let add binder value env = (binder, value) :: env
  let map f =
    List.map (fun (binder, value) -> binder, f value)
  let mapi f =
    List.map (fun (binder, value) -> binder, f binder value)
  let fold f env init =
    List.fold_right (fun (binder, value) -> f binder value) env init

  let zip f = List.map2 (fun (binder, a) (_, b) -> binder, f binder a b)

  let rec contextual_fold f env init = match env with
    | [] -> init
    | (binder, value)::context ->
	f binder value context (contextual_fold f context init)

  let depth li = V.scope (List.length li)
  let scope_diff la lb = V.scope (List.length la - List.length lb)
end


(**
   The env type records the 4 different types of environments, with
   the following mnemonics :
   f/b : free variables / bound variables
   e/t : expression variables / type variables

   It is parametrized over the value types for expression and type
   variable bindings.
*)
module FE = MakeFreeEnv(EVar)
module FT = MakeFreeEnv(TVar)

module BE = MakeBoundEnv(EVar)
module BT = MakeBoundEnv(TVar)

type ('tvar_data, 'evar_data) t =
    { ft : 'tvar_data FT.t;
      fe : 'evar_data FE.t;
      bt : 'tvar_data BT.t;
      be : 'evar_data BE.t;
      be_contextes : 'tvar_data BT.t BE.t }
      (** be_contextes assign to each bound expression variable the
          type context in wich it was declared *)

let toplevel ~ft ~fe =
  { ft = FT.of_list ft;
    fe = FE.of_list fe;
    bt = BT.empty;
    be = BE.empty;
    be_contextes = BE.empty }

let empty = toplevel ~ft:[] ~fe:[]

let add_tvar alpha sigma env =
  { env with bt = BT.add alpha sigma env.bt }
let add_evar x sigma env =
  { env with
      be = BE.add x sigma env.be;
      be_contextes = BE.add x env.bt env.be_contextes }

let find_evar evar env = match evar with
  | `F x -> FE.find x env.fe
  | `B x -> BE.find x env.be

(** tvar_scope_diff, evar_scope_diff : when accessing a binding in the
    environment, it is necessary to know the scope difference between
    the binding and the access place, in order to reindex correctly
    the out-of-scope indices *)
let tvar_scope_diff tvar env : TVar.scope =
  match (tvar : TVar.var) with
    | `F _ -> BT.depth env.bt
    | `B v ->
        (* for B k, scope difference is (k+1)
           TODO find a natural expression for this computation *)
        TVar.scope ((v :> int) + 1)

let evar_scope_diff evar env : TVar.scope =
  match (evar : EVar.var) with
    | `F _x -> BT.depth env.bt
    | `B x -> BT.scope_diff env.bt (BE.find x env.be_contextes)

let find_tvar tvar env = match tvar with
  | `F alpha -> FT.find alpha env.ft
  | `B alpha -> BT.find alpha env.bt

let free_evars env = FE.fold (fun x _ li -> x :: li) env.fe []
let free_tvars env = FT.fold (fun alpha _ li -> alpha :: li) env.ft []
