-- | Insert virtual braces and semicolons from token positions. Strings and
-- nested comments are lexed before layout; explicit delimiters suspend it.
module MLF.Layout (layoutSource, originalError) where

import Data.List (find)
import Text.Parsec hiding (token, tokens)
import Text.Parsec.Error (setErrorPos)
import Text.Parsec.Language (emptyDef)
import Text.Parsec.Pos (initialPos, updatePosString)
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok

data Token = Token { spelling :: String, start :: SourcePos, end :: SourcePos }
data Kind = Top | Block | Bindings deriving Eq
data Mark = LetMark | IfMark deriving Eq
data Frame = Layout Kind Int | Explicit String | Marker Mark Int
data Pending = Open Kind | AfterLet Int
type Positions = [(SourcePos,SourcePos)]

layoutSource :: Bool -> FilePath -> String -> Either String (String,Positions)
layoutSource program file input = do
  (tokens,finish) <- either (Left . show) Right (parse scanned file input)
  let firstLine = case tokens of t:_ -> sourceLine (start t); [] -> 1
      sourceLineText = case drop (firstLine - 1) (lines input) of line:_ -> line; [] -> ""
      indentation = sourceColumn (updatePosString (initialPos file) (takeWhile (\c -> elem c " \t\r") sourceLineText))
      explicit = case tokens of t:_ -> spelling t == "{"; [] -> False
      header = case tokens of t:_ -> spelling t == "module"; [] -> False
      implicitRoot = program && not explicit && not header
      root = if implicitRoot then [Layout Top indentation] else []
      arranged = case arrange root Nothing Nothing tokens finish of
        (prefix,t):rest | implicitRoot -> ("{" ++ prefix,t):rest
        other -> other
  pure (render file arranged)

scanned :: Parser ([Token],SourcePos)
scanned = do
  white
  ts <- many $ do
    p <- getPosition
    s <- quoted <|> many1 (alphaNum <|> oneOf "_'") <|> many1 (oneOf ":!#$%&*+./<=>?@\\^|-~")
      <|> ((:[]) <$> anyChar)
    q <- getPosition
    white
    pure (Token s p q)
  p <- getPosition
  pure (ts,p)
  where
    lexer = Tok.makeTokenParser emptyDef
      { Tok.commentLine = "--", Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True }
    white = Tok.whiteSpace lexer
    quoted = do
      a <- char '"'
      s <- concat <$> many (escaped <|> ((:[]) <$> noneOf "\"\\"))
      b <- char '"'
      pure (a : s ++ [b])
    escaped = do
      a <- char '\\'
      s <- ((\gap -> gap ++ "\\") <$> many1 space <* char '\\')
        <|> ((:[]) <$> anyChar)
      pure (a:s)

arrange :: [Frame] -> Maybe Pending -> Maybe Token -> [Token] -> SourcePos -> [(String,Token)]
arrange frames pending _ [] finish =
  [(opening ++ closes frames,Token "" finish finish)]
  where opening = case pending of Just (Open _) -> "{}"; _ -> ""
arrange frames pending previous (t:ts) finish = case pending of
  Just (AfterLet line)
    | spelling t == "rec" -> ("",t) : arrange frames (Just (AfterLet (sourceLine (end t)))) (Just t) ts finish
    | spelling t == "{" -> ("",t) : next (pushToken t frames)
    | sourceLine (start t) > line -> opened Bindings frames
    | otherwise -> normal frames
  Just (Open kind)
    | spelling t == "{" -> ("",t) : next (pushToken t frames)
    | otherwise -> opened kind frames
  Nothing -> normal frames
  where
    column = sourceColumn (start t)
    newLine = maybe False ((< sourceLine (start t)) . sourceLine . end) previous
    prev = maybe "" spelling previous
    token = spelling t
    continuation = elem token ["in","then","else","of","where","|",")","}",";"]
      || elem prev ["in","then","else","=","->","<-",":","|","+","-","*","/","%","++","&&","||","==","/=","<","<=",">",">="]
    opened kind stack
      | kind /= Top && not (deeper column stack) =
          let (prefix,rest) = offside column continuation prev stack
          in ("{}" ++ prefix,t) : next (pushToken t rest)
      | otherwise = ("{",t) : next (pushToken t (Layout kind column : stack))
    normal stack =
      let (ending,closed) = case token of
            "in" -> closeMark LetMark False stack
            "then" -> closeMark IfMark True stack
            "else" -> closeMark IfMark False stack
            ")" -> closeExplicit "(" stack
            "}" -> closeExplicit "{" stack
            ";" -> ("",dropInline stack)
            _ -> ("",stack)
          (separator,scoped) = if newLine && not (elem token [")","}"])
            then offside column continuation prev closed else ("",closed)
          pushed = if elem token [")","}"] then scoped else pushToken t scoped
      in (ending ++ separator,t) : next pushed
    next stack = arrange stack (keyword t) (Just t) ts finish

