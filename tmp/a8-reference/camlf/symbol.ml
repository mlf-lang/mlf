let const a ?(verbatim=false) () =
  ignore verbatim; a

let use_utf = ref true

let utf a b ?(verbatim=false) () =
  if !use_utf && not verbatim then a else b

let alpha = utf "α" "'a"
let beta = utf "β" "'b"
let gamma = utf "γ" "'c"
let delta = utf "δ" "'d"

let sigma = utf "σ" "sigma"
let tau = utf "τ" "tau"

let geq = utf "≥" ">" (* ">=" *)
let leq = utf "≤" "<="
let neq = utf "≠" "<>"
let eq = const "="

let arrow = utf "→" "->"
let forall = utf "∀" "\\/"
let lambda = utf "λ" "\\"
let _Lambda = utf "Λ" "/\\"
let turnstile = utf "⊢" "|-"
let negated_turnstile = utf "⊬" "|/-"

let bot = utf "⊥"  "-" (* "_|_" *)
let epsilon = utf "ε" "e"
let intro = utf "⅋" "intro"
let elim = const "&"
let tycomp_bot = utf "▹" "»" 
let tycomp_hyp = utf "◃" "«"

let reduces_to = utf "⇝" "->"

let star = utf "★" "*"
