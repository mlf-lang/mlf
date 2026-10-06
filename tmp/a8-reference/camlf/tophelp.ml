type help_document =
    Help of description * (item * (short_item_descr * help_document)) list
and description = string
and item = string
and short_item_descr = string

let help_leaf descr = Help (descr, [])

let s = Printf.sprintf

let toplevel_help_description =
"
 The toplevel help system.

 Syntax:
   #help (words | '*')*

 Examples:
   #help;;
   #help examples;;
   #help directives #local;;
   #help * backtrace;;

 The given list represent a 'help command', wich is a path in
 a hierarchical help tree. For each path, a description is given, with
 possibly a list of available children. For example, \"#help options\"
 and \"#help directives\" have children, while \"#help examples\" does
 not.

 There is a special '*' word that collapses all children of
 a node. For example, \"#help *\" will display a description of all
 #help children, and \"#help * foo\" will look for 'foo' in the
 children of 'options', 'directives', and all other #help children. If
 there is an ambiguity (two #help children have children named 'foo'),
 no result will be given, and you will have to give the explicit path.

 If, when processing one of the command word, no children is found in
 the current node, an implicit '*' is inserted. For example, if you
 ask for \"#help #include\" instead of \"#help directives #include\",
 it will be silently translated to \"#help * #include\", and find the
 correct help.

"

(**
   Read the toplevel_help_description above for a high-level
   explanation of the help search behaviour.

   Help search code :
   - 'eval' implements the global search strategy
   - 'find' is in charge of finding the next node children (with
     spelling correction)
   - 'collapse' handles the '*' functionality, by updating both the
     node description (concatenating a description of all its direct
     children) and its children list (wich becomes the list of the
     grandchildren)
*)
let eval help command =
  let fail x = (false, x) in
  let success x = (true, x) in
  let rec eval command_str (Help (description, subhelp) as help) = function
    | [] ->
        if subhelp = [] then success description
        else
          let subquery_help =
            s"You can query those items for more detailed help.\nFor example, %s %s;;\n"
              command_str (fst (List.hd subhelp)) in
          success (description ^ subquery_help ^ "\n")
    | "*" :: subcommand ->
        eval (command_str ^ " *") (collapse help) subcommand
    | item :: subcommand ->
      if subhelp = [] then
	fail (s"Help error : help command `%s` takes no subcommand.\n"
                command_str)
      else
	match find item subhelp with
	| Some (_short_desc, subhelp) ->
	    eval (command_str ^ " " ^ item) subhelp subcommand
	| None ->
            match
              eval (command_str ^ " *") (collapse help) (item :: subcommand)
            with
            | (false, _) ->
                fail (s"Help error : Invalid subcommand `%s` for command `%s`/\n"
	                item command_str)
            | (true, result) -> (true, result)
  and find item list =
    (* prevents ambiguity by matching on all associated item instead
       of just the first one (as List.assoc) *)
    match List.filter (fun (i, _) -> i = item) list with
    | _ :: _ :: _ -> None
    | [(_, subhelp)] -> Some subhelp
    | [] ->
        (* in case of failure, we try automatic spelling correction
           based on Utils.find_nearest (see detailed comment in
           utils.ml) *)
        match Utils.select_nearest item fst list with
        | None -> None
        | Some (_, subhelp) -> Some subhelp
  and collapse (Help (descr, subhelp)) : help_document =
    let collapsed_help =
      let of_subhelp (name, (_short, Help (descr, _subhelp))) = (name, descr) in
      (Utils.format_assoc_string
         ~indent:2 ~force_long:true ~doc_of_descr:Pprint.string
         (List.map of_subhelp subhelp)) in
    let subhelp' = 
      let of_subhelp (_name, (_short, Help (_descr, subhelp))) = subhelp in
      List.concat (List.map of_subhelp subhelp) in
    Help (descr ^ "\n" ^ collapsed_help, subhelp') in
  snd (eval "#help" help command)



let example_list =
  [ "fun x -> x", "A simple expression." (* " (see topic 'expressions')." *);
    "val id x = x", "A value declaration (see topic 'declarations').";
    "val either_id = (some 'a in fun (x : 'a) (y : 'a) -> x) id",
	"Another value declaration.";
    (let file = "\"Examples/boolean.mlf\"" in
     s"#include %s" file,
       s"Execute all phrases from file %s (see topic 'directives')." file);
    "#global +xmlf",
      "Change the 'xmlf' option to 'true' (see topic 'options').";
    "#+fail val auto x = x x",
      "Evaluate 'auto' value declaration with the option 'fail' \
       set to true (see topic 'options').";
  ]

let examples =
  Utils.format_assoc_string ~indent:2 example_list

let examples_help = help_leaf examples

let declarations =
  "
   The syntax of toplevel declarations is :
     val <rec> <let_name> <patt>* = <expr>
   It is translated to the following expression :
     let <rec> <let_name> <patt>* = <expr> in <let_name>

   The expression is typed, and its type is added to the environment,
   bound to the <let_name> identifier. It can then be used in further
   expressions or declarations.

   Example : `val id x = x`  ==>  `let id x = x in id`

  "

let declarations_help = help_leaf declarations

let directive_list =
  [ "#include", ("include a file by executing all its phrases",
"
 Include a file by executing all its phrases.

 Syntax: #include <string>
 
 Example: #include \"Examples/explicit.mlf\";;

");
    "#global", ("global (for all following phrases) option setting",
"
 Global (for all following phrases) option setting.
 
 Syntax: #global <option>

 See `#help options;;` for a list of available options.

 Example: #global -backtrace;;

");
    "#local", ("local (for the current phrase only) option setting",
"
 Local (for the current phrase only) option setting.

 Syntaxes:
   #local <option> <phrase>
   #<option> <phrase>

 Note that `#<option>` is available as an alias for `#local <option>`.

 See `#help options;;` for a list of available options.

 Examples:
   #local +backtrace val auto x = x x;;
   #-backtrace #+fail val auto x = x x;;
   #+xmlf #include \"nice_xmlf_translations.mlf\" 

");
    "#help", ("toplevel help", toplevel_help_description)
  ]
(** A remark about option setting : An enjoyable idea was to use
    #<option> <phrase>;; as sugar for #local <option> <phrase>;;,
    but #<option>;; as sugar for #global <option>;;

    While nice on paper, I believe this sugar would be too dangerous :
    #+foo #-bar #+baz;; really suggests all three options are globally
    changed, while in reality only the last one is.
  *)


let directives =
 s"Here is a list of available directives:\n%s\n.\n"
  (Utils.format_assoc_string ~indent:2
     (List.map (fun (name, (short, _long)) -> (name, short)) directive_list))

let directives_help =
  let to_help (name, (short, long)) =
    (name, (short, help_leaf long)) in
  Help (directives, List.map to_help directive_list)

let options_subhelp =
  let help_of_flag flag =
    let short_descr = flag.Config.short_descr in
    let descr = match flag.Config.long_descr with
      | None -> short_descr ^ "\n\n"
      | Some descr -> descr in
    (flag.Config.name, (short_descr, help_leaf descr)) in
  List.map help_of_flag Config.flag_list

let options =
 s"Dynamically changeable configuration flags:\n%s\n.\n"
  (Utils.format_assoc_string ~indent:2
     (List.map (fun (name, (short, _help)) -> (name, short)) options_subhelp))

let options_help =
  Help (options, options_subhelp)

let topics_subhelp =
  [
    "examples", ("Examples of toplevel phrases", examples_help);
    "declarations", ("Toplevel value declarations", declarations_help);
    "directives", ("Documentation of toplevel #directives", directives_help);
    "options", ("List of dynamic configuration flags", options_help);
  ]

let topics =
  s"Here is the list of available help topics:\n%s\n"
    (Utils.format_assoc_string ~indent:2
       (List.map
	  (fun (name, (short, _help)) -> (name, short))
	  topics_subhelp))

let short_help =
  "
This is an interactive toplevel. Type phrases after prompt ('#').
End phrases with double semicolons (';;'). Help is available
through the '#help' directive :
 # #help;;
"

let interactive_help =
"For practical reasons (software dependencies), the interactive gMLF
reducer is in a separate entry file, interact.ml.
To run the interactive mode, please 'make interact'.
"

let no_action_help =
"
If you wish to run MLF source files, please give them as argument to
the command line :
  camlf Examples/recursion.mlf

If you wish to run the MLF toplevel, please append the --toplevel option :
  camlf --toplevel

Note : This toplevel doesn't provide line-editing features. You should
use a readline wrapper program such as 'rlwrap' or 'ledit'.

" ^ interactive_help


let long_help =
  short_help
  ^ "\n"
  ^ topics

let help = Help (long_help, topics_subhelp)