-- A let marker distinguishes expression lets from do-local declarations and
-- pairs an explicit let block with its own 'in', even inside another let.
pushToken :: Token -> [Frame] -> [Frame]
pushToken t frames = case spelling t of
  "(" -> Explicit "(" : frames
  "{" -> Explicit "{" : frames
  "let" -> Marker LetMark (sourceColumn (start t)) : frames
  "if" -> Marker IfMark (sourceColumn (start t)) : frames
  _ -> frames

keyword :: Token -> Maybe Pending
keyword t = case spelling t of
  "do" -> Just (Open Block)
  "of" -> Just (Open Block)
  "where" -> Just (Open Block)
  "let" -> Just (AfterLet (sourceLine (end t)))
  _ -> Nothing

deeper :: Int -> [Frame] -> Bool
deeper n (Layout _ m:_) = n > m
deeper n (Marker _ _:rest) = deeper n rest
deeper _ _ = True

offside :: Int -> Bool -> String -> [Frame] -> (String,[Frame])
offside n continuation prev frames = case frames of
  Layout _ m:rest | n < m ->
    let (s,fs) = offside n continuation "}" rest in ('}':s,fs)
  Layout _ m:_ | n == m && not continuation && not (elem prev [";","{"]) -> (";",frames)
  Marker _ m:rest | n <= m && not continuation -> offside n continuation prev rest
  _ -> ("",frames)

dropInline :: [Frame] -> [Frame]
dropInline (Marker _ _:rest) = dropInline rest
dropInline fs = fs

closeMark :: Mark -> Bool -> [Frame] -> (String,[Frame])
closeMark wanted keep frames = case search frames of
  Nothing -> ("",frames)
  Just result -> result
  where
    search (f@(Marker mark _):rest)
      | mark == wanted = Just ("",if keep then f:rest else rest)
      | otherwise = search rest
    search (Layout _ _:rest) = do
      (s,fs) <- search rest
      pure ('}':s,fs)
    search _ = Nothing

closeExplicit :: String -> [Frame] -> (String,[Frame])
closeExplicit wanted frames = case search frames of
  Nothing -> ("",frames)
  Just result -> result
  where
    search (Explicit delimiter:rest) | delimiter == wanted = Just ("",rest)
    search (Layout _ _:rest) = do
      (s,fs) <- search rest
      pure ('}':s,fs)
    search (Marker _ _:rest) = search rest
    search _ = Nothing

closes :: [Frame] -> String
closes = concatMap (\f -> case f of Layout _ _ -> "}"; _ -> "")

-- Rebuild whitespace from the original coordinates. Virtual punctuation
-- never adds lines; a map restores columns in downstream parser errors.
render :: FilePath -> [(String,Token)] -> (String,Positions)
render file = go (initialPos file) (initialPos file)
  where
    go _ _ [] = ("",[])
    go original output ((prefix,t):rest) =
      let p = start t
          gap | sourceLine p > sourceLine original =
                  replicate (sourceLine p - sourceLine original) '\n' ++ replicate (sourceColumn p - 1) ' '
              | otherwise = replicate (max 0 (sourceColumn p - sourceColumn original)) ' '
          virtualStart = updatePosString output gap
          punctuation = if null prefix then "" else prefix ++ " "
          tokenStart = updatePosString virtualStart punctuation
          tokenEnd = updatePosString tokenStart (spelling t)
          text = gap ++ punctuation ++ spelling t
          (suffix,positions) = go (end t) tokenEnd rest
      in (text ++ suffix,(virtualStart,p):(tokenStart,p):(tokenEnd,end t):positions)

originalError :: Positions -> ParseError -> String
originalError positions err = show (setErrorPos original err)
  where
    p = errorPos err
    prior = find (\(out,_) -> sourceLine out == sourceLine p && sourceColumn out <= sourceColumn p) (reverse positions)
    original = case prior of
      Nothing -> p
      Just (out,source) -> setSourceColumn source (sourceColumn source + sourceColumn p - sourceColumn out)
