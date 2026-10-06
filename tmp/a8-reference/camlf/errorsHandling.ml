open Format
open Highlight


let report_error ppf exn =
  let report ppf = function
    | SyntaxErrors.LexingError e ->
        SyntaxErrors.report_lexing_error ppf e

    | SyntaxErrors.ParsingError e ->
        SyntaxErrors.report_parsing_error ppf e

    | TypingErrors.TypingError e ->
        TypingErrors.report_typing_error ppf e

    | GraphErrors.GraphError e ->
        GraphErrors.report_graph_error ppf e

    | GUnify.Errors.UnifError e ->
        GUnify.Errors.report_unif_error ppf e

    | ToplevelErrors.ToplevelError e ->
        ToplevelErrors.report_toplevel_error ppf e

    | FeatureErrors.FeatureError e ->
        FeatureErrors.report_feature_error ppf e

    | exn ->
        fprintf ppf "Unknown error :\n%s" (Printexc.to_string exn) in

  fprintf ppf "@[%a@]@." report exn


let error_to_string = Utils.format_into_string report_error
