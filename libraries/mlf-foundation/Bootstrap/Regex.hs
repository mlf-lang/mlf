-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Regex (Regex, compile, find, countMatches, replaceAll) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.IntMap as M;
  import qualified Bootstrap.IntSet as Set;
  -- Ordered Thompson NFA. Consuming states are deduplicated at each input
  -- position; nullable loops terminate without recursive backtracking.
  -- Offsets and character classes use Unicode scalar values, like String itself.
  data CharacterSet =
    Ranges Bool ([] ((,) Int Int)) |
    Union ([] CharacterSet) |
    Complement CharacterSet |
    AnyCharacter;
  data Pattern =
    Empty |
    Character CharacterSet |
    Begin |
    End |
    Sequence Pattern Pattern |
    Alternative Pattern Pattern |
    Repeat Pattern Int (Maybe Int);
  data Instruction =
    Consume CharacterSet Int | Fork Int Int | Loop Int Int | AtBegin Int | AtEnd Int | Accept;
  data SearchPlan = GeneralPlan | FixedPlan Int String |
    SkipPlan Int String String String | SpanPlan String ([] Span);
  data Span = Single CharacterSet | Delimited CharacterSet Int CharacterSet String CharacterSet String;
  data Regex = Regex Int (IntMap Instruction) SearchPlan;
  data Parsed = Parsed Pattern Int | ParseError String;
  data ClassAtom = ClassAtom CharacterSet (Maybe Int) Int;
  data Build = Build Int (IntMap Instruction);
  data Thread = Thread Int Int;
  at :: String -> Int -> Int;
  at text offset = if (offset < stringLength text) then stringCodeAt text offset else (-1);
  failure :: Int -> String -> Parsed;
  failure offset message = ParseError (message ++ (" at character " ++ showInt offset));
  literal :: Int -> CharacterSet;
  literal code = Ranges False ((:) ((,) code code) []);
  digit :: Int -> Bool;
  digit code = ((code >= 48) && (code <= 57));
  asciiLetter :: Int -> Bool;
  asciiLetter code = (((code >= 65) && (code <= 90)) || ((code >= 97) && (code <= 122)));
  escaped :: String -> Int -> Either String ClassAtom;
  escaped text offset =
    let {
      code = at text offset
    } in
    let {
      ranges =
        if ((code == 100) || (code == 68))
        then (:) ((,) 48 57) []
        else if ((code == 119) || (code == 87))
             then (:) ((,) 48 57) ((:) ((,) 65 90) ((:) ((,) 95 95) ((:) ((,) 97 122) [])))
             else (:) ((,) 9 13) ((:) ((,) 32 32) [])
    } in
    if (code == (-1))
    then Left "trailing regular-expression escape"
    else if S.elem eqInt code ((:) 100 ((:) 68 ((:) 119 ((:) 87 ((:) 115 ((:) 83 []))))))
         then Right
                (ClassAtom (Ranges ((code == 68) || ((code == 87) || (code == 83))) ranges) Nothing
                   (offset + 1))
         else if (asciiLetter code && ((code /= 110) && ((code /= 114) && (code /= 116))))
              then Left ("unsupported regular-expression escape at character " ++ showInt offset)
              else if digit code
                   then Left "regular-expression backreferences are unsupported"
                   else let {
                          value =
                            if (code == 110)
                            then 10
                            else if (code == 114) then 13 else if (code == 116) then 9 else code
                        } in
                        Right (ClassAtom (literal value) (Just value) (offset + 1));
  classAtom :: String -> Int -> Either String ClassAtom;
  classAtom text offset =
    if (at text offset == 92)
    then escaped text (offset + 1)
    else if (at text offset == (-1))
         then Left "unterminated character class"
         else Right (ClassAtom (literal (at text offset)) (Just (at text offset)) (offset + 1));
  parseClass :: String -> Int -> Bool -> [] CharacterSet -> Parsed;
  parseClass text offset inverted parts =
    if (at text offset == (-1))
    then failure offset "unterminated character class"
    else if (at text offset == 93)
         then if S.null parts
              then failure offset "empty character class"
              else Parsed
                     (Character
                        (if inverted
                         then Complement (Union (S.reverse parts))
                         else Union (S.reverse parts)))
                     (offset + 1)
         else case classAtom text offset of {
                Left message -> ParseError message;
                Right (ClassAtom first value next) ->
                  if ((at text next == 45) &&
                      ((at text (next + 1) /= 93) && (at text (next + 1) /= (-1))))
                  then case classAtom text (next + 1) of {
                         Left message -> ParseError message;
                         Right (ClassAtom last upper after) ->
                           case value of {
                             Nothing ->
                               failure next "character-class range requires literal endpoints";
                             Just low ->
                               case upper of {
                                 Nothing ->
                                   failure next "character-class range requires literal endpoints";
                                 Just high ->
                                   if (low > high)
                                   then failure next "descending character-class range"
                                   else parseClass text after inverted
                                          ((:) (Ranges False ((:) ((,) low high) [])) parts)
                               }
                           }
                       }
                  else parseClass text next inverted ((:) first parts)
              };
  parseAtom :: String -> Int -> Parsed;
  parseAtom text offset =
    let {
      code = at text offset
    } in
    if (code == 40)
    then case parseAlternative text (offset + 1) of {
           ParseError message -> ParseError message;
           Parsed body next ->
             if (at text next == 41)
             then Parsed body (next + 1)
             else failure next "unterminated group"
         }
    else if (code == 91)
         then let {
                inverted = (at text (offset + 1) == 94)
              } in
              parseClass text (offset + (if inverted then 2 else 1)) inverted []
         else if (code == 92)
              then case escaped text (offset + 1) of {
                     Left message -> ParseError message;
                     Right (ClassAtom set value next) -> Parsed (Character set) next
                   }
              else if (code == 46)
                   then Parsed (Character AnyCharacter) (offset + 1)
                   else if (code == 94)
                        then Parsed Begin (offset + 1)
                        else if (code == 36)
                             then Parsed End (offset + 1)
                             else if S.elem eqInt code
                                       ((:) 42
                                          ((:) 43 ((:) 63 ((:) 123 ((:) 125 ((:) 93 []))))))
                                  then failure offset "unexpected regular-expression operator"
                                  else Parsed (Character (literal code)) (offset + 1);
  number :: String -> Int -> Int -> (,) Int Int;
  number text offset value =
    if (digit (at text offset) && (value <= 1000))
    then number text (offset + 1) (((value * 10) + at text offset) - 48)
    else (,) value offset;
  parseBound :: String -> Pattern -> Int -> Parsed;
  parseBound text body offset =
    if S.not (digit (at text offset))
    then failure offset "expected repetition count"
    else case number text offset 0 of {
           (,) minimum next ->
             if (minimum > 1000)
             then failure offset "repetition count exceeds 1000"
             else if (at text next == 125)
                  then Parsed (Repeat body minimum (Just minimum)) (next + 1)
                  else if (at text next /= 44)
                       then failure next "expected comma or closing repetition brace"
                       else if (at text (next + 1) == 125)
                            then Parsed (Repeat body minimum Nothing) (next + 2)
                            else if S.not (digit (at text (next + 1)))
                                 then failure (next + 1) "expected repetition count"
                                 else case number text (next + 1) 0 of {
                                        (,) maximum after ->
                                          if ((maximum > 1000) || (maximum < minimum))
                                          then failure next "invalid repetition bounds"
                                          else if (at text after /= 125)
                                               then failure after
                                                      "expected closing repetition brace"
                                               else Parsed (Repeat body minimum (Just maximum))
                                                      (after + 1)
                                      }
         };
  parseRepeated :: String -> Int -> Parsed;
  parseRepeated text offset =
    case parseAtom text offset of {
      ParseError message -> ParseError message;
      Parsed body next ->
        let {
          code = at text next
        } in
        if (code == 42)
        then Parsed (Repeat body 0 Nothing) (next + 1)
        else if (code == 43)
             then Parsed (Repeat body 1 Nothing) (next + 1)
             else if (code == 63)
                  then Parsed (Repeat body 0 (Just 1)) (next + 1)
                  else if (code == 123) then parseBound text body (next + 1) else Parsed body next
    };
  parseSequence :: String -> Int -> Pattern -> Parsed;
  parseSequence text offset prefix =
    if ((at text offset == (-1)) || ((at text offset == 41) || (at text offset == 124)))
    then Parsed prefix offset
    else case parseRepeated text offset of {
           ParseError message -> ParseError message;
           Parsed body next -> parseSequence text next (Sequence prefix body)
         };
  parseAlternative :: String -> Int -> Parsed;
  parseAlternative text offset =
    case parseSequence text offset Empty of {
      ParseError message -> ParseError message;
      Parsed left next ->
        if (at text next /= 124)
        then Parsed left next
        else case parseAlternative text (next + 1) of {
               ParseError message -> ParseError message;
               Parsed right after -> Parsed (Alternative left right) after
             }
    };
  emit :: Instruction -> Build -> (,) Int Build;
  emit instruction (Build next code) =
    (,) next (Build (next + 1) (M.insert next instruction code));
  assemble :: Pattern -> Int -> Build -> (,) Int Build;
  assemble pattern continuation state =
    case pattern of {
      Empty -> (,) continuation state;
      Character set -> emit (Consume set continuation) state;
      Begin -> emit (AtBegin continuation) state;
      End -> emit (AtEnd continuation) state;
      Sequence first second ->
        case assemble second continuation state of {
          (,) next after -> assemble first next after
        };
      Alternative first second ->
        case assemble second continuation state of {
          (,) right afterRight ->
            case assemble first continuation afterRight of {
              (,) left afterLeft -> emit (Fork left right) afterLeft
            }
        };
      Repeat body minimum maximum ->
        if (minimum > 0)
        then case assemble (Repeat body (minimum - 1) (S.mapOptional (\n -> (n - 1)) maximum))
                    continuation
                    state of {
               (,) next after -> assemble body next after
             }
        else case maximum of {
               Just remaining ->
                 if (remaining == 0)
                 then (,) continuation state
                 else case assemble (Repeat body 0 (Just (remaining - 1))) continuation state of {
                        (,) next after ->
                          case assemble body next after of {
                            (,) first final -> emit (Fork first continuation) final
                          }
                      };
               Nothing ->
                 case state of {
                   Build loop code ->
                     case assemble body loop (Build (loop + 1) code) of {
                       (,) first (Build next final) ->
                         (,) loop (Build next (M.insert loop (Loop first continuation) final))
                     }
                 }
             }
    };
  compile :: String -> Either String Regex;
  compile text =
    case parseAlternative text 0 of {
      ParseError message -> Left message;
      Parsed pattern end ->
        if (end /= stringLength text)
        then Left ("unexpected closing group at character " ++ showInt end)
        else if (patternSize pattern >= 10000)
             then Left "regular expression exceeds compilation budget"
             else case assemble pattern 0 (Build 1 (M.singleton 0 Accept)) of {
                    (,) start (Build size code) -> Right (Regex start code (searchPlan pattern))
                  }
    };
  -- This bounds construction work as well as emitted states: an empty body costs
  -- one unit so nested bounded empty repetitions cannot bypass the budget.
  patternSize :: Pattern -> Int;
  patternSize pattern =
    S.min 10000
      (case pattern of {
         Empty -> 1;
         Sequence first second -> (patternSize first + patternSize second);
         Alternative first second -> ((1 + patternSize first) + patternSize second);
         Repeat body minimum maximum ->
           case maximum of {
             Nothing -> (((minimum + 1) * patternSize body) + 1);
             Just limit -> (((limit * patternSize body) + limit) - minimum)
           };
         _ -> 1
       });
  contains :: CharacterSet -> Int -> Bool;
  contains set code =
    case set of {
      AnyCharacter -> (code /= 10);
      Ranges inverted ranges ->
        let {
          present = S.any (\((,) low high) -> ((code >= low) && (code <= high))) ranges
        } in
        if inverted then S.not present else present;
      Union parts -> S.any (\part -> contains part code) parts;
      Complement inner -> S.not (contains inner code)
    };
  -- These accelerators are compiled from the regular-expression structure.
  -- Equal-width alternatives have no competing end positions: the first
  -- accepting DFA transition is precisely the ordered NFA's leftmost match.
  -- Other expressions retain the ordered Thompson machine below.
  searchPlan :: Pattern -> SearchPlan;
  searchPlan pattern =
    case fixedPlan pattern of {
      Just plan -> plan;
      Nothing -> case spanAlternatives pattern of {
        Just spans -> if safeSpans spans then SpanPlan (spanDispatch spans) spans else GeneralPlan;
        Nothing -> GeneralPlan
      }
    };
  fixedWords :: Pattern -> Maybe ([] ([] CharacterSet));
  fixedWords pattern =
    case pattern of {
      Empty -> Just [[]];
      Character set -> Just [[set]];
      Sequence first second -> case fixedWords first of {
        Nothing -> Nothing;
        Just left -> case fixedWords second of {
          Nothing -> Nothing;
          Just right -> if S.length left * S.length right > 64 then Nothing
            else Just (S.concatMap (\prefix -> S.map (S.append prefix) right) left)
        }
      };
      Alternative first second -> case fixedWords first of {
        Nothing -> Nothing;
        Just left -> case fixedWords second of {
          Nothing -> Nothing;
          Just right -> if S.length left + S.length right > 64 then Nothing
            else Just (S.append left right)
        }
      };
      _ -> Nothing
    };
  boundaries :: CharacterSet -> [] Int;
  boundaries set = case set of {
    AnyCharacter -> [10,11];
    Ranges _ ranges -> S.concatMap (\((,) low high) -> [low, high + 1]) ranges;
    Union parts -> S.concatMap boundaries parts;
    Complement inner -> boundaries inner
  };
  partitionPoints :: [] CharacterSet -> [] Int;
  partitionPoints sets = Set.toList (Set.fromList (S.append [0,1114112] (S.concatMap boundaries sets)));
  asciiSet :: CharacterSet -> Bool;
  asciiSet set = S.all (\code -> code < 128 || code >= 1114112 || S.not (contains set code))
    (Set.toList (Set.fromList (S.append [128] (boundaries set))));
  disjointSets :: CharacterSet -> CharacterSet -> Bool;
  disjointSets first second = S.all
    (\code -> code >= 1114112 || S.not (contains first code && contains second code))
    (partitionPoints [first,second]);
  fixedInstructions :: [] ([] CharacterSet) -> IntMap ((,) CharacterSet Int);
  fixedInstructions words = M.fromList (S.concatMap
    (\((,) base word) -> S.zipWith (\index set -> (,) index ((,) set
      (if index + 1 == base + S.length word then (-1) else index + 1)))
      (S.range base (base + S.length word - 1)) word)
    (S.zip (S.map (\n -> n * S.length (S.head words)) (S.range 0 (S.length words - 1))) words));
  intervalIndex :: [] Int -> Int -> Int -> Int;
  intervalIndex points code index = case points of {
    [] -> index;
    (:) boundary rest -> if code < boundary then index else intervalIndex rest code (index + 1)
  };
  stateIndex :: [] Int -> [] ([] Int) -> Int -> Maybe Int;
  stateIndex state known index = case known of {
    [] -> Nothing;
    (:) first rest -> if S.eqList eqInt state first then Just index else stateIndex state rest (index + 1)
  };
  fixedStep :: IntMap ((,) CharacterSet Int) -> [] Int -> Int -> [] Int;
  fixedStep instructions active code = Set.toList (Set.fromList (S.concatMap
    (\index -> case M.get index instructions of {
      (,) set next -> if contains set code then [next] else []
    }) active));
  fixedRow :: IntMap ((,) CharacterSet Int) -> [] Int -> [] Int -> [] Int -> [] ([] Int) ->
              [] Int -> Maybe ((,) ([] ([] Int)) ([] Int));
  fixedRow instructions starts state alphabet known row = case alphabet of {
    [] -> Just ((,) known (S.reverse row));
    (:) character rest -> let {
      next = fixedStep instructions (S.append starts state) character
    } in if S.elem eqInt (-1) next
      then fixedRow instructions starts state rest known ((:) 0 row)
      else case stateIndex next known 0 of {
        Just index -> fixedRow instructions starts state rest known ((:) (index + 1) row);
        -- Keep every encoded transition in ASCII, including the state + 1
        -- representation; larger automata retain the general matcher.
        Nothing -> if S.length known >= 127 then Nothing
          else fixedRow instructions starts state rest (S.snoc known next) ((:) (S.length known + 1) row)
      }
  };
  fixedRows :: IntMap ((,) CharacterSet Int) -> [] Int -> [] Int -> [] Int -> Int -> [] ([] Int) ->
               [] String -> Maybe String;
  fixedRows instructions starts alphabet columns index known rows =
    if index == S.length known then Just (S.concatStrings (S.reverse rows))
    else case fixedRow instructions starts (S.index known index) alphabet known [] of {
      Nothing -> Nothing;
      -- Determinize one representative per character interval, then expand its
      -- row to direct ASCII columns. At most 127 * 128 bytes per table avoid a
      -- second dependent alphabet lookup in every subject-character step.
      Just ((,) expanded row) -> let {
        encoded = S.concatMapString stringFromCode row;
        direct = S.concatMapString (\column -> stringFromCode (stringCodeAt encoded column)) columns
      } in fixedRows instructions starts alphabet columns (index + 1) expanded ((:) direct rows)
    };
  fixedPlan :: Pattern -> Maybe SearchPlan;
  fixedPlan pattern = case fixedWords pattern of {
    Nothing -> Nothing;
    Just words -> let {
      width = S.length (S.head words);
      sets = S.concat words
    } in if width <= 0 || width > 64 || S.length sets > 256 ||
      S.not (S.all (\word -> S.length word == width) words) || S.not (S.all asciiSet sets)
      then Nothing
      else let {
        points = Set.toList (Set.fromList (S.append [0] (S.filter (\n -> n > 0 && n < 128)
          (S.concatMap boundaries sets))));
        columns = S.map (\code -> intervalIndex (S.tail points) code 0) (S.range 0 127);
        starts = S.map (\n -> n * width) (S.range 0 (S.length words - 1))
      } in case fixedRows (fixedInstructions words) starts points columns 0 [[]] [] of {
        Nothing -> Nothing;
        Just table ->
          if width < 2 then Just (FixedPlan width table)
          else case fixedRows (fixedInstructions (S.map S.reverse words)) [] points columns 0 [[],starts] [] of {
            Nothing -> Just (FixedPlan width table);
            Just backward -> Just (SkipPlan width table backward
              (S.concatMapString (\code -> stringFromCode (fixedShift words width code)) (S.range 0 127)))
          }
      }
  };
  -- One bad-character table serves every equal-width alternative. Its shift
  -- is the minimum licensed by any alternative, so no possible start is
  -- skipped. The last position is excluded, as in Horspool's rule.
  fixedShift :: [] ([] CharacterSet) -> Int -> Int -> Int;
  fixedShift words width code = S.foldlStrict
    (\shift word -> S.foldlStrict (\current ((,) index set) ->
      if contains set code then S.min current (width - index - 1) else current)
      shift (S.zip (S.range 0 (width - 2)) (S.take (width - 1) word))) width words;
  -- Flatten only concatenation; nullable/ambiguous regex operators are never
  -- discarded. The delimiter path requires a body/suffix partition, so there
  -- is exactly one possible end for each start and no greedy backtracking.
  sequenceParts :: Pattern -> [] Pattern;
  sequenceParts pattern = case pattern of {
    Empty -> [];
    Sequence left right -> S.append (sequenceParts left) (sequenceParts right);
    _ -> [pattern]
  };
  spanAlternative :: Pattern -> Maybe Span;
  spanAlternative pattern = case sequenceParts pattern of {
    [Character set] -> Just (Single set);
    [Character prefix, Repeat (Character body) minimum Nothing, Character suffix] ->
      if minimum <= 1 && disjointSets body suffix
      then Just (Delimited prefix minimum body (asciiMembership body) suffix (asciiMembership suffix)) else Nothing;
    [Character prefix, Character required, Repeat (Character body) 0 Nothing, Character suffix] ->
      if sameSet required body && disjointSets body suffix
      then Just (Delimited prefix 1 body (asciiMembership body) suffix (asciiMembership suffix)) else Nothing;
    _ -> Nothing
  };
  sameSet :: CharacterSet -> CharacterSet -> Bool;
  sameSet first second = S.all (\code -> code >= 1114112 || contains first code == contains second code)
    (partitionPoints [first,second]);
  spanAlternatives :: Pattern -> Maybe ([] Span);
  spanAlternatives pattern = case pattern of {
    Alternative first second -> case spanAlternatives first of {
      Nothing -> Nothing;
      Just left -> case spanAlternatives second of {
        Nothing -> Nothing;
        Just right -> if S.length left + S.length right > 64 then Nothing else Just (S.append left right)
      }
    };
    _ -> S.mapOptional (\span -> [span]) (spanAlternative pattern)
  };
  spanPrefix :: Span -> CharacterSet;
  spanPrefix span = case span of { Single set -> set; Delimited prefix _ _ _ _ _ -> prefix };
  safeSpans :: [] Span -> Bool;
  safeSpans spans = S.length spans <= 64 && safeSpanPairs spans spans;
  safeSpanPairs :: [] Span -> [] Span -> Bool;
  safeSpanPairs all remaining = case remaining of {
    [] -> True;
    (:) first rest -> S.all (\second -> disjointSets (spanPrefix first) (spanPrefix second)) rest &&
      (case first of {
        Single _ -> True;
        Delimited prefix _ body _ _ _ -> S.all (\other ->
          sameSet prefix (spanPrefix other) || disjointSets body (spanPrefix other)) all
      }) && safeSpanPairs all rest
  };
  asciiMembership :: CharacterSet -> String;
  asciiMembership set = S.concatMapString (\code -> stringFromCode (if contains set code then 1 else 0))
    (S.range 0 127);
  spanOrdinal :: [] Span -> Int -> Int -> Int;
  spanOrdinal spans code index = case spans of {
    [] -> 0;
    (:) span rest -> if contains (spanPrefix span) code then index else spanOrdinal rest code (index + 1)
  };
  spanDispatch :: [] Span -> String;
  -- Disjoint prefixes let one ASCII lookup choose an alternative without
  -- allocating a predicate closure for every input character. Non-ASCII
  -- scalars still use the original character-set predicates, at scalar offsets.
  spanDispatch spans = S.concatMapString (\code -> stringFromCode (spanOrdinal spans code 1)) (S.range 0 127);
  spanAt :: String -> [] Span -> Int -> Maybe Span;
  spanAt dispatch spans code =
    if code < 128 then let { index = stringCodeAt dispatch code } in
      if index == 0 then Nothing else Just (S.index spans (index - 1))
    else S.find (\span -> contains (spanPrefix span) code) spans;
  scanFixed :: String -> String -> Int -> Int -> Int -> Int;
  scanFixed table subject size offset state =
    if offset >= size then (-1) else let {
      character = stringCodeAt subject offset;
      next = if character >= 128 then 1 else stringCodeAt table
        (state * 128 + character)
    } in if next == 0 then offset + 1 else scanFixed table subject size (offset + 1) (next - 1);
  countFixed :: String -> String -> Int -> Int -> Int -> Int -> Int;
  countFixed table subject size offset state count =
    if offset >= size then count else let {
      character = stringCodeAt subject offset;
      next = if character >= 128 then 1 else stringCodeAt table
        (state * 128 + character);
      total = if next == 0 then count + 1 else count
    } in seq total (countFixed table subject size (offset + 1)
      (if next == 0 then 0 else next - 1) total);
  -- The reverse DFA is anchored: it does not inject fresh starts. Row zero is
  -- the dead state, row one its initial state; transition zero accepts. A
  -- failed match returns the remaining width, recording exact comparison work.
  backwardMatch :: String -> String -> Int -> Int -> Int -> Int;
  backwardMatch table subject offset state remaining =
    if remaining <= 0 then 0 else let {
      character = stringCodeAt subject offset;
      next = if character >= 128 then 1 else stringCodeAt table
        (state * 128 + character)
    } in if next == 0 then 0 else if next == 1 then remaining
      else backwardMatch table subject (offset - 1) (next - 1) (remaining - 1);
  backwardFirst :: String -> String -> Int -> Int -> Int -> Int;
  backwardFirst table subject end width character = let {
    next = if character >= 128 then 1 else stringCodeAt table (128 + character)
  } in if next == 0 then 0 else if next == 1 then width
    else backwardMatch table subject (end - 1) (next - 1) (width - 1);
  -- Adversarial subjects can defeat a bad-character heuristic. Charge both
  -- subject/table reads for every reverse comparison and the shift-table read
  -- against the two reads a forward DFA would spend per advanced scalar.
  -- A capped credit balance permits only bounded excess work before resuming
  -- the forward DFA at the next unexamined start. Accepting matches advance a
  -- full positive width, so resetting their credit also retains linear work.
  -- Credits and counters are forced on every iteration.
  scanSkip :: Int -> String -> String -> String -> String -> Int -> Int -> Int -> Int;
  scanSkip width forward backward shifts subject size end credit =
    if end >= size then (-1) else let {
      character = stringCodeAt subject end;
      -- Keep this small reverse-entry expression in the scanning worker so
      -- its already-forced subject/end facts survive the first backward step.
      remaining = let {
        reverseNext = if character >= 128 then 1 else stringCodeAt backward (128 + character)
      } in if reverseNext == 0 then 0 else if reverseNext == 1 then width
        else backwardMatch backward subject (end - 1) (reverseNext - 1) (width - 1)
    } in if remaining == 0 then end + 1 else let { cap = 2 * width } in
      -- min first demands its cap, then the credit expression demands credit
      -- before shift. Keep that order explicit, and construct the next offset
      -- only after balance is known, avoiding deferred arithmetic each step.
      seq cap (seq credit (let {
        shift = if character >= 128 then width else stringCodeAt shifts character
      } in seq shift (let {
        raw = credit + 2 * shift - (2 * (width - remaining + 1) + 1)
      } in seq raw (let { balance = S.min cap raw } in seq balance (let { next = end + shift } in if balance < 0
        then scanFixed forward subject size (next - width + 1) 0
        else scanSkip width forward backward shifts subject size next balance)))));
  countSkip :: Int -> String -> String -> String -> String -> Int -> Int -> Int -> Int -> Int;
  countSkip width forward backward shifts subject size end credit count =
    if end >= size then count else let {
      character = stringCodeAt subject end;
      -- Keep this small reverse-entry expression in the scanning worker so
      -- its already-forced subject/end facts survive the first backward step.
      remaining = let {
        reverseNext = if character >= 128 then 1 else stringCodeAt backward (128 + character)
      } in if reverseNext == 0 then 0 else if reverseNext == 1 then width
        else backwardMatch backward subject (end - 1) (reverseNext - 1) (width - 1)
    } in if remaining == 0 then let { total = count + 1 } in
      seq total (countSkip width forward backward shifts subject size (end + width) (2 * width) total)
    else let { cap = 2 * width } in seq cap (seq credit (let {
      shift = if character >= 128 then width else stringCodeAt shifts character
    } in seq shift (let {
      raw = credit + 2 * shift - (2 * (width - remaining + 1) + 1)
    } in seq raw (let { balance = S.min cap raw } in seq balance (let { next = end + shift } in if balance < 0
      then countFixed forward subject size (next - width + 1) 0 count
      else countSkip width forward backward shifts subject size next balance count)))));
  spanBodyEnd :: CharacterSet -> String -> String -> Int -> Int -> Int;
  spanBodyEnd body membership subject size offset =
    if offset >= size then offset else let { code = stringCodeAt subject offset } in
      if (if code < 128 then stringCodeAt membership code /= 0 else contains body code)
      then spanBodyEnd body membership subject size (offset + 1) else offset;
  scanSpans :: String -> [] Span -> String -> Int -> Int -> Maybe ((,) Int Int);
  scanSpans dispatch spans subject size offset =
    if offset >= size then Nothing else case spanAt dispatch spans (stringCodeAt subject offset) of {
      Nothing -> scanSpans dispatch spans subject size (offset + 1);
      Just (Single _) -> Just ((,) offset (offset + 1));
      Just (Delimited _ minimum body membership suffix suffixMembership) -> let {
        end = spanBodyEnd body membership subject size (offset + 1)
      } in if end < size && end - offset - 1 >= minimum &&
           (let { code = stringCodeAt subject end } in
            if code < 128 then stringCodeAt suffixMembership code /= 0 else contains suffix code)
        then Just ((,) offset (end + 1)) else scanSpans dispatch spans subject size end
    };
  closure :: IntMap Instruction ->
             Int ->
             Int ->
             [] Thread ->
             IntSet -> [] Thread -> (,,) ([] Thread) IntSet (Maybe ((,) Int Int));
  -- Returning to a repetition without consuming a character terminates that
  -- iteration at its current priority, before alternatives still on the stack.
  closure code size offset pending seen ready =
    case pending of {
      [] -> (,,) (S.reverse ready) seen Nothing;
      (:) (Thread instruction start) rest ->
        if Set.member instruction seen
        then case M.get instruction code of {
               Loop body next ->
                 closure code size offset ((:) (Thread next start) rest) seen ready;
               _ -> closure code size offset rest seen ready
             }
        else let {
               visited = Set.insert instruction seen
             } in
             case M.get instruction code of {
               Accept -> (,,) (S.reverse ready) visited (Just ((,) start offset));
               Consume set next ->
                 closure code size offset rest visited ((:) (Thread instruction start) ready);
               Fork first second ->
                 closure code size offset
                   ((:) (Thread first start) ((:) (Thread second start) rest))
                   visited
                   ready;
               Loop first second ->
                 closure code size offset
                   ((:) (Thread first start) ((:) (Thread second start) rest))
                   visited
                   ready;
               AtBegin next ->
                 closure code size offset
                   (if (offset == 0) then (:) (Thread next start) rest else rest)
                   visited
                   ready;
               AtEnd next ->
                 closure code size offset
                   (if (offset == size) then (:) (Thread next start) rest else rest)
                   visited
                   ready
             }
    };
  advance :: IntMap Instruction -> Int -> [] Thread -> [] Thread;
  advance code character threads =
    case threads of {
      [] -> [];
      (:) (Thread instruction start) rest ->
        case M.get instruction code of {
          Consume set next ->
            if contains set character
            then (:) (Thread next start) (advance code character rest)
            else advance code character rest;
          _ -> panic "invalid consuming regular-expression state"
        }
    };
  search :: Regex ->
            String -> Int -> Int -> [] Thread -> Maybe ((,) Int Int) -> Maybe ((,) Int Int);
  search regex subject size offset pending fallback =
    case regex of {
      Regex start code _ ->
        let {
          candidates =
            case fallback of {
              Nothing -> S.snoc pending (Thread start offset);
              Just result -> pending
            }
        } in
        case closure code size offset candidates Set.empty [] of {
          (,,) ready visited accepted ->
            let {
              best =
                case accepted of {
                  Nothing -> fallback;
                  Just result -> accepted
                }
            } in
            if ((offset == size) || (S.null ready && S.isJust best))
            then best
            else search regex subject size (offset + 1)
                   (advance code (stringCodeAt subject offset) ready)
                   best
        }
    };
  find :: Regex -> String -> Int -> Maybe ((,) Int Int);
  find regex subject offset =
    if ((offset < 0) || (offset > stringLength subject))
    then Nothing
    else case regex of {
      Regex _ _ (FixedPlan width table) ->
        let { end = scanFixed table subject (stringLength subject) offset 0 } in
        if end < 0 then Nothing else Just ((,) (end - width) end);
      Regex _ _ (SkipPlan width forward backward shifts) ->
        let { end = scanSkip width forward backward shifts subject (stringLength subject)
          (offset + width - 1) (2 * width) } in
        if end < 0 then Nothing else Just ((,) (end - width) end);
      Regex _ _ (SpanPlan dispatch spans) -> scanSpans dispatch spans subject (stringLength subject) offset;
      Regex _ _ GeneralPlan -> search regex subject (stringLength subject) offset [] Nothing
    };
  countFrom :: Regex -> String -> Int -> Int -> Int;
  countFrom regex subject offset count =
    case find regex subject offset of {
      Nothing -> count;
      Just ((,) start end) ->
        let {
          total = (count + 1)
        } in
        seq total
          (if ((start == end) && (end == stringLength subject))
           then total
           else countFrom regex subject (if (start == end) then (end + 1) else end) total)
    };
  countMatches :: Regex -> String -> Int;
  countMatches regex subject = let { size = stringLength subject } in
    -- The original countFrom enters find's bounds check before inspecting the
    -- regex. Keep that demand order even when selecting a compiled fast plan.
    seq size (case regex of {
      Regex _ _ (FixedPlan _ table) -> countFixed table subject size 0 0 0;
      Regex _ _ (SkipPlan width forward backward shifts) ->
        countSkip width forward backward shifts subject size (width - 1) (2 * width) 0;
      _ -> countFrom regex subject 0 0
    });
  replaceFrom :: Regex -> String -> String -> Int -> Int -> [] String -> String;
  replaceFrom regex replacement subject offset copied pieces =
    case find regex subject offset of {
      Nothing ->
        S.concatStrings
          (S.reverse (if copied == stringLength subject then pieces
            else (:) (stringSlice subject copied (stringLength subject - copied)) pieces));
      Just ((,) start end) ->
        let {
          -- Skip structurally empty pieces before concatenating the result.
          -- Inspect replacement only after a match, so an
          -- unused replacement retains the public API's existing laziness.
          prefix = if start == copied then pieces else (:) (stringSlice subject copied (start - copied)) pieces;
          next = if stringLength replacement == 0 then prefix else (:) replacement prefix
        } in
        if ((start == end) && (end == stringLength subject))
        then S.concatStrings (S.reverse next)
        else replaceFrom regex replacement subject (if (start == end) then (end + 1) else end) end
               next
    };
  replaceAll :: Regex -> String -> String -> String;
  replaceAll regex replacement subject = replaceFrom regex replacement subject 0 0 []
}
