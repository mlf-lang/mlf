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
  data Regex = Regex Int (IntMap Instruction);
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
                    (,) start (Build size code) -> Right (Regex start code)
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
      Regex start code ->
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
    else search regex subject (stringLength subject) offset [] Nothing;
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
  countMatches regex subject = countFrom regex subject 0 0;
  replaceFrom :: Regex -> String -> String -> Int -> Int -> [] String -> String;
  replaceFrom regex replacement subject offset copied pieces =
    case find regex subject offset of {
      Nothing ->
        S.concatStrings
          (S.reverse ((:) (stringSlice subject copied (stringLength subject - copied)) pieces));
      Just ((,) start end) ->
        let {
          next = (:) replacement ((:) (stringSlice subject copied (start - copied)) pieces)
        } in
        if ((start == end) && (end == stringLength subject))
        then S.concatStrings (S.reverse next)
        else replaceFrom regex replacement subject (if (start == end) then (end + 1) else end) end
               next
    };
  replaceAll :: Regex -> String -> String -> String;
  replaceAll regex replacement subject = replaceFrom regex replacement subject 0 0 []
}
