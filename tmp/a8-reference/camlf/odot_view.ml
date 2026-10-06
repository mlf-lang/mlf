(******************************************************************************)
(*                Odot                                                        *)
(*                                                                            *)
(*    Copyright (C) 2005 Institut National de Recherche en Informatique et    *)
(*    en Automatique. All rights reserved.                                    *)
(*                                                                            *)
(*    This program is free software; you can redistribute it and/or modify    *)
(*    it under the terms of the GNU General Public License as published       *)
(*    by the Free Software Foundation; either version 2.1 of the License, or  *)
(*    any later version.                                                      *)
(*                                                                            *)
(*    This program is distributed in the hope that it will be useful,         *)
(*    but WITHOUT ANY WARRANTY; without even the implied warranty of          *)
(*    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           *)
(*    GNU Lesser General Public License for more details.                     *)
(*                                                                            *)
(*    You should have received a copy of the GNU General Public License       *)
(*    along with this program; if not, write to the Free Software             *)
(*    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA                *)
(*    02111-1307  USA                                                         *)
(*                                                                            *)
(*    Contact: Maxence.Guesdon@inria.fr                                       *)
(******************************************************************************)

(* Heavy updates by Boris Yakobowski *)


(** A Lablgtk2 box to view dot graphs.*)

let default_dot_ppi = 72.0

open Odot

(* let extract_bb (c1, c2, c3, c4) = *)
(*   if c1 = 0 && c4 = 0 then *)
(*     c2, c3 *)
(*   else if c1 = 0 && c2 = 0 then *)
(*     c4, c3 *)
(*   else assert false *)

let int_of_string str = truncate (float_of_string str)

let extract_bb (c1, c2, c3, c4) =
  let li = [c1;c2;c3;c4] in
  match List.filter (fun x -> abs x < 10) li with
    | [c; c'] -> (c, c')
    | li ->
        List.iter (fun x -> prerr_newline (prerr_int x)) li;
        assert false

let show image file zoom_file zoom =
  let com = Printf.sprintf "convert -resize %d%% %s %s"
      zoom
      (Filename.quote file)
      (Filename.quote zoom_file)
  in
  match Sys.command com with
  | 0 -> image#set_file zoom_file
  | n -> failwith (Printf.sprintf "Exec error %d: %s" n com)

let extract_field field attr_list =
  match attr_value (Simple_id field) attr_list with
    | Some (Simple_id v)
    | Some (Double_quoted_id v) -> v
    | _ -> raise Not_found

let rec parse_spline = function
  | [] -> []
  | ("s" | "e") :: q -> parse_spline q
  | e1 :: e2 :: q -> (float_of_string e1, float_of_string e2) :: parse_spline q
  | _ :: _ -> assert false

(* let get_graph_bounding_box g = *)
(*   Utils.extract_one (function *)
(*      | Stmt_attr (Attr_graph attr_list) -> *)
(*          (try match Utils.split_string (extract_field "bb" attr_list) [','] with *)
(* 	    | [x1; y1; x2; y2] -> *)
(*                 Some (int_of_string x1, int_of_string y1, *)
(* 		      int_of_string x2, int_of_string y2) *)
(* 	    | _ -> None *)
(*           with Not_found -> None) *)
(*      | _ -> None) *)
(*     g.stmt_list *)

let get_graph_bounding_box g =
  let rec iter = function
    [] -> raise Not_found
  | (Stmt_attr (Attr_graph attr_list)) :: q ->
      begin
        match attr_value (Simple_id "bb") attr_list with
          Some (Simple_id v)
        | Some (Double_quoted_id v) ->
            begin
              match Utils.split_string v [','] with
                [x1;y1;x2;y2] ->
                  (
                   let (a,b,c,d) =
                     (int_of_string x1, int_of_string y1,
                      int_of_string x2, int_of_string y2)
                   in
                   match a,b,c,d with
                     0, _, _, 0 -> (0,0,c,b)
                   | _ as x -> x
                  )
              | _ -> raise Not_found
            end
        | _ -> iter q
      end
  | _ :: q -> iter q
  in
  iter g.stmt_list


let find_nodes_edges_annotated_graph graph =
  let nodes = new Utils.store ()
  and edges = new Utils.store () in
  let rec iter = function
    | [] -> ()
    | Stmt_node (node_id,attr_list) :: q ->
	let w = float_of_string (extract_field "width" attr_list) in
	let h = float_of_string (extract_field "height" attr_list) in
	let (x,y) =
          (match Utils.split_string (extract_field "pos" attr_list)
             [','] with
	       | [x;y] -> (int_of_string x, int_of_string y)
	       | _ -> assert false
          ) in
	let w = w *. default_dot_ppi in
	let h = h *. default_dot_ppi in
	let x1 = (float x) -. w /. 2.0 in
	let y1 = (float y) -. h /. 2.0 in
	let x2 = (float x) +. w /. 2.0 in
	let y2 = (float y) +. h /. 2.0 in
	let s_id = string_of_node_id node_id in
        nodes#add ((x1, y1, x2, y2), s_id);
        iter q
    | Stmt_edge (Edge_node_id n1, [Edge_node_id n2], attr_list) :: q ->
        let pos = Utils.split_string (extract_field "pos" attr_list) [','; ' ']
        and edge = (string_of_node_id n1, string_of_node_id n2) in
        let pos' = List.map (fun c -> (c, edge)) (parse_spline pos) in
        edges#addl pos';
        iter q
    | Stmt_subgraph g :: q ->
	iter (g.sub_stmt_list @ q)
    | _ :: q -> iter q
  in
  iter graph.stmt_list;
  nodes#get, edges#get


