-- Exact pre-candidate canonicalize body, qualified only for this fixture.
-- Source-only: not compiled or executed. The candidate must leave every helper
-- called here byte-identical to the pinned production source.
module CanonicalizeReference (canonicalizeBefore) where

import qualified Bootstrap.Graph as G
import qualified Bootstrap.Types as T

canonicalizeBefore :: T.Graph -> T.Graph
canonicalizeBefore graph =
  G.mkGraph
    (G.mapNodes (\node -> G.mkNode (G.mapTag (G.resolve graph) (G.tag node)) (G.binder node) (G.flag node))
       (G.nodes graph))
    (G.links graph)
    (G.nextId graph)
