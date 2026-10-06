module G = Kaputt.Generator

type 'a gen = G.random -> 'a
type 'a printer = 'a -> string

let to_kaputt gen prn = (gen, prn)
let kaputt_gen = fst
let kaputt_prn = snd

(** 'a gen is a monad *)
let map f gen = fun rand -> f (gen rand)
let map' gen f = map f gen

let app f gen = fun rand -> f rand (gen rand)
let app' gen f = app f gen

let pure f = fun _ -> f

let return x = fun _ -> x
let bind f gen = fun rand -> f (gen rand) rand
let bind' gen f = bind f gen
let join gen = fun rand -> gen rand rand

let rec fix derec_gen param =
  fun rand -> derec_gen (fix derec_gen) param rand

(** Value generators *)
let unit = kaputt_gen G.unit
let bool = kaputt_gen G.bool
let make_int a b = kaputt_gen (G.make_int a b)

let make_char start len =
  map' (make_int 0 len) (fun n -> char_of_int (n + int_of_char start))
let lowercase = make_char 'a' 26
let uppercase = make_char 'A' 26
let digit = make_char '0' 10

let string int char = kaputt_gen
  (G.string (to_kaputt int string_of_int) (to_kaputt char (String.make 1)))

let select_list li = map (List.nth li) (make_int 0 (List.length li))
let choose_list li = join (select_list li)

let split_int n =
  map' (make_int 0 (n+1)) (fun k -> k, n - k)