class box ?(dot_program="dot") ~filesuffix ~(box_zoom:GPack.box) ~(box_image:GPack.box) () =
  let dot_file = Printf.sprintf "%s.dot" filesuffix in
  let annot_dot_file = Printf.sprintf "%s.annot.dot" filesuffix in
  let png_file = Printf.sprintf "%s.png" filesuffix in

  (* Zoom *)
  let frame_zoom = GBin.frame ~label:"Zoom" ~packing:box_zoom#pack () in
  let zooms =
      [ 10 ; 20 ; 30 ; 40 ; 50 ; 60 ; 70 ; 80 ; 90 ; 100 ; 120 ]
  in
  let wcombo = GEdit.combo
      ~popdown_strings: (List.map (fun s -> Printf.sprintf "%d%%" s) zooms)
      ~allow_empty:false
      ~enable_arrow_keys:true
      ~value_in_list:true
      ~width:70
      ~packing:(frame_zoom#add)
      ()
  in

  (* Graph *)
  let wscroll = GBin.scrolled_window
      ~vpolicy:`AUTOMATIC
      ~hpolicy:`AUTOMATIC
      ~packing:(box_image#pack ~expand:true ~from:`START)
      ()
  in
  let evt_box = GBin.event_box ~packing:wscroll#add_with_viewport () in
  let image = GMisc.image ~packing:evt_box#add () in
  let _ = image#set_xalign 0.0 in
  let _ = image#set_yalign 0.0 in


  object(self)
    val mutable current_zoom = 100.0
    val mutable dot_width = 1
    val mutable dot_height = 1
    val mutable nodes = []
    val mutable edges = []

    method combo_zoom = wcombo
    method image = image
    method evt_box = evt_box
    method zooms = zooms

    method private zoom_file_of_zoom zoom =
      Printf.sprintf "%s_%d%%.png" (Filename.chop_extension png_file) zoom

    method zoom () =
      let z =
	try Scanf.sscanf wcombo#entry#text "%d%%" (fun a -> Some a)
	with _ -> None
      in
      match z with
      | None -> ()
      |	Some 100 ->
	  current_zoom <- 100.0;
	  image#set_file png_file
      |	Some z ->
	  let f = self#zoom_file_of_zoom z in
	  if Sys.file_exists f then
	    image#set_file f
	  else
	    show image png_file f z;
	  current_zoom <- float z

    method update_info =
      let graph = parse_file annot_dot_file in
      let h, w =  extract_bb (get_graph_bounding_box graph) in
      let n, e = find_nodes_edges_annotated_graph graph in
      dot_width <- w;
      dot_height <- h;
      nodes <- n;
      edges <- e;

    method clean_files =
      List.iter (fun f -> try Sys.remove f with _ -> ())
	[ annot_dot_file ; png_file];
      List.iter (fun z -> try Sys.remove (self#zoom_file_of_zoom z) with _ -> ()) zooms;

    method refresh_image () =
      self#clean_files;
      let com = Printf.sprintf
	  "%s -s%d -y %s > %s && %s -s%d -T png -o %s %s"
	  dot_program
	  (int_of_float default_dot_ppi)
	  (Filename.quote dot_file)
	  (Filename.quote annot_dot_file)
	  dot_program
	  (int_of_float default_dot_ppi)
	  (Filename.quote png_file)
	  (Filename.quote dot_file)
      in
      match Sys.command com with
        | 0 ->
	    self#update_info ;
	    self#zoom ()
        | n -> GToolbox.message_box "Error"
	    (Printf.sprintf "Exec error %d: %s" n com)

    method at_pos x y =
      let px = image#pixbuf in
      let dc = {
   	Gobject.kind = `INT ;
   	Gobject.proj = (function `INT n -> n | _ -> assert false) ;
	Gobject.inj = (fun n -> `INT n);
      } in
      let image_width = Gobject.Property.get px
        { Gobject.name = "width" ; Gobject.conv = dc } in
      let image_height = Gobject.Property.get px
	{ Gobject.name = "height" ; Gobject.conv = dc } in
      let ratio_x = (float image_width) /. (float dot_width) in
      let ratio_y = (float image_height) /. (float dot_height) in
      let nodes, edges =
        let x = float x in
        let y = float y in
        List.filter
	  (fun ((x1,y1,x2,y2),_) ->
	     x1 *. ratio_x <= x && x <= x2 *. ratio_x &&
             y1 *. ratio_y <= y && y <= y2 *. ratio_y
	  ) nodes,
        List.filter
          (fun ((xp, yp), _) ->
             let d = 6. in
             xp *. ratio_x -. d <= x && x <= xp *. ratio_x +. d &&
             yp *. ratio_y -. d <= y && y <= yp *. ratio_y +. d
          ) edges
      in
      (Utils.unique (=) (List.map snd nodes),
       Utils.unique (=) (List.map snd edges))


    initializer
      ignore (box_image#connect#destroy (fun () -> self#clean_files));
      wcombo#entry#set_editable false;
      wcombo#entry#set_text "100%";
      ignore (wcombo#entry#connect#changed self#zoom );

  end
