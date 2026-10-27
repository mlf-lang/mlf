-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Benchmark where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as M;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  import qualified Package.Verification as V;
  import qualified Package.Build as Build;
  import qualified Bootstrap.Std as SharedSyntax;
  -- Untimed mathematical and sequence oracles. Measured programs cannot read them.
  power :: Int -> Int -> Int;
  power base n =
    if (n == 0)
    then 1
    else if (remInt n 2 == 0)
         then let {
                half = power base (quotInt n 2)
              } in
              (half * half)
         else (base * power base (n - 1));
  atan :: Int -> Int -> Int -> Int -> Int -> Int;
  atan square value total odd sign =
    if (value == 0)
    then total
    else atan square (quotInt value square) (total + (sign * quotInt value odd)) (odd + 2)
           (0 - sign);
  piDigits :: Int -> String;
  piDigits size =
    let {
      scale = power 10 (size + 30)
    } in
    stringSlice
      (showInt
         ((16 * atan 25 (quotInt scale 5) 0 1 1) - (4 * atan 57121 (quotInt scale 239) 0 1 1)))
      0
      size;
  pidigits :: Int -> String;
  pidigits size =
    let {
      digits = piDigits size
    } in
    S.intercalate "\n"
      (S.map
         (\i ->
            let {
              part = stringSlice digits i (S.min 10 (size - i))
            } in
            (part ++
             (S.concatStrings (S.replicate (10 - stringLength part) " ") ++
              ("\t:" ++ showInt (S.min (i + 10) size)))))
         (S.filter (\i -> (remInt i 10 == 0)) (S.range 0 (size - 1))));
  binaryTrees :: Int -> String;
  binaryTrees size =
    let {
      maximum = S.max 6 size
    } in
    S.intercalate "\n"
      ((:)
         ("stretch tree of depth " ++
          (showInt (maximum + 1) ++ (" check: " ++ showInt (power 2 (maximum + 2) - 1))))
         (S.snoc
            (S.map
               (\depth ->
                  let {
                    n = power 2 ((maximum - depth) + 4)
                  } in
                  (showInt n ++
                   (" trees of depth " ++
                    (showInt depth ++ (" check: " ++ showInt (n * (power 2 (depth + 1) - 1)))))))
               (S.filter (\depth -> (remInt depth 2 == 0)) (S.range 4 maximum)))
            ("long lived tree of depth " ++
             (showInt maximum ++ (" check: " ++ showInt (power 2 (maximum + 1) - 1))))));
  factorial :: Int -> Int;
  factorial n = S.product (S.range 1 n);
  unrank :: Int -> Int -> [] Int -> [] Int;
  unrank n remaining permutation =
    if (n <= 0)
    then permutation
    else let {
           rotation = quotInt remaining (factorial n)
         } in
         let {
           front = S.take (n + 1) permutation
         } in
         unrank (n - 1) (remInt remaining (factorial n))
           (S.append (S.append (S.drop rotation front) (S.take rotation front))
              (S.drop (n + 1) permutation));
  flips :: [] Int -> Int -> Int;
  flips permutation count =
    let {
      end = S.head permutation
    } in
    if (end == 1)
    then count
    else flips (S.append (S.reverse (S.take end permutation)) (S.drop end permutation)) (count + 1);
  fannkuch :: Int -> (,) Int Int;
  fannkuch size =
    S.foldl
      (\((,) checksum maximum) rank ->
         let {
           count = flips (unrank (size - 1) rank (S.range 1 size)) 0
         } in
         (,) (checksum + (if (remInt rank 2 == 0) then count else (0 - count)))
           (S.max maximum count))
      ((,) 0 0)
      (S.range 0 (factorial size - 1));
  wrap :: Int -> String -> String;
  wrap width text =
    if (stringLength text == 0)
    then ""
    else let {
           n = S.min width (stringLength text)
         } in
         (stringSlice text 0 n ++ ("\n" ++ wrap width (O.drop n text)));
  alu :: String;
  alu =
    "GGCCGGGCGCGGTGGCTCACGCCTGTAATCCCAGCACTTTGGGAGGCCGAGGCGGGCGGATCACCTGAGGTCAGGAGTTCGAGACCAGCCTGGCCAACATGGTGAAACCCCGTCTCTACTAAAAATACAAAAATTAGCCGGGCGTGGTGGCGCGCGCCTGTAATCCCAGCTACTCGGGAGGCTGAGGCAGGAGAATCGCTTGAACCCGGGAGGCGGAGGTTGCAGTGAGCCGAGATCGCGCCACTGCACTCCAGCCTGGGCGACAGAGCGAGACTCCGTCTCAAAAA";
  iubBounds = (:) 27 ((:) 39 ((:) 51 ((:) 78 (S.map (\n -> (78 + (2 * n))) (S.range 1 11)))));
  humanBounds :: [] Int;
  humanBounds =
    (:) 3029549426680 ((:) 5009432431601 ((:) 6984905497992 ((:) 10000000000000 [])));
  choose :: String -> Int -> Int -> [] Int -> Int -> String;
  choose letters scale seed bounds index =
    case bounds of {
      (:) bound rest ->
        if ((seed * scale) < (bound * 139968))
        then O.char letters index
        else choose letters scale seed rest (index + 1);
      [] -> panic "RNG probability bounds exhausted"
    };
  randomSequence :: Int -> Int -> String -> Int -> [] Int -> (,) String Int;
  randomSequence count seed letters scale bounds =
    if (count == 0)
    then (,) "" seed
    else let {
           next = remInt ((seed * 3877) + 29573) 139968
         } in
         case randomSequence (count - 1) next letters scale bounds of {
           (,) suffix final -> (,) (choose letters scale next bounds 0 ++ suffix) final
         };
  fasta :: Int -> String;
  fasta size =
    let {
      first =
        S.concatStrings
          (S.map (\i -> O.char alu (remInt i (stringLength alu))) (S.range 0 ((2 * size) - 1)))
    } in
    case randomSequence (3 * size) 42 "acgtBDHKMNRSVWY" 100 iubBounds of {
      (,) second seed ->
        case randomSequence (5 * size) seed "acgt" 10000000000000 humanBounds of {
          (,) third final ->
            (">ONE Homo sapiens alu\n" ++
             (wrap 60 first ++
              (">TWO IUB ambiguity codes\n" ++
               (wrap 60 second ++ (">THREE Homo sapiens frequency\n" ++ wrap 60 third)))))
        }
    };
  records :: String -> [] ((,) String String);
  records text = parseRecords "" "" [] (O.lines text);
  parseRecords :: String ->
                  String -> [] ((,) String String) -> [] String -> [] ((,) String String);
  parseRecords header sequence done lines =
    case lines of {
      [] -> S.reverse (if eqString header "" then done else (:) ((,) header sequence) done);
      (:) line rest ->
        if O.starts ">" line
        then parseRecords line ""
               (if eqString header "" then done else (:) ((,) header sequence) done)
               rest
        else parseRecords header (sequence ++ line) done rest
    };
  upper :: String -> String;
  upper text =
    S.concatStrings
      (S.map
         (\i ->
            let {
              code = stringCodeAt text i
            } in
            stringFromCode (if ((code >= 97) && (code <= 122)) then (code - 32) else code))
         (S.range 0 (stringLength text - 1)));
  complement :: Int -> String;
  complement code =
    let {
      from = "ACGTUMRWSYKVHDBN"
    } in
    let {
      to = "TGCAAKYWSRMBDHVN"
    } in
    let {
      c = if ((code >= 97) && (code <= 122)) then (code - 32) else code
    } in
    case S.find (\i -> (stringCodeAt from i == c)) (S.range 0 (stringLength from - 1)) of {
      Just i -> stringFromCode (stringCodeAt to i);
      Nothing -> stringFromCode code
    };
  reverseComplement :: String -> String;
  reverseComplement text =
    S.concatStrings
      (S.map
         (\((,) header sequence) ->
            (header ++
             ("\n" ++
              wrap 60
                (S.concatStrings
                   (S.map (\i -> complement (stringCodeAt sequence i))
                      (S.reverse (S.range 0 (stringLength sequence - 1))))))))
         (records text));
  queries = O.words "GGT GGTA GGTATT GGTATTTTAATT GGTATTTTAATTTATAGT";
  windows :: Int -> String -> [] String;
  windows width sequence =
    S.map (\i -> stringSlice sequence i width) (S.range 0 (stringLength sequence - width));
  counts :: Int -> String -> Map String Int;
  counts width sequence =
    M.fromListWith compareString addInt (S.map (\key -> (,) key 1) (windows width sequence));
  percent :: String -> Int -> Int -> [] String;
  percent key value total =
    let {
      lower = quotInt (100000 * value) total
    } in
    let {
      remainder = remInt (100000 * value) total
    } in
    let {
      nearest =
        (lower +
         (if (((2 * remainder) > total) || (((2 * remainder) == total) && (remInt lower 2 == 1)))
          then 1
          else 0))
    } in
    let {
      options =
        if ((2 * remainder) == total)
        then (:) nearest ((:) (if (nearest == lower) then (lower + 1) else lower) [])
        else (:) nearest []
    } in
    S.map
      (\n ->
         let {
           fraction = showInt (remInt n 1000)
         } in
         (key ++
          (" " ++
           (showInt (quotInt n 1000) ++
            ("." ++
             (S.concatStrings (S.replicate (3 - stringLength fraction) "0") ++
              (fraction ++ "\n")))))))
      options;
  nucleotideLines :: String -> [] ([] String);
  nucleotideLines text =
    let {
      sequence =
        upper
          (S.maybe "" S.snd
             (S.find (\((,) header _) -> eqString (S.head (O.words header)) ">THREE")
                (records text)))
    } in
    S.concatMap
      (\width ->
         let {
           table = counts width sequence
         } in
         if (width <= 2)
         then let {
                total = S.sum (M.elems table)
              } in
              let {
                sorted =
                  S.sortBy
                    (\((,) a x) ((,) b y) ->
                       if (x > y) then (-1) else if (x < y) then 1 else compareString a b)
                    (M.toList table)
              } in
              S.snoc (S.map (\((,) key value) -> percent key value total) sorted) ((:) "\n" [])
         else let {
                key =
                  S.fromMaybe (panic "missing nucleotide query")
                    (S.find (\q -> (stringLength q == width)) queries)
              } in
              (:)
                ((:)
                   (showInt (S.fromMaybe 0 (M.lookup compareString key table)) ++
                    ("\t" ++ (key ++ "\n")))
                   [])
                [])
      ((:) 1 ((:) 2 ((:) 3 ((:) 4 ((:) 6 ((:) 12 ((:) 18 [])))))));
  nucleotideCounts :: String -> String;
  nucleotideCounts text = S.concatStrings (S.map S.head (nucleotideLines text));
  -- Independent regex-redux oracle: direct fixed-width DNA comparisons and
  -- literal/delimiter scans. No regular-expression parser or matcher is shared
  -- with the measured implementation, including the five sequential rewrites.
  regexPatterns =
    O.words
      "agggtaaa|tttaccct [cgt]gggtaaa|tttaccc[acg] a[act]ggtaaa|tttacc[agt]t ag[act]gtaaa|tttac[agt]ct agg[act]taaa|ttta[agt]cct aggg[acg]aaa|ttt[cgt]ccct agggt[cgt]aa|tt[acg]accct agggta[cgt]a|t[acg]taccct agggtaa[cgt]|[acg]ttaccct";
  regexFindCode :: Int -> String -> Int -> Int;
  regexFindCode code text i =
    if (i >= stringLength text)
    then (-1)
    else if (stringCodeAt text i == code) then i else regexFindCode code text (i + 1);
  regexClean :: String -> String;
  regexClean text = S.concatStrings (regexCleanAt text 0);
  regexCleanAt :: String -> Int -> [] String;
  regexCleanAt text i =
    if (i >= stringLength text)
    then []
    else let {
           code = stringCodeAt text i
         } in
         if (code == 10)
         then regexCleanAt text (i + 1)
         else if (code == 62)
              then let {
                     end = regexFindCode 10 text (i + 1)
                   } in
                   if (end < 0) then (:) (O.drop i text) [] else regexCleanAt text (end + 1)
              else (:) (O.char text i) (regexCleanAt text (i + 1));
  regexMer :: Int -> Bool -> String -> Int -> Bool;
  regexMer variant forward text offset =
    let {
      literal = if forward then "agggtaaa" else "tttaccct"
    } in
    let {
      changed = if forward then (variant - 1) else (8 - variant)
    } in
    let {
      letters =
        if ((variant == 1) || (variant >= 6))
        then if forward then "cgt" else "acg"
        else if (variant <= 4)
             then if forward then "act" else "agt"
             else if forward then "acg" else "cgt"
    } in
    S.all
      (\position ->
         let {
           code = stringCodeAt text (offset + position)
         } in
         if ((variant > 0) && (position == changed))
         then (regexFindCode code letters 0 >= 0)
         else (code == stringCodeAt literal position))
      (S.range 0 7);
  regexCount :: Int -> String -> Int;
  regexCount variant text = regexCountAt variant text 0 0;
  regexCountAt :: Int -> String -> Int -> Int -> Int;
  regexCountAt variant text i count =
    seq count
      (if ((i + 8) > stringLength text)
       then count
       else if (regexMer variant True text i || regexMer variant False text i)
            then regexCountAt variant text (i + 8) (count + 1)
            else regexCountAt variant text (i + 1) count);
  regexReplaceWords :: [] String -> String -> String -> String;
  regexReplaceWords words replacement text =
    S.concatStrings (regexWordsAt words replacement text 0);
  regexWordsAt :: [] String -> String -> String -> Int -> [] String;
  regexWordsAt words replacement text i =
    if (i >= stringLength text)
    then []
    else case S.find
                (\word ->
                   (((i + stringLength word) <= stringLength text) &&
                    eqString word (stringSlice text i (stringLength word))))
                words of {
           Just word ->
             (:) replacement (regexWordsAt words replacement text (i + stringLength word));
           Nothing -> (:) (O.char text i) (regexWordsAt words replacement text (i + 1))
         };
  regexReplaceDelimited :: Int -> Int -> Int -> String -> String -> String;
  regexReplaceDelimited open close minimum replacement text =
    S.concatStrings (regexDelimitedAt open close minimum replacement text 0);
  regexDelimitedAt :: Int -> Int -> Int -> String -> String -> Int -> [] String;
  regexDelimitedAt open close minimum replacement text i =
    if (i >= stringLength text)
    then []
    else let {
           end = if (stringCodeAt text i == open) then regexFindCode close text (i + 1) else (-1)
         } in
         if (end >= ((i + 1) + minimum))
         then (:) replacement (regexDelimitedAt open close minimum replacement text (end + 1))
         else (:) (O.char text i) (regexDelimitedAt open close minimum replacement text (i + 1));
  regexSubstitute :: String -> String;
  regexSubstitute text =
    let {
      first = regexReplaceWords (O.words "tHaN tHat") "<4>" text
    } in
    let {
      second = regexReplaceWords (O.words "aND caN HaD HaS WaS") "<3>" first
    } in
    let {
      third = regexReplaceWords (O.words "aN aS at BY") "<2>" second
    } in
    regexReplaceDelimited 124 124 1 "-" (regexReplaceDelimited 60 62 0 "|" third);
  regexRedux :: String -> String;
  regexRedux text =
    let {
      sequence = regexClean text
    } in
    (S.concatStrings
       (S.zipWith
          (\pattern variant ->
             (pattern ++ (" " ++ (showInt (regexCount variant sequence) ++ "\n"))))
          regexPatterns
          (S.range 0 8)) ++
     ("\n" ++
      (showInt (stringLength text) ++
       ("\n" ++
        (showInt (stringLength sequence) ++
         ("\n" ++ (showInt (stringLength (regexSubstitute sequence)) ++ "\n")))))));
  -- Scalar pair state, unlike the measured mutable-array n-body implementation.
  data Vector = Vector Double Double Double;
  data Body = Body Vector Vector Double;
  add :: Vector -> Vector -> Vector;
  add (Vector a b c) (Vector x y z) = Vector (addDouble a x) (addDouble b y) (addDouble c z);
  sub :: Vector -> Vector -> Vector;
  sub (Vector a b c) (Vector x y z) = Vector (subDouble a x) (subDouble b y) (subDouble c z);
  scale :: Double -> Vector -> Vector;
  scale n (Vector x y z) = Vector (mulDouble n x) (mulDouble n y) (mulDouble n z);
  dot :: Vector -> Vector -> Double;
  dot (Vector a b c) (Vector x y z) =
    addDouble (addDouble (mulDouble a x) (mulDouble b y)) (mulDouble c z);
  position :: Body -> Vector;
  position (Body p _ _) = p;
  velocity :: Body -> Vector;
  velocity (Body _ v _) = v;
  mass :: Body -> Double;
  mass (Body _ _ m) = m;
  sumDouble :: [] Double -> Double;
  sumDouble xs = S.foldl addDouble 0.0 xs;
  solar = mulDouble 4.0 (mulDouble 3.141592653589793 3.141592653589793);
  body :: Double -> Double -> Double -> Double -> Double -> Double -> Double -> Body;
  body x y z vx vy vz m = Body (Vector x y z) (scale 365.24 (Vector vx vy vz)) (mulDouble m solar);
  initialBodies =
    let {
      bodies =
        (:) (Body (Vector 0.0 0.0 0.0) (Vector 0.0 0.0 0.0) solar)
          ((:)
             (body 4.84143144246472090 (SharedSyntax.negateDouble 1.16032004402742839)
                (SharedSyntax.negateDouble 0.103622044471123109)
                0.00166007664274403694
                0.00769901118419740425
                (SharedSyntax.negateDouble 0.0000690460016972063023)
                0.000954791938424326609)
             ((:)
                (body 8.34336671824457987 4.12479856412430479
                   (SharedSyntax.negateDouble 0.403523417114321381)
                   (SharedSyntax.negateDouble 0.00276742510726862411)
                   0.00499852801234917238
                   0.0000230417297573763929
                   0.000285885980666130812)
                ((:)
                   (body 12.8943695621391310 (SharedSyntax.negateDouble 15.1111514016986312)
                      (SharedSyntax.negateDouble 0.223307578892655734)
                      0.00296460137564761618
                      0.00237847173959480950
                      (SharedSyntax.negateDouble 0.0000296589568540237556)
                      0.0000436624404335156298)
                   ((:)
                      (body 15.3796971148509165 (SharedSyntax.negateDouble 25.9193146099879641)
                         0.179258772950371181
                         0.00268067772490389322
                         0.00162824170038242295
                         (SharedSyntax.negateDouble 0.0000951592254519715870)
                         0.0000515138902046611451)
                      []))))
    } in
    let {
      momentum = S.foldl (\v b -> add v (scale (mass b) (velocity b))) (Vector 0.0 0.0 0.0) bodies
    } in
    (:)
      (Body (Vector 0.0 0.0 0.0) (scale (divDouble (SharedSyntax.negateDouble 1.0) solar) momentum)
         solar)
      (S.tail bodies);
  pairs :: Int -> [] ((,) Int Int);
  pairs size =
    S.concatMap (\i -> S.map ((,) i) (S.range (i + 1) (size - 1))) (S.range 0 (size - 1));
  energy :: [] Body -> Double;
  energy bodies =
    subDouble
      (sumDouble
         (S.map (\b -> mulDouble (mulDouble 0.5 (mass b)) (dot (velocity b) (velocity b))) bodies))
      (sumDouble
         (S.map
            (\((,) i j) ->
               let {
                 a = S.index bodies i
               } in
               let {
                 b = S.index bodies j
               } in
               let {
                 d = sub (position a) (position b)
               } in
               divDouble (mulDouble (mass a) (mass b)) (sqrtDouble (dot d d)))
            (pairs (S.length bodies))));
  replaceAt :: forall a. Int -> a -> [] a -> [] a;
  replaceAt n value xs =
    case xs of {
      [] -> panic "oracle array index";
      (:) x rest -> if (n == 0) then (:) value rest else (:) x (replaceAt (n - 1) value rest)
    };
  advancePair :: [] Body -> (,) Int Int -> [] Body;
  advancePair bodies ((,) i j) =
    let {
      a = S.index bodies i
    } in
    let {
      b = S.index bodies j
    } in
    let {
      delta = sub (position a) (position b)
    } in
    let {
      distance = sqrtDouble (dot delta delta)
    } in
    let {
      magnitude = divDouble 0.01 (mulDouble distance (mulDouble distance distance))
    } in
    let {
      first =
        Body (position a) (sub (velocity a) (scale (mulDouble (mass b) magnitude) delta)) (mass a)
    } in
    let {
      second =
        Body (position b) (add (velocity b) (scale (mulDouble (mass a) magnitude) delta)) (mass b)
    } in
    replaceAt j second (replaceAt i first bodies);
  advance :: Int -> [] Body -> [] Body;
  advance n bodies =
    if (n == 0)
    then bodies
    else let {
           changed = S.foldl advancePair bodies (pairs (S.length bodies))
         } in
         advance (n - 1)
           (S.map (\b -> Body (add (position b) (scale 0.01 (velocity b))) (velocity b) (mass b))
              changed);
  nbodyEnergy :: Int -> (,) Double Double;
  nbodyEnergy steps = (,) (energy initialBodies) (energy (advance steps initialBodies));
  accurateSum :: [] Double -> Double;
  accurateSum values =
    S.fst
      (S.foldl
         (\((,) sum correction) x ->
            let {
              y = subDouble x correction
            } in
            let {
              next = addDouble sum y
            } in
            (,) next (subDouble (subDouble next sum) y))
         ((,) 0.0 0.0)
         values);
  multiply :: [] ([] Double) -> [] Double -> Bool -> [] Double;
  multiply matrix vector transpose =
    S.map
      (\i ->
         accurateSum
           (S.map
              (\j ->
                 mulDouble
                   (S.index (S.index matrix (if transpose then j else i))
                      (if transpose then i else j))
                   (S.index vector j))
              (S.range 0 (S.length vector - 1))))
      (S.range 0 (S.length vector - 1));
  normLoop :: Int -> [] ([] Double) -> [] Double -> [] Double -> Double;
  normLoop n matrix u v =
    if (n == 0)
    then sqrtDouble
           (divDouble (accurateSum (S.zipWith mulDouble u v))
              (accurateSum (S.map (\x -> mulDouble x x) v)))
    else normLoop (n - 1) matrix (multiply matrix (multiply matrix u False) True) u;
  spectralNorm :: Int -> Double;
  spectralNorm size =
    let {
      matrix =
        S.map
          (\i ->
             S.map
               (\j -> divDouble 1.0 (intToDouble ((quotInt ((i + j) * ((i + j) + 1)) 2 + i) + 1)))
               (S.range 0 (size - 1)))
          (S.range 0 (size - 1))
    } in
    normLoop 20 matrix (S.replicate size 1.0) (S.replicate size 1.0);
  pixel :: Int -> Double -> Double -> Double -> Double -> Bool;
  pixel remaining cr ci zr zi =
    if (remaining == 0)
    then True
    else let {
           real = addDouble (subDouble (mulDouble zr zr) (mulDouble zi zi)) cr
         } in
         let {
           imaginary = addDouble (mulDouble 2.0 (mulDouble zr zi)) ci
         } in
         if ltDouble 4.0 (addDouble (mulDouble real real) (mulDouble imaginary imaginary))
         then False
         else pixel (remaining - 1) cr ci real imaginary;
  mandelbrot :: Int -> [] Int;
  mandelbrot size =
    let {
      stride = quotInt (size + 7) 8
    } in
    S.concatMap
      (\y ->
         S.map
           (\byte ->
              S.sum
                (S.map
                   (\bit ->
                      let {
                        x = ((byte * 8) + bit)
                      } in
                      if ((x < size) &&
                          pixel 50
                            (subDouble
                               (divDouble (mulDouble 2.0 (intToDouble x)) (intToDouble size))
                               1.5)
                            (subDouble
                               (divDouble (mulDouble 2.0 (intToDouble y)) (intToDouble size))
                               1.0)
                            0.0
                            0.0)
                      then power 2 (7 - bit)
                      else 0)
                   (S.range 0 7)))
           (S.range 0 (stride - 1)))
      (S.range 0 (size - 1));
  textBytes :: String -> [] Int;
  textBytes text =
    S.concatMap
      (\i ->
         let {
           c = stringCodeAt text i
         } in
         if (c < 128) then (:) c [] else panic "benchmark oracle expects ASCII")
      (S.range 0 (stringLength text - 1));
  expectedOutput :: String -> Int -> [] Int;
  expectedOutput name size =
    if eqString name "mandelbrot"
    then S.append (textBytes ("P4\n" ++ (showInt size ++ (" " ++ (showInt size ++ "\n")))))
           (mandelbrot size)
    else textBytes
           (if eqString name "binary-trees"
            then binaryTrees size
            else if eqString name "pidigits"
                 then pidigits size
                 else if eqString name "fasta"
                      then fasta size
                      else if eqString name "reverse-complement"
                           then reverseComplement (fasta size)
                           else if eqString name "k-nucleotide"
                                then nucleotideCounts (fasta size)
                                else if eqString name "regex-redux"
                                     then regexRedux (fasta size)
                                     else if eqString name "n-body"
                                          then case nbodyEnergy size of {
                                                 (,) a b ->
                                                   (formatDouble 9 a ++ ("\n" ++ formatDouble 9 b))
                                               }
                                          else if eqString name "spectral-norm"
                                               then formatDouble 9 (spectralNorm size)
                                               else if eqString name "fannkuch-redux"
                                                    then case fannkuch size of {
                                                           (,) a b ->
                                                             (showInt a ++
                                                              ("\nPfannkuchen(" ++
                                                               (showInt size ++
                                                                (") = " ++ showInt b))))
                                                         }
                                                    else panic "unknown correctness oracle");
  validateOutput :: String -> Int -> [] Int -> Bool;
  validateOutput name size output =
    if (eqString name "n-body" || eqString name "spectral-norm")
    then let {
           reference =
             if eqString name "n-body"
             then case nbodyEnergy size of {
                    (,) a b -> (:) a ((:) b [])
                  }
             else (:) (spectralNorm size) []
         } in
         let {
           actual =
             S.map (\token -> V.number (J.Number token))
               (O.words (S.concatStrings (S.map stringFromCode output)))
         } in
         ((S.length actual == S.length reference) &&
          (S.all S.isJust actual &&
           S.all
             (\((,) a b) ->
                (V.finite a &&
                 S.not
                   (ltDouble 0.00000001 (if ltDouble a b then subDouble b a else subDouble a b))))
             (S.zip (S.catMaybes actual) reference)))
    else if eqString name "k-nucleotide"
         then validateNucleotide (nucleotideLines (fasta size))
                (S.concatStrings (S.map stringFromCode output))
         else if S.elem eqString name (O.words "fasta mandelbrot reverse-complement regex-redux")
              then S.eqList eqInt output (expectedOutput name size)
              else S.eqList eqString (O.words (S.concatStrings (S.map stringFromCode output)))
                     (O.words (S.concatStrings (S.map stringFromCode (expectedOutput name size))));
  validateNucleotide :: [] ([] String) -> String -> Bool;
  validateNucleotide allowed text =
    let {
      actual = O.lines text
    } in
    let {
      complete = if O.ends "\n" text then S.init actual else actual
    } in
    (O.ends "\n" text &&
     ((S.length complete == S.length allowed) &&
      S.all (\((,) line options) -> S.elem eqString (line ++ "\n") options)
        (S.zip complete allowed)));
  performanceChecks :: [] J.Json -> J.Json -> [] J.Json;
  performanceChecks rows targets =
    S.concatMap
      (\row ->
         S.map
           (\dimension ->
              let {
                entries = J.get "languages" row
              } in
              let {
                ratio =
                  divDouble
                    (V.double 0.0
                       (J.get "median_wall_seconds" (J.get dimension (J.get "mlf" entries))))
                    (V.double 0.0
                       (J.get "median_wall_seconds" (J.get dimension (J.get "c" entries))))
              } in
              let {
                maximum = V.double 0.0 (J.get dimension targets)
              } in
              J.Object
                ((:) ((,) "benchmark" (J.get "benchmark" row))
                   ((:) ((,) "dimension" (J.str dimension))
                      ((:) ((,) "maximum_ratio" (J.Number (formatDouble 12 maximum)))
                         ((:) ((,) "mlf_over_c" (J.Number (formatDouble 12 ratio)))
                            ((:)
                               ((,) "passed"
                                  (J.Boolean (V.positive ratio && S.not (ltDouble maximum ratio))))
                               []))))))
           (S.map S.fst (J.items targets)))
      rows;
  validateLimits :: J.Json -> Bool;
  validateLimits targets =
    S.all (\entry -> S.maybe False V.positive (V.number (S.snd entry))) (J.items targets);
  measure :: String -> [] String -> String -> Int -> IO (Either String J.Json);
  measure directory argv input timeout =
    do {
      host <- getEnv "MLF_TEST_HOST_SUPPORT";
      O.require (stringLength host > 0) "missing native measurement transport";
      let {
        stdout = (directory ++ "/stdout")
      };
      let {
        stderr = (directory ++ "/stderr")
      };
      let {
        sample = (directory ++ "/sample.json")
      };
      code <-
        O.exec directory
          (S.append
             ((:) host
                ((:) "measure"
                   ((:) (showInt timeout) ((:) input ((:) stdout ((:) stderr []))))))
             argv)
          ""
          sample
          (sample ++ ".err")
          (timeout + 5);
      if S.not (code == 0)
      then return (Left "measurement interrupted")
      else do {
             value <- J.read sample;
             let {
               status = V.int "exit_code" value
             };
             return
               (if ((status == 0) &&
                    S.maybe False V.positive (V.number (J.get "wall_seconds" value)))
                then Right value
                else Left ("measured command failed (" ++ (showInt status ++ ")")))
           }
    };
  -- Resolve the manifest's explicitly pinned native dependency before measuring.
  -- Save the .pc file, tool, headers and linked library identity with the flags.
  benchmarkPackage :: String -> String -> String -> [] String -> IO J.Json;
  -- pkg-config suppresses system -I paths. Explicit public headers still bind
  -- those installations without recursively hashing all of /usr/include.
  benchmarkPackage directory name expected headers =
    do {
      O.mkdir directory;
      tool <- Build.tool "pkg-config";
      let {
        command = V.text "path" tool
      };
      version <- Build.raw directory ((:) command ((:) "--modversion" ((:) name [])));
      O.require ((stringLength expected > 0) && eqString (O.trim version) expected)
        ("benchmark library version differs: " ++
         (name ++ ("; expected " ++ (expected ++ (", found " ++ O.trim version)))));
      text <- Build.raw directory ((:) command ((:) "--cflags" ((:) "--libs" ((:) name []))));
      libdir <- Build.raw directory ((:) command ((:) "--variable=libdir" ((:) name [])));
      pcdir <- Build.raw directory ((:) command ((:) "--variable=pcfiledir" ((:) name [])));
      includedir <-
        Build.raw directory ((:) command ((:) "--variable=includedir" ((:) name [])));
      O.require (S.not (S.null headers) && (stringLength (O.trim includedir) > 0))
        ("benchmark library headers missing: " ++ name);
      let {
        selected =
          S.append (if eqString (O.trim libdir) "" then [] else (:) ("-L" ++ O.trim libdir) [])
            (Build.flags text)
      };
      identity <- Build.flagIdentity selected;
      requiredHeaders <-
        Build.hashFiles (S.map (\header -> (O.trim includedir ++ ("/" ++ header))) headers);
      let {
        completeHeaders =
          S.foldlStrict (\result entry -> J.set (S.fst entry) (S.snd entry) result)
            (J.get "headers" identity)
            (J.items requiredHeaders)
      };
      let {
        complete = J.set "headers" completeHeaders identity
      };
      let {
        definition = (O.trim pcdir ++ ("/" ++ (name ++ ".pc")))
      };
      hash <- fileDigest definition;
      return
        (J.set "package" (J.str name)
           (J.set "version" (J.str (O.trim version))
              (J.set "pkg_config" tool
                 (J.set "definition" (Build.obj1 definition (J.str hash)) complete))))
    };
  benchmarkPackageFiles :: J.Json -> [] String;
  benchmarkPackageFiles identity =
    (:) (V.text "path" (J.get "pkg_config" identity))
      (S.map S.fst
         (S.concatMap (\key -> J.items (J.get key identity))
            (O.words "headers libraries definition")));
  collectorFlags :: String -> IO ([] String);
  collectorFlags directory =
    do {
      prefix <- getEnv "MLF_GC_PREFIX";
      if eqString prefix ""
      then do {
             code <-
               O.exec "" (O.words "pkg-config --cflags --libs bdw-gc") "" (directory ++ "/gc.flags")
                 (directory ++ "/gc.err")
                 60;
             O.require (code == 0) "BDWGC discovery failed";
             text <- readFile (directory ++ "/gc.flags");
             return (Build.flags text)
           }
      else do {
             actual <- canonicalPath prefix;
             windows <- O.isWindows;
             code <-
               O.exec "" (O.words "uname -s") "" (directory ++ "/gc.system")
                 (directory ++ "/gc.system.err")
                 60;
             O.require (code == 0) "collector platform discovery failed";
             system <- readFile (directory ++ "/gc.system");
             return
               ((:) ("-I" ++ (actual ++ "/include"))
                  ((:) (actual ++ (if windows then "/lib/libgc.dll.a" else "/lib/libgc.a"))
                     (if eqString (O.trim system) "Linux" then (:) "-ldl" [] else [])))
           }
    };
  buildNative :: String -> String -> String -> String -> String -> Int -> IO (Either String ());
  buildNative directory compiler clang source binary timeout =
    do {
      O.mkdir directory;
      let {
        ir = (directory ++ "/program.ll")
      };
      emitted <-
        O.exec "" ((:) compiler ((:) "--emit-llvm-gc" ((:) source []))) "" ir
          (directory ++ "/emit.err")
          timeout;
      if S.not (emitted == 0)
      then return (Left "LLVM emission failed")
      else do {
             code <-
               O.exec "" ((:) compiler ((:) "--llvm-runtime" [])) ""
                 (directory ++ "/runtime.path")
                 (directory ++ "/runtime.err")
                 timeout;
             if S.not (code == 0)
             then return (Left "runtime discovery failed")
             else do {
                    runtime <- readFile (directory ++ "/runtime.path");
                    code <-
                      O.exec "" (O.words "pkg-config --cflags --libs gmp") ""
                        (directory ++ "/gmp.flags")
                        (directory ++ "/gmp.err")
                        timeout;
                    if S.not (code == 0)
                    then return (Left "GMP discovery failed")
                    else do {
                           flags <- readFile (directory ++ "/gmp.flags");
                           gc <- collectorFlags directory;
                           let {
                             pending = (directory ++ "/pending-executable")
                           };
                           code <-
                             O.exec ""
                               (S.append
                                  ((:) clang
                                     ((:) "-O2"
                                        ((:) "-Wno-override-module"
                                           ((:) ir ((:) (O.trim runtime) [])))))
                                  (S.append (S.append (Build.flags flags) gc)
                                     ((:) "-lm" ((:) "-o" ((:) pending [])))))
                               ""
                               (directory ++ "/link.out")
                               (directory ++ "/link.err")
                               timeout;
                           if S.not (code == 0)
                           then return (Left "native link failed")
                           else do {
                                  O.move pending binary;
                                  return (Right ())
                                }
                         }
                  }
           }
    };
  checkIntegrity :: [] ((,) String String) -> IO (Either String ());
  checkIntegrity fingerprints =
    do {
      matches <-
        S.mapM
          (\((,) path hash) ->
             do {
               actual <- fileDigest path;
               return (eqString actual hash)
             })
          fingerprints;
      return (if S.all S.id matches then Right () else Left "sources changed during measurement")
    };
  validateConfiguration :: J.Json -> Either String ();
  validateConfiguration config =
    do {
      V.ensure
        (((V.int "runs" config > 0) &&
          ((V.int "timeout" config > 0) && S.not (J.has "size" config))) ||
         ((V.int "runs" config > 0) && ((V.int "timeout" config > 0) && (V.int "size" config > 0))))
        "invalid CLI inputs";
      V.ensure (validateLimits (J.get "maximum_mlf_c_ratios" config)) "invalid performance limits";
      V.ensure (V.sameKeys V.languages (J.get "languages" config))
        "all four languages are mandatory";
      V.ensure
        (S.not (J.getBool "compile_only" False config && J.getBool "runtime_only" False config))
        "incompatible benchmark modes";
      return ()
    };
  identifyNative :: String -> String -> IO (Either String ((,) String J.Json));
  identifyNative directory compiler =
    do {
      code <-
        O.exec "" ((:) compiler ((:) "--help" [])) "" (directory ++ "/help.out")
          (directory ++ "/help.err")
          60;
      if S.not (code == 0)
      then return (Left ("selected compiler exited " ++ showInt code))
      else do {
             help <- readFile (directory ++ "/help.out");
             code <-
               O.exec "" ((:) compiler ((:) "--llvm-runtime" [])) ""
                 (directory ++ "/runtime.out")
                 (directory ++ "/runtime.err")
                 60;
             if S.not (code == 0)
             then return (Left "selected compiler runtime discovery failed")
             else do {
                    runtime <- readFile (directory ++ "/runtime.out");
                    hash <- fileDigest compiler;
                    return
                      (Right
                         ((,) (O.trim runtime)
                            (J.Object
                               ((:) ((,) "path" (J.str compiler))
                                  ((:) ((,) "sha256" (J.str hash))
                                     ((:)
                                        ((,) "identification"
                                           (J.Object
                                              ((:)
                                                 ((,) "command"
                                                    (J.stringArray
                                                       ((:) compiler ((:) "--help" []))))
                                                 ((:) ((,) "stdout" (J.str (O.trim help))) []))))
                                        []))))))
                  }
           }
    };
  runGuarded :: String -> J.Json -> IO (Either String ()) -> IO (Either String ());
  -- Save a non-success before validation or any tool work; a signal cannot leave a stale pass.
  runGuarded reportPath configuration action =
    do {
      J.write reportPath (J.Object ((:) ((,) "status" (J.str "running")) []));
      manifest <- J.read "benchmarks/manifest.json";
      case validateSelection configuration manifest of {
        Left error ->
          do {
            J.write reportPath
              (J.Object
                 ((:) ((,) "status" (J.str "failed")) ((:) ((,) "error" (J.str error)) [])));
            return (Left error)
          };
        Right _ ->
          do {
            result <- action;
            J.write reportPath
              (J.Object
                 ((:) ((,) "status" (J.str (if S.isRight result then "passed" else "failed")))
                    []));
            return result
          }
      }
    };
  stdinMetadata :: String -> String -> Int -> String -> IO J.Json;
  stdinMetadata directory name size language =
    do {
      let {
        inputText =
          if S.elem eqString name (O.words "reverse-complement k-nucleotide regex-redux")
          then fasta size
          else (showInt size ++ "\n")
      };
      writeFile (directory ++ "/stdin") inputText;
      hash <- fileDigest (directory ++ "/stdin");
      return
        (J.Object
           ((:) ((,) "stdin_bytes" (J.num (stringLength inputText)))
              ((:) ((,) "stdin_sha256" (J.str hash)) [])))
    };
  runGroup :: String ->
              Double -> [] ((,,,) String String String ([] String)) -> IO (Either String J.Json);
  runGroup directory timeout commands =
    do {
      host <- getEnv "MLF_TEST_HOST_SUPPORT";
      O.mkdir directory;
      let {
        spec = (directory ++ "/group.spec")
      };
      let {
        fields =
          (:) (showInt (S.length commands))
            (S.concatMap
               (\((,,,) cwd input output argv) ->
                  S.append
                    ((:) cwd
                       ((:) input
                          ((:) output
                             ((:) (output ++ ".stderr") ((:) (showInt (S.length argv)) [])))))
                    argv)
               commands)
      };
      writeFile spec (O.pack fields);
      code <-
        O.exec "" ((:) host ((:) "group" ((:) (formatDouble 6 timeout) ((:) spec [])))) ""
          (directory ++ "/group.json")
          (directory ++ "/group.err")
          30;
      if S.not (code == 0)
      then return (Left "group transport failed")
      else do {
             value <- J.read (directory ++ "/group.json");
             return
               (if ((V.int "exit_code" value == 0) && (V.int "remaining_children" value == 0))
                then Right value
                else Left "parallel compiler phase failed or timed out")
           }
    };
  -- The caller describes a dependency graph; the transport records every stage
  -- against one clock, including source emission, fresh runtime, LLVM and link.
  runPipeline :: String ->
                 Double ->
                 [] ((,) ([] Int) ((,,,) String String String ([] String))) ->
                 IO (Either String J.Json);
  runPipeline directory timeout commands =
    do {
      host <- getEnv "MLF_TEST_HOST_SUPPORT";
      O.mkdir directory;
      let {
        spec = (directory ++ "/pipeline.spec")
      };
      let {
        fields =
          (:) (showInt (S.length commands))
            (S.concatMap
               (\((,) dependencies ((,,,) cwd input output argv)) ->
                  S.append ((:) (showInt (S.length dependencies)) (S.map showInt dependencies))
                    (S.append
                       ((:) cwd
                          ((:) input
                             ((:) output
                                ((:) (output ++ ".stderr") ((:) (showInt (S.length argv)) [])))))
                       argv))
               commands)
      };
      writeFile spec (O.pack fields);
      code <-
        O.exec "" ((:) host ((:) "pipeline" ((:) (formatDouble 6 timeout) ((:) spec [])))) ""
          (directory ++ "/pipeline.json")
          (directory ++ "/pipeline.err")
          (1 + readInt (formatDouble 0 timeout));
      if S.not (code == 0)
      then return (Left "pipeline transport failed")
      else do {
             value <- J.read (directory ++ "/pipeline.json");
             return
               (if ((V.int "exit_code" value == 0) && (V.int "remaining_children" value == 0))
                then Right value
                else Left "compiler pipeline failed or timed out")
           }
    };
  buildParallel :: String ->
                   String ->
                   String ->
                   String ->
                   String -> [] String -> Double -> IO (Either String ((,) String J.Json));
  buildParallel directory compiler clang source runtime flags timeout =
    buildParallelWithIncludes directory compiler clang source runtime flags [] timeout;
  buildParallelWithIncludes :: String ->
                               String ->
                               String ->
                               String ->
                               String ->
                               [] String ->
                               [] String -> Double -> IO (Either String ((,) String J.Json));
  buildParallelWithIncludes directory compiler clang source runtime flags includes timeout =
    do {
      present <- directoryExists directory;
      files <- if present then O.entries directory else return [];
      if S.not (S.null files)
      then return (Left "build directory must be fresh")
      else do {
             O.mkdir directory;
             let {
               ir = (directory ++ "/program.ll")
             };
             let {
               object = (directory ++ "/runtime.o")
             };
             let {
               code = (directory ++ "/program.o")
             };
             let {
               binary = (directory ++ "/pending-executable")
             };
             let {
               mode = if O.ends ".mlfci" source then "--crate-to-llvm-gc" else "--emit-llvm-gc"
             };
             streaming <- getEnv "MLF_BENCH_STREAM_LLVM";
             O.require (eqString streaming "" || eqString streaming "1")
               "invalid streaming compiler setting";
             let {
               stream = eqString streaming "1"
             };
             linking <- getEnv "MLF_BENCH_STREAM_LINK";
             O.require (eqString linking "" || (eqString linking "1" && stream))
               "streaming link requires streaming LLVM";
             let {
               streamLink = eqString linking "1"
             };
             let {
               emit =
                 (:) compiler
                   (S.append (S.concatMap (\path -> (:) "-i" ((:) path [])) includes)
                      ((:) mode ((:) source [])))
             };
             let {
               frontend =
                 if stream
                 then (:) "/bin/bash"
                        ((:) "-o"
                           ((:) "pipefail"
                              ((:) "-c"
                                 ((:) "fifo=$1; shift; \"$@\" | /bin/cat > \"$fifo\""
                                    ((:) "mlf-stream" ((:) (ir ++ ".pipe") emit))))))
                 else emit
             };
             let {
               runtimeCommand =
                 S.append ((:) clang (O.words "-O2 -std=c11 -c"))
                   (S.append ((:) runtime flags) ((:) "-o" ((:) object [])))
             };
             let {
               llvmCommand =
                 S.append
                   ((:) clang
                      (S.append (if stream then (:) "--mlf-stream-ir" [] else [])
                         (O.words "-O2 -Wno-override-module -c")))
                   ((:) ir ((:) "-o" ((:) code [])))
             };
             let {
               linkCommand =
                 S.append
                   ((:) clang
                      (S.append (if streamLink then (:) "--mlf-wait-objects" [] else [])
                         ((:) code ((:) object flags))))
                   ((:) "-lm" ((:) "-o" ((:) binary [])))
             };
             let {
               ordinary =
                 (:) frontend ((:) runtimeCommand ((:) llvmCommand ((:) linkCommand [])))
             };
             let {
               setup = (:) "/usr/bin/mkfifo" ((:) (ir ++ ".pipe") [])
             };
             let {
               linked =
                 (:) setup
                   ((:) frontend
                      ((:) runtimeCommand
                         ((:) llvmCommand
                            ((:) ((:) "/usr/bin/touch" ((:) (object ++ ".ready") []))
                               ((:) ((:) "/usr/bin/touch" ((:) (code ++ ".ready") []))
                                  ((:) linkCommand []))))))
             };
             let {
               commands =
                 if streamLink then linked else if stream then (:) setup ordinary else ordinary
             };
             let {
               linkDependencies =
                 (:) []
                   ((:) ((:) 0 [])
                      ((:) []
                         ((:) ((:) 0 [])
                            ((:) ((:) 0 ((:) 2 []))
                               ((:) ((:) 0 ((:) 3 [])) ((:) ((:) 0 []) []))))))
             };
             let {
               dependencies =
                 if streamLink
                 then linkDependencies
                 else if stream
                      then (:) []
                             ((:) ((:) 0 [])
                                ((:) []
                                   ((:) ((:) 0 []) ((:) ((:) 1 ((:) 2 ((:) 3 []))) []))))
                      else (:) [] ((:) [] ((:) ((:) 0 []) ((:) ((:) 1 ((:) 2 [])) [])))
             };
             let {
               ordinaryOutputs =
                 (:) (if stream then (directory ++ "/frontend.stdout") else ir)
                   ((:) (directory ++ "/runtime.stdout")
                      ((:) (directory ++ "/llvm.stdout") ((:) (directory ++ "/link.stdout") [])))
             };
             let {
               linkedOutputs =
                 (:) (directory ++ "/setup.stdout")
                   ((:) (directory ++ "/frontend.stdout")
                      ((:) (directory ++ "/runtime.stdout")
                         ((:) (directory ++ "/llvm.stdout")
                            ((:) (directory ++ "/runtime-ready.stdout")
                               ((:) (directory ++ "/llvm-ready.stdout")
                                  ((:) (directory ++ "/link.stdout") []))))))
             };
             let {
               outputs =
                 if streamLink
                 then linkedOutputs
                 else if stream
                      then (:) (directory ++ "/setup.stdout") ordinaryOutputs
                      else ordinaryOutputs
             };
             let {
               phases =
                 O.words
                   (if streamLink
                    then "setup frontend runtime llvm runtime-ready llvm-ready link"
                    else if stream
                         then "setup frontend runtime llvm link"
                         else "frontend runtime llvm link")
             };
             result <-
               runPipeline directory timeout
                 (S.zipWith (\deps command -> (,) deps command) dependencies
                    (S.zipWith (\output argv -> (,,,) directory "" output argv) outputs commands));
             case result of {
               Left error -> return (Left error);
               Right group ->
                 do {
                   let {
                     stages =
                       S.zipWith (\name entry -> J.set "phase" (J.str name) entry) phases
                         (S.zipWith (\argv entry -> J.set "command" (J.stringArray argv) entry)
                            commands
                            (V.array "stages" group))
                   };
                   let {
                     cpu =
                       S.foldl addDouble 0.0
                         (S.map (\row -> V.double 0.0 (J.get "cpu_seconds" row)) stages)
                   };
                   return
                     (Right
                        ((,) binary
                           (J.set "cpu_seconds" (J.Number (formatDouble 9 cpu))
                              (J.set "stages" (J.Array stages) group))))
                 }
             }
           }
    };
  validateSelection :: J.Json -> J.Json -> Either String ();
  validateSelection configuration manifest =
    do {
      validateConfiguration configuration;
      let {
        selected =
          if J.has "benchmarks" configuration
          then J.getStrings "benchmarks" configuration
          else V.workloads
      };
      V.ensure
        (S.not (S.null selected) &&
         (S.all (\name -> S.elem eqString name V.workloads) selected &&
          (S.length selected == S.length (S.nubBy eqString selected))))
        "invalid benchmark selection";
      if J.has "size" configuration
      then do {
             V.ensure (S.length selected == 1) "size override requires exactly one benchmark";
             let {
               row =
                 S.fromMaybe (panic "unknown manifest workload")
                   (S.find (\row -> eqString (V.text "name" row) (S.head selected))
                      (V.array "workloads" manifest))
             };
             V.ensure
               ((V.int "size" configuration >= V.int "minimum_input" row) &&
                (V.int "size" configuration <= V.int "maximum_input" row))
               "benchmark size outside supported range"
           }
      else return ();
      return ()
    }
}
