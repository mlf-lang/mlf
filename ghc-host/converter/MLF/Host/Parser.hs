module MLF.Host.Parser (parseModule) where

import Control.Monad (void, when)
import Data.Char (isAlpha, isLower, isUpper, isDigit)
import Data.List (intercalate)
import qualified Text.Parsec as P
import Text.Parsec hiding (Token, parse, parseTest, lower, upper)
import Text.Parsec.Pos (newPos)
import MLF.Host.Lexer
import MLF.Host.Layout
import MLF.Host.Syntax

type Parser = Parsec [Token] ()

parseModule :: FilePath -> String -> Either String Module
parseModule file source = do
  tokens <- layout file source
  either (Left . show) Right (P.parse (moduleP <* eof) file tokens)

tok :: (String -> Bool) -> Parser Token
tok predicate = tokenPrim spelling update (\t -> if predicate (spelling t) then Just t else Nothing)
  where update pos t rest = case rest of
          n:_ -> newPos (sourceName pos) (line n) (column n)
          [] -> newPos (sourceName pos) (endLine t) (endColumn t)

sym :: String -> Parser String
sym s = spelling <$> tok (==s)

-- MLF allows the lambda delimiter to be a prefix of a maximal symbol token.
prefix :: String -> Parser String
prefix s = try $ do
  ts <- getInput
  case ts of
    t:rest | take (length s) (spelling t) == s -> do
      _ <- anyToken
      let suffix=drop (length s) (spelling t)
      when (not (null suffix)) (setInput (t { spelling=suffix, column=column t+length s }:rest))
      pure s
    _ -> unexpected s

reserved :: [String]
reserved = words "data class instance where case of do let rec in if then else forall exists true false True False bot module import"
ident :: (Char -> Bool) -> Parser String
ident predicate = spelling <$> tok (\s -> not (null s) && predicate (head s) && s `notElem` reserved)
lower, upper, name :: Parser String
lower = ident isLower
upper = ident isUpper
name = ident isAlpha
upperRef :: Parser String
upperRef = reference (upper <|> sym "True" <|> sym "False")
lowerRef :: Parser String
lowerRef = try (reference lower)
reference :: Parser String -> Parser String
reference final = do
  prefixes <- many (try (upper <* sym "."))
  n <- final
  pure (intercalate "." (prefixes++[n]))
moduleName :: Parser String
moduleName = intercalate "." <$> sepBy1 upper (sym ".")
parens, braces :: Parser a -> Parser a
parens = between (sym "(") (sym ")")
braces = between (sym "{") (sym "}")
annSym :: Parser String
annSym = sym ":" <|> sym "::"
at :: Parser Token
at = lookAhead anyToken
sep :: Parser ()
sep = void (sym ";") <|> void (lookAhead (sym "}"))

moduleP :: Parser Module
moduleP = do
  header <- optionMaybe $ do
    sym "module"
    n <- moduleName
    exports <- optionMaybe (parens (sepEndBy exportP (sym ",")))
    sym "where"
    pure (n,exports)
  braces $ do
    imports <- many (importP <* sep)
    declarations <- many (decl <* sep)
    body <- optionMaybe expr
    let (n,exports)=maybe ("Main",Nothing) id header
    case body of
      Nothing -> pure (Module n exports imports declarations)
      Just e | n=="Main" -> do
        t <- at
        pure (Module n exports imports (declarations++[Equation t "main" [] Nothing e]))
      Just _ -> fail "named implementation modules must contain declarations only"

exportP :: Parser Export
exportP = (ModuleExport <$> (sym "module" *> moduleName))
  <|> (ValueExport <$> lowerRef)
  <|> do
    n <- upperRef
    members <- optionMaybe (parens (([".."] <$ sym "..") <|> sepEndBy (name <|> sym "True" <|> sym "False") (sym ",")))
    pure (TypeExport n members)
importP :: Parser Import
importP = do
  sym "import"
  qualified <- option False (True <$ sym "qualified")
  n <- moduleName
  alias <- optionMaybe (sym "as" *> moduleName)
  selection <- optionMaybe $ do
    hiding <- option False (True <$ sym "hiding")
    items <- parens (sepEndBy exportP (sym ","))
    pure (hiding,items)
  pure (Import qualified n alias selection)
decl :: Parser Decl
decl = dataP <|> classP <|> instanceP <|> valueP
valueP :: Parser Decl
valueP = try signature <|> equation
signature :: Parser Decl
signature = do
  t <- at
  n <- lower
  annSym
  ty <- typeP
  lookAhead (sym ";")
  pure (Signature t n ty)
