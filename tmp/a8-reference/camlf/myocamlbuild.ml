open Ocamlbuild_plugin;;
open Command;;

(*
let packages = "lablgtk2";; (* written using a comma separated list *)
let ocamlfind x = S [ A "ocamlfind"; x; A "-package"; A packages];;
*)

let run_and_read cmd =
  let str = Ocamlbuild_pack.My_unix.run_and_read cmd in
  let len = String.length str in
  if not (len > 0 && str.[len - 1] = '\n')
  then str
  else String.sub str 0 (len - 1)

let ocamlfind_dir package =
  run_and_read
    (Printf.sprintf
       "ocamlfind query -i-format %s | sed s/\\-I\\ //" package)
let () = 
  dispatch begin function
  (*
   | Before_options ->
       (* by using Before_options one let command line options have 
          an higher priority *) 
       (* on the contrary using After_options will guarantee to have 
          the higher priority *)
       Options.ocamlc := ocamlfind & S [ A "ocamlc"; A "-g"; ];
       Options.ocamlopt := ocamlfind & A "ocamlopt";
       Options.make_links := false;
  *)
  
    | After_rules ->
        let findlib (findlib_name, lib_name) = 
          ocaml_lib ~extern:true ~dir:(ocamlfind_dir findlib_name) lib_name in
        let lib name = (name, name) in
        List.iter findlib [ ("lablgtk2", "lablgtk"); lib "camomile"; lib "kaputt" ];
	let odot_dir =	
		try Sys.getenv "ODOT_DIR"
		with Not_found -> "+cameleon" in
        ocaml_lib ~dir:odot_dir ~extern:true "odot";
        (* why "cameleon" ? in Debian, odot is contained in the
           libcameleon-ocaml-dev package, and odot files go in
           /usr/lib/ocaml/cameleon *)
    | _ -> ()
  end;;
