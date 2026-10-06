type gtype = GType.gtype

(** global environments :
   - type defined in `Alias phrases
   - values defined in `Val phrases *)
module Global = struct
  module TMap = ETypeConstructors.TypeConstrMap
  module EMap = AST.ValueMap

  type type_env = gtype TMap.t
  type expr_env = gtype EMap.t

  type env = { 
      typ : type_env;
      exp : expr_env;
    }

  let empty = {
    typ = TMap.empty;
    exp = EMap.empty;
  }

  let find_typ constr env =
    TMap.find constr env

  let add_typ constr gtype env =
      { env with typ = 
        TMap.add constr gtype env.typ }

  let find_exp value env =
    EMap.find value env

  let add_exp value gtype env =
    { env with exp =
      EMap.add value gtype env.exp }
end



(** Local type environments *)
module Typ = struct
  module TMap = ETypeConstructors.TypeVarMap

  type env = {
      global : gtype Global.TMap.t;
      local : gtype TMap.t;
    }

  let of_global g = {
    global = g;
    local = TMap.empty
  }

  let empty = of_global Global.empty.Global.typ

  let add var gtype env =
    { env with local = TMap.add var gtype env.local }

  let find var env = TMap.find var env.local
end

(** Local value environments *)
module Exp = struct
  module EMap = AST.ValueMap

  type env = {
      global : gtype Global.EMap.t;
      local : gtype EMap.t;
    }

  let of_global g = {
    global = g;
    local = EMap.empty
  }

  let empty = of_global Global.empty.Global.exp

  let add value gtype env =
    { env with local = EMap.add value gtype env.local }

  let find value env = EMap.find value env.local
end

(** Local environments, both types and values *)
module Local = struct
  type env = {
    typ : Typ.env;
    exp : Exp.env;
  }

  let empty = {
    typ = Typ.empty;
    exp = Exp.empty;
  }

  let of_global g = {
    typ = Typ.of_global g.Global.typ;
    exp = Exp.of_global g.Global.exp;
  }

  let add_typ var gtype env =
      { env with typ = 
        Typ.add var gtype env.typ }

  let add_exp value gtype env =
    { env with exp =
      Exp.add value gtype env.exp }
end
