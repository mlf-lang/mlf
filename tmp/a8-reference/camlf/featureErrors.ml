open Locations
open Highlight
open Format

type feature_error =
  | FOmega of location
  | XmlfOmega of location
  | XmlfGlobalVal of location

exception FeatureError of feature_error

let feature_error e = raise (FeatureError e)

let report_feature_error ppf = function
  | FOmega loc ->
      print_loc ppf loc;
      fprintf ppf "Higher-order types (Fω) features are not yet supported."

  | XmlfOmega loc ->
      print_loc ppf loc;
      fprintf ppf "xMLF translation of higher-order types (Fω) is not yet supported."

  | XmlfGlobalVal loc ->
      print_loc ppf loc;
      fprintf ppf
        "xMLF does not yet support translation from global values (toplevel \
         declarations)."

