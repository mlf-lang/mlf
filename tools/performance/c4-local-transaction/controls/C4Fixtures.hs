{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Fixed literals copied from pre-candidate independent C4 prefix controls.
-- No dependency on the diagnostic classifier and no selected-by-candidate input.
module C4Fixtures where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified FrozenGraph as FG
import qualified SessionGraftFixtures as A

node :: T.GTag -> Integer -> T.Node
node tag parent = T.Node tag (T.Just parent) T.Flexible
base :: T.Graph
base = T.Graph (IM.fromList
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible)
  ,(1,node (T.GCon "Int" []) 0),(2,node (T.GGen 3) 0)
  ,(3,node (T.GArr 4 5) 2),(4,node (T.GArr 6 6) 3)
  ,(5,node T.GBot 3),(6,node T.GBot 4),(7,node (T.GGen 8) 0)
  ,(8,node (T.GArr 9 10) 7),(9,node T.GBot 8),(10,node T.GBot 8)]) IM.empty 11

-- Authored topology, NOT constructed by the classifier or by an optimized path.
-- Physical construction history is compared separately against complete P3.
baseExpected :: T.Graph
baseExpected = T.Graph
  (IM.insert 14 (node T.GBot 9)
    (IM.insert 9 (node (T.GArr 14 14) 8) (FG.nodes base)))
  (IM.fromList [(11,8),(12,9),(13,10)]) 15

sharing, frontier, nonGen, kindMismatch, cyclic :: T.Graph
sharing = A.replace 3 (node (T.GArr 4 4) 2)
  (A.replace 4 (node T.GBot 2) (A.without [5,6] base))
frontier = A.replace 4 (node T.GBot 0)
  (A.replace 5 (node (T.GArr 6 6) 3)
  (A.replace 6 (node T.GBot 5)
  (A.replace 8 (node (T.GArr 4 10) 7) (A.without [9] base))))
nonGen = A.replace 7 (node (T.GGen 11) 0)
  (A.replace 8 (node (T.GArr 9 10) 11)
  (A.replace 11 (node (T.GArr 8 12) 7)
  (A.replace 12 (node T.GBot 11) base)))
kindMismatch = A.replace 8 (node (T.GTyCon "List" (T.KArrow T.Star T.Star)) 7)
  (A.without [9,10] base)
-- Literal existing SessionGraftFixtures.congruence-old-cycle-equations shape.
-- A sharing conflict creates an occurs/binding dependency cycle on fallback.
-- Its exact FIRST error is deliberately read from complete frozen P3, not
-- guessed from the generic name "occurs" (rebinding may reject first).
cyclic = A.replace 3 (node (T.GArr 4 4) 2) (A.without [5,6]
  (A.replace 8 (node (T.GArr 9 10) 7)
  (A.replace 9 (node T.GBot 8)
  (A.replace 10 (A.node (T.GArr 9 11) 8 T.Rigid)
  (A.replace 11 (A.node (T.GCon "Int" []) 10 T.Rigid) A.poly)))))

data Fixture = Fixture String T.Graph Integer Integer Bool Bool (Maybe T.Graph)
fixtures :: [Fixture]
fixtures =
  [Fixture "mutable-old-bottom/fresh-survivor" base 2 8 True True (Just baseExpected)
  ,Fixture "shared-fresh/old-merge" sharing 2 8 True True Nothing
  ,Fixture "fixed-frontier/then-mutation" frontier 2 8 True True Nothing
  ,Fixture "ordinary-type-destination/rejection" nonGen 2 8 True False Nothing
  ,Fixture "rigid-old-bottom/rejection" (A.replace 9 (A.node T.GBot 8 T.Rigid) base)
     2 8 True False Nothing
  ,Fixture "protected-old-bottom/rejection" (A.replace 8 (A.node (T.GArr 9 10) 7 T.Rigid) base)
     2 8 True False Nothing
  ,Fixture "kind-mismatch/rejection" kindMismatch 2 8 False False Nothing
  ,Fixture "sharing-cycle/rejection" cyclic 2 8 True False Nothing
  ,Fixture "nonzero-dense-offset" (A.rename (+100) base) 102 108 True True Nothing
  ,Fixture "negative-Integer-identities" (A.rename (subtract 100) base) (-98) (-92) True True Nothing
  ,Fixture "beyond-machine-Integer-identities" (A.rename (+1000000000000000000000000000000) base)
     1000000000000000000000000000002 1000000000000000000000000000008 True True Nothing
  ,Fixture "canonical-alias-target" (T.Graph (FG.nodes base) (IM.fromList [(30,8),(31,30),(32,2)]) 33)
     32 31 True True Nothing
  ]

