module MLF.Host.Layout (layout) where

import MLF.Host.Lexer

-- This is the fixed implementation dialect's layout algorithm, matching
-- libraries/mlf-frontend/Bootstrap/Layout.emlf. Explicit tokens retain spans.
data Kind = Top | Block | Bindings deriving Eq
data Mark = LetMark | IfMark deriving Eq
data Frame = Layout Kind Int | Explicit String | Marker Mark Int
data Pending = Open Kind | AfterLet Int

layout :: FilePath -> String -> Either String [Token]
layout file source = do
  (tokens,finish) <- scan file source
  let first=case tokens of { t:_ -> t; [] -> finish }
      implicit=spelling first /= "{" && spelling first /= "module"
      frames=if implicit then [Layout Top (lineIndent (line first))] else []
      arranged=arrange frames Nothing Nothing tokens finish
  pure (if implicit then virtual "{" first:arranged else arranged)
  where
    lineIndent n = indent 1 (if n <= length (lines source) then lines source !! (n-1) else "")
    indent c (' ':xs)=indent (c+1) xs
    indent c ('\r':xs)=indent (c+1) xs
    indent c ('\t':xs)=indent (c+8-(c-1) `mod` 8) xs
    indent c _=c

punctuation :: String -> Token -> [Token]
punctuation s t = map (\c -> virtual [c] t) s

arrange frames pending previous tokens finish = case tokens of
  [] -> punctuation ((case pending of { Just (Open _) -> "{}"; _ -> "" }) ++ closes frames) finish
  t:ts -> case pending of
    Just (AfterLet l)
      | spelling t == "rec" -> t:arrange frames (Just (AfterLet (endLine t))) (Just t) ts finish
      | spelling t == "{" -> t:next t ts finish (push t frames)
      | line t > l -> opened Bindings frames previous t ts finish
      | otherwise -> normal frames previous t ts finish
    Just (Open k) -> if spelling t == "{" then t:next t ts finish (push t frames) else opened k frames previous t ts finish
    Nothing -> normal frames previous t ts finish

next t rest finish stack = arrange scoped (keyword t) (Just t) rest finish
  where scoped = case (spelling t,rest,stack) of
          ("if",n:_,Marker IfMark _:outer) | spelling n == "{" -> outer
          _ -> stack
previousText = maybe "" spelling
continuation token previous = token `elem` ["]",",","in","then","else","of","where","|",")","}",";"] ||
  previous `elem` ["::",",","in","then","else","=","->","<-",":","|","+","-","*","/","%","++","&&","||","==","/=","<","<=",">",">="]
opened kind stack previous t rest finish
  | kind /= Top && not (deeper (column t) stack) =
      let (prefix,remaining)=offside (column t) (continuation (spelling t) (previousText previous)) (previousText previous) stack
      in punctuation ("{}"++prefix) t ++ t:next t rest finish (push t remaining)
  | otherwise = virtual "{" t:t:next t rest finish (push t (Layout kind (column t):stack))
normal stack previous t rest finish =
  let text=spelling t
      (ending,closed)=case text of
        "in" -> closeMark LetMark False stack
        "then" -> closeMark IfMark True stack
        "else" -> closeMark IfMark False stack
        ")" -> closeExplicit "(" stack
        "]" -> closeExplicit "[" stack
        "," -> closeCollection stack
        "}" -> closeExplicit "{" stack
        ";" -> ("",dropInline stack)
        _ -> ("",stack)
      newline=maybe False ((<line t).endLine) previous
      closing=text `elem` [")", "]", "}"]
      (separator,scoped)=if newline && not closing then offside (column t) (continuation text (previousText previous)) (previousText previous) closed else ("",closed)
  in punctuation (ending++separator) t ++ t:next t rest finish (if closing then scoped else push t scoped)
push t frames = case spelling t of
  x | x `elem` ["(","[","{"] -> Explicit x:frames
  "let" -> Marker LetMark (column t):frames
  "if" -> Marker IfMark (column t):frames
  _ -> frames
keyword t = case spelling t of
  x | x `elem` ["do","of","where"] -> Just (Open Block)
  "let" -> Just (AfterLet (endLine t))
  _ -> Nothing
deeper col (Layout _ n:_) = col > n
deeper col (Marker _ _:rest) = deeper col rest
deeper _ _ = True
offside col continued previous frames = case frames of
  Layout _ n:rest | col < n -> let (prefix,remaining)=offside col continued "}" rest in ('}':prefix,remaining)
                 | col == n && not continued && previous `notElem` [";","{"] -> (";",frames)
  Marker _ n:rest | col <= n && not continued -> offside col continued previous rest
  _ -> ("",frames)
dropInline (Marker _ _:rest)=dropInline rest
dropInline frames=frames
closeMark wanted keep frames = maybe ("",frames) id (search frames)
  where search fs = case fs of
          Marker mark _:rest -> if mark==wanted then Just ("",if keep then fs else rest) else search rest
          Layout _ _:rest -> fmap (\(s,remaining) -> ('}':s,remaining)) (search rest)
          _ -> Nothing
closeExplicit wanted frames = maybe ("",frames) id (search frames)
  where search fs = case fs of
          Explicit delimiter:rest -> if delimiter==wanted then Just ("",rest) else Nothing
          Layout _ _:rest -> fmap (\(s,remaining) -> ('}':s,remaining)) (search rest)
          Marker _ _:rest -> search rest
          _ -> Nothing
closeCollection frames = maybe ("",frames) id (search frames)
  where search fs = case fs of
          Explicit delimiter:_ -> if delimiter `elem` ["(","["] then Just ("",fs) else Nothing
          Layout _ _:rest -> fmap (\(s,remaining) -> ('}':s,remaining)) (search rest)
          Marker _ _:rest -> search rest
          _ -> Nothing
closes []=""
closes (Layout _ _:rest)='}':closes rest
closes (_:rest)=closes rest
