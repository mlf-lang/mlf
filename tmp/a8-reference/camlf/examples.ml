let id_id_let = "let x = fun y -> y in x x"
let id_id = "(fun x -> x) (fun x -> x)"
let id = "fun x -> x"
let id_int = "(fun x -> x) 1"
let abs_int = "fun x -> 1"

let poly_exp = "fun x -> let x = (x : 'a. 'a -> 'a) in x x"

let poly = "fun (x : 'a. 'a -> 'a) -> x x"
let poly' = "fun (x : 'a. ('a -> 'a) -> ('a -> 'a)) -> x x"
let poly'' = "fun (x : 'a. ('b > 'a -> 'a). ('c > 'a -> 'a). 'b -> 'c) -> x x"
let x_x = "fun x -> x x"
let two_lets = "let x = fun y -> y in let z = x x in z z"
let let_x = "fun x -> let y = x in x y"
let app1 = "fun x y z -> (x y) (y z)"
let app2 = "fun x y -> y (x y)"
let app3 = "fun x y -> y (x y) y"
let coerce = "fun x -> (x : 'a. 'a -> 'a) x"
let coerce' = "fun x -> x (x : 'a. 'a -> 'a)"
let coerce'' = "fun x -> (x : 'a. 'a -> 'a) (x : 'a. 'a -> 'a)"

let ct_bot = "(: some 'a in 'a )"
let ct_id = "(: some 'a in 'a -> 'a)"
let ct_sid = "(: 'a. 'a -> 'a)"
let ct_aba = "(: some 'b in 'a. 'a -> 'b -> 'a)"

let ifthenelse = "fun x y z -> (x : some 'a in 'a -> 'a -> 'a) y z "
let booltrue = "fun y z -> y"
let boolfalse = "fun y z -> z"
let either = "fun u v -> (fun x y z -> x y z) (fun y z -> y) u v"

let fail = "(fun (u : 'a. 'b. 'a -> 'b) -> u) (fun x -> x)"

let same_as_expl2 = "fun (x : 'b. 'b -> 'b) -> x"


let complexity i =
  String.concat "\n\t"
    ("" :: "let x y = (y, y) in " ::
     Utils.ct_list "let x y = x (x y) in" i @ [ "x (fun z -> z)" ])

let complexity =
  Array.init 5 (fun i -> "comp"^ string_of_int i, complexity (i+1));;

let examples = [
   "id", id; 
   "id_id", id_id;
   "id_id_let", id_id_let; 
   "id_int", id_int;
   "abs_int", abs_int;
   "poly_exp", poly_exp; 
   "poly", poly;
   "poly'", poly';
   "poly''", poly'';
   "x_x",  x_x; (* cycle *)
   "two_lets", two_lets;  (* cycle *)
   "let_x", let_x;     (* cycle *)
   "app1", app1;
   "app2", app2; 
   "app3", app3;      (* cycle *)
   "coerce", coerce;
   "coerce'", coerce'; (* not typable, raise Bound *)
   "coerce''", coerce''; (* not typable, raise Cobound *)
   "ct_bot", ct_bot;
   "ct_id", ct_id;
   "ct_sid", ct_sid;
   "ct_aba", ct_aba; 
   "ifthenelse", ifthenelse;
   "booltrue", booltrue;
   "boolfalse", boolfalse;
   "either", either;
   "fail_cobound", fail;
   "same_as_expl2", same_as_expl2;
]

let predefined = ref (examples @ Array.to_list complexity);;