-- Fixed non-admitted branches ensure the complete original graft/fallback
-- path remains available. These are not C3 optimizations.
closed :: T.Graph
closed = A.replace 4 (node T.GBot 2)
  (A.replace 5 (node T.GBot 2) (A.without [6] base))

payloadBarrier :: T.Graph
payloadBarrier = A.replace 4 (node (T.GCon "Int" []) 3)
  (A.replace 5 (node (T.GArr 6 6) 3)
  (A.replace 6 (node T.GBot 5)
  (A.replace 9 (node (T.GCon "Int" []) 8) base)))

identityFrontier :: T.Graph
identityFrontier = A.replace 2 (node (T.GGen 8) 0)
  (A.replace 8 (node (T.GArr 9 10) 0)
  (A.replace 9 (node T.GBot 8)
  (A.replace 10 (node (T.GCon "Int" []) 8) (A.without [3,4,5,6] A.poly))))

typeApplication :: T.Graph
typeApplication = A.replace 3 (node (T.GTyApp 4 5) 2)
  (A.replace 4 (node (T.GTyApp 6 11) 3)
  (A.replace 6 (node (T.GTyCon "K" (T.KArrow T.Star (T.KArrow T.Star T.Star))) 4)
  (A.replace 11 (node T.GBot 4)
  (A.replace 8 (node (T.GTyApp 9 10) 7)
  (A.replace 9 (node (T.GBotK (T.KArrow T.Star T.Star)) 8) base)))))

unchangedSurvivor, unchangedSurvivorExpected :: T.Graph
unchangedSurvivor = A.replace 6 (node (T.GArr 11 11) 4)
  (A.replace 11 (node T.GBot 6) base)
unchangedSurvivorExpected = T.Graph
  (IM.insert 16 (node T.GBot 15)
  (IM.insert 15 (node (T.GArr 16 16) 9)
  (IM.insert 9 (node (T.GArr 15 15) 8) (FG.nodes unchangedSurvivor))))
  (IM.fromList [(12,8),(13,9),(14,10)]) 17

additionalFixtures :: [Fixture]
additionalFixtures =
  [Fixture "nonadmitted-congruent-success" closed 2 8 False True Nothing
  ,Fixture "nonadmitted-payload-then-mutation" payloadBarrier 2 8 False True Nothing
  ,Fixture "nonadmitted-bottom-target" A.poly 2 8 False True Nothing
  ,Fixture "nonadmitted-frontier-identity" identityFrontier 2 8 False True Nothing
  ,Fixture "TyApp-kind-correct-mutation" typeApplication 2 8 True True Nothing
  ,Fixture "unchanged-surviving-grandchild" unchangedSurvivor 2 8 True True (Just unchangedSurvivorExpected)
  ]

renameFixture :: String -> (Integer -> Integer) -> Fixture -> Fixture
renameFixture prefix image (Fixture label g a b admitted success _) =
  Fixture (prefix ++ "/" ++ label) (A.rename image g) (image a) (image b) admitted success Nothing

renamedFixtures :: [Fixture]
renamedFixtures =
  [renameFixture name image f
  |(name,image) <- [("sparse",\n -> 100003*n-9001),("huge-negative",subtract (10^40))]
  ,f <- [fixtures !! 0,fixtures !! 1,fixtures !! 2,fixtures !! 3,fixtures !! 4]]

