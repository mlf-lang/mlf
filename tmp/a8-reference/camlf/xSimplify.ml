open XAst

let rec simplify : exp -> exp = function
  | `Var v -> `Var v
  | `Builtin b -> `Builtin b
  | `App (a, b) -> `App (simplify a, simplify b)
  | `Lam(x, sigma, a) -> `Lam(x, sigma, simplify a)
  | `TyAbs(alpha, sigma, a) -> `TyAbs(alpha, sigma, simplify a)
  | `Let(x, a, b) -> `Let(x, simplify a, simplify b)
  | `TyComp _ as a ->
      let rec collect_tycomp acc = function
        (* collect (a[φ])[χ] acc = collect a (φ::χ::acc) *)
	| `TyComp(a, phi) -> collect_tycomp (phi :: acc) a
	| a ->
            let a = simplify a in
            simplify_tycomp a acc in
      collect_tycomp [] a
and simplify_tycomp a li =
  let trans = function
    | [] -> Refl
    | hd::tl -> List.fold_left (fun a b -> Trans(a, b)) hd tl in
  let rec simpl = function
    (* routine *)
    | [] -> []
    | Trans(a, b) :: rest -> simpl (a :: b :: rest)

    (* removing identity computations *)
    | Refl :: rest -> simpl rest

    | Inner phi :: rest ->
        (match simpl [phi] with
           | [] -> simpl rest
           | li -> Inner (trans li) :: simpl rest)
    | Outer (alpha, phi) :: rest ->
        (match simpl [phi] with
           | [] -> simpl rest
           | li -> Outer (alpha, trans li) :: simpl rest)

    (* Optimizing the introduction of fresh bounds *)
    | Intro :: rest ->
	begin match simpl rest with
	  | [] -> Intro :: []
	  | Inner phi :: rest ->
	      let phis = simpl [phi] in
	      let rec simpl_intro = function
		| [] -> []
		| Bot TBot :: rest -> simpl_intro rest
		| rest -> rest in
	      begin match simpl_intro phis with
		| [] -> simpl (Intro :: rest)
		| phis -> Intro :: Inner (trans phis) :: simpl rest
	      end
	  | phi :: rest -> Intro :: phi :: simpl rest
	end

    (* Optimizing reordering : TODO *)
    (* Sharing computation contexts : TODO *)

    | (Bot _ | Hyp _ | Elim) as phi :: rest -> phi :: simpl rest
  in
  match simpl li with
    | [] -> a
    | li -> `TyComp(a, trans li)

