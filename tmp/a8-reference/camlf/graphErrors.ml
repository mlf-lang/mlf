open Locations
open Highlight
open Format

open GType

type graph_error =
  | IncompatibleFlags of gtype * location * binding_flags * binding_flags

exception GraphError of graph_error

let graph_error e = raise (GraphError e)

let report_graph_error ppf error =
  begin match error with
  | IncompatibleFlags (g, loc, f1, f2) ->
      print_loc ppf loc;
      ignore g;
      let s flags =
        Print_type.string_of_binding_flags
          (syntactic_binding_of_graphic_binding flags) in
      fprintf ppf "Incompatible flags %s and %s." (s f1) (s f2)
  end;
  fprintf ppf "\n%!"