equation :: Parser Decl
equation = do
  t <- at
  n <- lower
  ps <- many patternAtom
  ty <- optionMaybe (annSym *> typeP)
  body <- (sym "=" *> expr) <|> (many1 (guardBranch "=") >>= guards)
  pure (Equation t n ps ty body)
valueBlock :: Parser [Decl]
valueBlock = braces (sepEndBy1 valueP (sym ";")) <|> ((:[]) <$> equation)

parameter :: Parser (String,Maybe Kind)
parameter = try (parens ((,) <$> lower <*> (Just <$> (sym ":" *> kindP)))) <|> ((\n -> (n,Nothing)) <$> lower)
kindP :: Parser Kind
kindP = chainr1 ((Star <$ sym "*") <|> parens kindP) (KArrow <$ sym "->")
contextP :: Parser [Type]
contextP = try ((parens (sepBy1 predicate (sym ",")) <|> ((:[]) <$> predicate)) <* sym "=>")
predicate :: Parser Type
predicate = foldl TyApp <$> (TyName <$> upperRef) <*> many1 typeAtom
classP :: Parser Decl
classP = do
  t <- at
  sym "class"
  supers <- option [] contextP
  n <- upper
  parameters <- many1 parameter
  sym "where"
  methods <- braces (sepEndBy ((,) <$> lower <*> (annSym *> typeP)) (sym ";"))
  pure (Class t supers n parameters methods)
instanceP :: Parser Decl
instanceP = do
  t <- at
  sym "instance"
  variables <- option [] (sym "forall" *> many1 parameter <* sym ".")
  givens <- option [] contextP
  n <- upperRef
  types <- many1 typeAtom
  sym "where"
  methods <- braces (sepEndBy valueP (sym ";"))
  pure (Instance t variables givens n types methods)
dataP :: Parser Decl
dataP = do
  t <- at
  sym "data"
  n <- upper
  parameters <- many parameter
  sym "="
  constructors <- sepBy1 ((,) <$> upper <*> many typeAtom) (sym "|")
  pure (Data t n parameters constructors)
typeP :: Parser Type
typeP = (TyForall <$> (sym "forall" *> many1 parameter <* sym ".") <*> typeP)
  <|> try (TyContext <$> contextP <*> typeP)
  <|> chainr1 typeApp (TyArrow <$ sym "->")
typeApp :: Parser Type
typeApp = foldl1 TyApp <$> many1 typeAtom
typeAtom :: Parser Type
typeAtom = (parens (collection ")" typeP >>= tuple (TyName "Unit") (\n xs -> foldl TyApp (TyName n) xs)))
  <|> (TyApp (TyName "List") <$> between (sym "[") (sym "]") typeP)
  <|> (TyName <$> lower) <|> (TyName <$> upperRef)

expr :: Parser Expr
expr = do
  e <- disjunction
  option e (Ann e <$> (annSym *> typeP))
binary :: String -> String -> Parser (Expr -> Expr -> Expr)
binary s n = (\a b -> apps (Var n) [a,b]) <$ sym s
disjunction, conjunction, comparison, concatenation, addition, multiplication, prefixed, operand, application, atom :: Parser Expr
disjunction = chainr1 conjunction ((\a b -> If a (Lit (LBool True)) b) <$ sym "||")
conjunction = chainr1 comparison ((\a b -> If a b (Lit (LBool False))) <$ sym "&&")
comparison = do
  a <- concatenation
  option a $ do
    op <- choice [binary "==" "eqInt", binary "/=" "$neInt", binary "<" "ltInt", binary "<=" "$leInt", binary ">" "$gtInt", binary ">=" "$geInt"]
    b <- concatenation
    pure (op a b)
concatenation = chainr1 addition (binary "++" "concatString")
addition = chainl1 multiplication (binary "+" "addInt" <|> binary "-" "subInt")
multiplication = chainl1 prefixed (binary "*" "mulInt" <|> binary "/" "quotInt" <|> binary "%" "remInt")
prefixed = do
  sign <- optionMaybe (sym "-" <|> sym "+")
  e <- operand
  pure $ case (sign,e) of
    (Just "-",Lit (LDouble n)) -> Lit (LDouble ('-':n))
    (Just "+",Lit (LDouble _)) -> e
    (Just "-",_) -> apps (Var "subInt") [Lit (LInteger "0"),e]
    (Just "+",_) -> apps (Var "addInt") [Lit (LInteger "0"),e]
    _ -> e
