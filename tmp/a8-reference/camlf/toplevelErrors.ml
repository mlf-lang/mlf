open Locations

type toplevel_error =
  | File_not_found of (Locations.location * string)
  | Invalid_option of (Locations.location * string)

exception ToplevelError of toplevel_error

let report_toplevel_error ppf = function
  | File_not_found (loc, file) ->
      Highlight.print_loc ppf loc;
      Format.fprintf ppf "Cannot find file %s." file
  | Invalid_option (loc, option) ->
      Highlight.print_loc ppf loc;
      Format.fprintf ppf "Invalid option %s." option

