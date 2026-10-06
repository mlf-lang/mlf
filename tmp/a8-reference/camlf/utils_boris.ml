let show_debug = ref false

let debug ?(oc=stderr) format =
  let format' = format ^^ "\n%!" in
  if !show_debug then
    Printf.fprintf oc format'
  else
    Printf.ifprintf oc format'

let counter init =
object (self)
  val mutable c = ref init
  method get = self#incr ; !c
  method incr = c := !c + 1

  method peek = !c
  method set_to v = c := v
end

let rec remove f e = function
  | [] -> []
  | e' :: q ->
      if f e e' then
        remove f e q
      else
        e' :: remove f e q

let rec replace f e er = function
  | [] -> []
  | e' :: q ->
      (if f e e' then er else e') :: replace f e er q

let rec unique f = function
  | [] -> []
  | e :: q -> if List.exists (f e) q then unique f q else e :: unique f q

let rec assocf f e = function
  | [] -> raise Not_found
  | (e', v) :: q ->
      if f e e' then
        v
      else
        assocf f e q

let rec mem f e = function
  | [] -> false
  | e' :: q -> f e e' || mem f e q

let rec extract_one f = function
  | [] -> raise Not_found
  | e :: q ->
      match f e with
        | None -> extract_one f q
        | Some v -> v

let rec extract f = function
  | [] -> []
  | e :: q ->
      match f e with
        | None -> extract f q
        | Some v -> v :: extract f q



let fail : 'a -> 'a -> bool = fun _ _ -> failwith "store#mem undefined"

(* Accumulation lists *)
class ['a] store ?(eq=fail) () =
object (self)
  val mutable l = ([] : 'a list)
  method add v =  l <- v :: l
  method add_unique v =
    if self#mem v = false then
      self#add v
  method addl l' = l <- l' @ l
  method get = l
  method remove_matching : 'b. ('b -> 'a -> bool) -> 'b -> unit =
    fun f e ->
      l <- remove f e l
  method remove = self#remove_matching eq
  method replace_matching : 'b. ('b -> 'a -> bool) -> 'b -> 'a -> unit =
    fun f e e' ->
      l <- replace f e e' l
  method replace = self#replace_matching eq
  method restore (s : 'a store) =
    l <- s#get
  method mem e =
    mem eq e self#get
  method set l_ =
    l <- l_
  method exists f =
    List.exists f l
end

let rec iter2 f l1 l2 = match l1, l2 with
  | [], [] -> ()
  | e1 :: q1, e2 :: q2 -> f e1 e2; iter2 f q1 q2
  | _ -> raise (Invalid_argument "iter2")

let rec iteri f i = function
  | [] -> ()
  | e :: q -> f i e; iteri f (i+1) q

let rec ct_list e i =
  if i <= 0 then [] else e :: ct_list e (i - 1)


module Tree = struct

type 'a tree =
  | Empty
  | Leaf of 'a
  | Node of 'a tree * 'a tree

let rec iter f = function
  | Empty -> ()
  | Leaf v -> f v
  | Node (t1, t2) -> iter f t1; iter f t2

let rec map f = function
  | Empty -> Empty
  | Leaf v -> Leaf (f v)
  | Node (t1, t2) -> Node (map f t1, map f t2)

let rec fold f e = function
  | Empty -> e
  | Leaf v -> f v e
  | Node (t1, t2) ->
      fold f (fold f e t1) t2

let rec size = function
  | Empty -> 0
  | Leaf _ -> 1
  | Node (t1, t2) -> size t1 + size t2

let rec exists f = function
  | Empty -> false
  | Leaf e -> f e
  | Node (t1, t2) -> exists f t1 || exists f t2

end

module Tag :
sig
  type 'a tag

  val tag: unit -> 'a tag
  val equal: 'a tag -> 'a tag -> bool

  val dummy_tag: 'a tag
end =
struct
  type 'a tag = unit ref

  let tag () = ref ()
  let equal (t1 : 'a tag) (t2 : 'a tag) = t1 == t2

  let dummy_tag = tag ()
end


let unitf _ = ()


let split_string s chars =
  let len = String.length s in
  (* pos is the current position in the string,
     acc is the start of the next supposed substring *)
  let rec iter acc pos =
    if pos >= len then
      if acc = pos then [] else [String.sub s acc (pos-acc)]
    else
      if List.mem s.[pos] chars then
        if acc = pos then
          iter_start (pos+1)
        else
          (String.sub s acc (pos-acc)) :: iter_start (pos+1)
      else
        iter acc (pos + 1)
  (* Function starting a potential new substring *)
  and iter_start pos =
    iter pos pos
  in
  iter_start 0


let rec un_option_list = function
  | [] -> []
  | Some e :: q -> e :: un_option_list q
  | None :: q -> un_option_list q


let ( @?:: ) x y =
  match x with
    | None -> y
    | Some x -> x :: y


let rec print_list f sep ppf = function
  | [] -> ()
  | [e] -> Format.fprintf ppf "%a" f e
  | e :: q ->
      Format.fprintf ppf "%a" f e;
      Format.fprintf ppf sep;
      print_list f sep ppf q


let format_into_string f e =
  let buf = Buffer.create 100 in
  let ppf = Format.formatter_of_buffer buf in
  Format.fprintf ppf "@[";
  f ppf e;
  Format.fprintf ppf "@]";
  Format.pp_print_flush ppf ();
  Buffer.contents buf


let read_file ?(skip=0) ch =
  for i = 0 to skip - 1 do
    ignore (input_line ch)
  done;
  let rec loop accum =
    let line, eof =
      try (input_line ch), false
      with End_of_file -> "", true
    in
    if eof = false then
      loop (line :: accum)
    else
      List.rev accum
  in
  String.concat "\n" (loop [])

let newline_to_space s = String.map (fun c -> if c = '\n' then ' ' else c) s

let add_end_newline s =
  if s <> "" && s.[String.length s - 1] <> '\n' then
    s ^ "\n"
  else
    s