operand = letP <|> lambdaP <|> caseP <|> ifP <|> application
application = foldl1 App <$> many1 atom
atom = (parens (collection ")" expr >>= tuple (Var "Unit") (\n xs -> apps (Var n) xs)))
  <|> (foldr (\a b -> apps (Var "Cons") [a,b]) (Var "Nil") <$> between (sym "[") (sym "]") (collection "]" expr))
  <|> doP <|> (Lit <$> literal) <|> (Var <$> lowerRef) <|> (Var <$> upperRef)
ifP :: Parser Expr
ifP = do
  sym "if"
  (braces (sepEndBy (guardBranch "->") (sym ";")) >>= guards)
    <|> (If <$> expr <*> (sym "then" *> expr) <*> (sym "else" *> expr))
guardBranch :: String -> Parser (Maybe Expr,Expr)
guardBranch delimiter = do
  sym "|"
  condition <- (Nothing <$ try (sym "otherwise" <* lookAhead (sym delimiter))) <|> (Just <$> expr)
  sym delimiter
  body <- expr
  pure (condition,body)
guards :: [(Maybe Expr,Expr)] -> Parser Expr
guards [(Nothing,body)] = pure body
guards ((Just c,b):rest) = If c b <$> guards rest
guards _ = fail "implementation guards require one final otherwise branch"
letP :: Parser Expr
letP = Let <$> (sym "let" *> option False (True <$ sym "rec")) <*> valueBlock <*> (sym "in" *> expr)
lambdaP :: Parser Expr
lambdaP = Lambda <$> ((prefix "\\" <|> prefix "λ") *> many1 patternAtom <* (prefix "->" <|> prefix ".")) <*> expr
caseP :: Parser Expr
caseP = Case <$> (sym "case" *> expr) <*> (sym "of" *> braces (sepEndBy1 ((,) <$> patternP <*> (sym "->" *> expr)) (sym ";")))
doP :: Parser Expr
doP = Do <$> (sym "do" *> braces (sepEndBy1 statement (sym ";")))
statement :: Parser Statement
statement = try (Bind <$> patternP <*> (sym "<-" *> expr))
  <|> try (Local <$> (sym "let" *> option False (True <$ sym "rec")) <*> valueBlock <* lookAhead (sym ";" <|> sym "}"))
  <|> (Then <$> expr)
patternP, patternApp, patternAtom :: Parser Pattern
patternP = chainr1 patternApp ((\a b -> PCon "Cons" [a,b]) <$ sym ":")
patternApp = try (PCon <$> upperRef <*> many patternAtom) <|> patternAtom
patternAtom = parens (try (PAnn <$> lower <*> (annSym *> typeP) <* lookAhead (sym ")")) <|> (collection ")" patternP >>= tuple (PCon "Unit" []) PCon))
  <|> (foldr (\a b -> PCon "Cons" [a,b]) (PCon "Nil" []) <$> between (sym "[") (sym "]") (collection "]" patternP))
  <|> (PLit <$> literal) <|> (PLit . LInteger . ('-':) <$> try (sym "-" *> integer))
  <|> (PCon <$> upperRef <*> pure []) <|> (PWild <$ sym "_") <|> (PVar <$> lower)
literal :: Parser Literal
literal = (LBool True <$ (sym "true" <|> sym "True")) <|> (LBool False <$ (sym "false" <|> sym "False"))
  <|> (LString . spelling <$> tok (\s -> not (null s) && head s=='"'))
  <|> try (LDouble . spelling <$> tok (\s -> not (null s) && isDigit (head s) && take 2 s `notElem` ["0x","0X","0o","0O"] && any (`elem` ".eE") s))
  <|> (LInteger <$> integer)
integer :: Parser String
integer = spelling <$> tok (\s -> not (null s) && isDigit (head s))
collection :: String -> Parser a -> Parser [a]
collection closing item = ([] <$ lookAhead (sym closing)) <|> sepBy1 item (sym ",")
tuple :: a -> (String -> [a] -> a) -> [a] -> Parser a
tuple unit _ [] = pure unit
tuple _ _ [x] = pure x
tuple _ f xs | length xs <= 4 = pure (f (["Pair","Triple","Quad"] !! (length xs-2)) xs)
tuple _ _ _ = fail "implementation tuple supports 2-4 components"
