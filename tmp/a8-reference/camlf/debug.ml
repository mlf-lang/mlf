let is_env_set var default =
  try
     begin match Sys.getenv var with
       | "YES" | "1" -> true
       | "NO" | "0" -> false
       | other -> failwith 
           (Printf.sprintf 
              "unknown environment value '%s' for '%s' : use YES/NO or 1/0"
              other var)
     end
   with Not_found -> default

let after_gtranslate =
  ref (is_env_set "DEBUG_GTRANSLATE" false)

let after_gsolve =
  ref (is_env_set "DEBUG_GSOLVE" false)

let after_rigidify =
  ref (is_env_set "DEBUG_RIGIDIFY" false)
let rigidify_error =
  ref (is_env_set "DEBUG_RIGIDIFY_ERROR" false)

let add_existentials =
  ref (is_env_set "DEBUG_ADD_EXISTENTIALS" false)

let after_xtranslate =
  ref (is_env_set "DEBUG_XTRANSLATE" false)

let unification_error =
  ref (is_env_set "DEBUG_UNIFICATION_ERROR" true)

let before_normalize_instance =
  ref (is_env_set "DEBUG_NORMALIZE_INSTANCE" false)

let before_normalize_unification =
  ref (is_env_set "DEBUG_NORMALIZE_UNIFICATION" false)

let before_check_explicit_instance =
  ref (is_env_set "DEBUG_CHECK_EXPLICIT_INSTANCE" false)

let before_apply_atomic_instance_operation =
  ref (is_env_set "DEBUG_APPLY_ATOMIC_INSTANCE_OPERATION" false)

let all_refs =
  [ after_gtranslate
  ; after_gsolve
  ; after_rigidify
  ; rigidify_error
  ; after_xtranslate
  ; unification_error
  ; before_normalize_instance
  ; before_normalize_unification
  ; before_check_explicit_instance
  ; before_apply_atomic_instance_operation ]

let () =
  if is_env_set "DEBUG_ALL" false then
    List.iter (fun r -> r := true) all_refs;
  if is_env_set "DEBUG_NONE" false then
    List.iter (fun r -> r := false) all_refs 
