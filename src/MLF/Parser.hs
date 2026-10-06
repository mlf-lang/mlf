module MLF.Parser (parseProgram, parseExpr, parseAnnotation) where

import Control.Monad (void, when)
import Data.Char (isUpper)
import Data.List (nub)
import Text.Parsec
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok
import Text.Parsec.Language (emptyDef)
import MLF.Syntax
import MLF.Data.Parser (declaration, upperIdentifier, lowerIdentifier)
import MLF.Kind
import qualified MLF.Data as D

lexer :: Tok.TokenParser ()
lexer = Tok.makeTokenParser emptyDef
  { Tok.commentLine = "--"
  , Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True
  , Tok.identStart = letter
  , Tok.identLetter = alphaNum <|> oneOf "_'"
  , Tok.reservedNames = ["data","class","instance","where","case","of","do","let","in","forall","exists","true","false","True","False","bot"]
  , Tok.reservedOpNames = ["\\", "->", "<-", ".", ":", "=", ">=", ">", "|", "=>"]
  }

identifier :: Parser String
identifier = Tok.identifier lexer

reserved :: String -> Parser ()
reserved = Tok.reserved lexer

op :: String -> Parser ()
op = Tok.reservedOp lexer

symbol :: String -> Parser String
symbol = Tok.symbol lexer

parens :: Parser a -> Parser a
parens = Tok.parens lexer

parseExpr :: FilePath -> String -> Either String Expr
parseExpr file input = either (Left . show) Right (parse (Tok.whiteSpace lexer *> expr <* eof) file input)

parseProgram :: FilePath -> String -> Either String Program
parseProgram file input = either (Left . show) Right
  (parse (Tok.whiteSpace lexer *> program <* eof) file input)
  where
    program = do
      ds <- many (topDeclaration <* Tok.semi lexer)
      body <- expr
      let datatypes = [d | DataTop d <- ds]
          classes = [c | ClassTop c <- ds]
          instances = [i | InstanceTop i <- ds]
      pure (if null classes && null instances then Program datatypes body else ClassProgram datatypes classes instances body)

data Top = DataTop D.DataDecl | ClassTop ClassDecl | InstanceTop InstanceDecl

topDeclaration :: Parser Top
topDeclaration = (DataTop <$> declaration lexer) <|> (ClassTop <$> classDecl) <|> (InstanceTop <$> instanceDecl)

parameter :: Parser (String, Kind)
parameter = parens ((,) <$> lowerIdentifier lexer <*> (op ":" *> kindParser lexer))
        <|> ((\n -> (n,Star)) <$> lowerIdentifier lexer)

predicate :: Parser Predicate
predicate = Predicate <$> upperIdentifier lexer <*> many1 typeAtom

context :: Parser [Predicate]
context = try ((parens (predicate `sepBy1` Tok.comma lexer) <|> ((:[]) <$> predicate)) <* op "=>")

classDecl :: Parser ClassDecl
classDecl = do
  reserved "class"
  supers <- option [] context
  name <- upperIdentifier lexer
  params <- many1 parameter
  reserved "where"
  methods <- Tok.braces lexer (((,) <$> lowerIdentifier lexer <*> (op ":" *> typ)) `sepEndBy` Tok.semi lexer)
  pure (ClassDecl name params supers methods)

instanceDecl :: Parser InstanceDecl
instanceDecl = do
  reserved "instance"
  vars <- option [] (reserved "forall" *> many1 parameter <* op ".")
  givens <- option [] context
  name <- upperIdentifier lexer
  headType <- many1 typeAtom
  reserved "where"
  methods <- Tok.braces lexer (((,) <$> lowerIdentifier lexer <*> (op "=" *> expr)) `sepEndBy` Tok.semi lexer)
  pure (InstanceDecl vars givens name headType methods)

parseAnnotation :: String -> Either String Annotation
parseAnnotation input = either (Left . show) Right (parse (Tok.whiteSpace lexer *> annotation <* eof) "<type>" input)

expr :: Parser Expr
expr = letExpr <|> lambda <|> caseExpr <|> do
  e <- foldl1 App <$> many1 atom
  option e (Ann e <$> (op ":" *> annotation))

letExpr :: Parser Expr
letExpr = do
  reserved "let"
  x <- lowerIdentifier lexer
  a <- optionMaybe (op ":" *> annotation)
  op "="
  rhs <- expr
  reserved "in"
  body <- expr
  pure (Let x (maybe rhs (Ann rhs) a) body)

lambda :: Parser Expr
lambda = do
  void (symbol "\\" <|> symbol "λ")
  args <- many1 binder
  void (symbol "->" <|> symbol ".")
  body <- expr
  pure (foldr (\(n,a) b -> Lam n a b) body args)
  where
    binder = parens ((,) <$> lowerIdentifier lexer <*> optionMaybe (op ":" *> annotation))
          <|> ((\n -> (n, Nothing)) <$> lowerIdentifier lexer)

caseExpr :: Parser Expr
caseExpr = do
  reserved "case"
  scrutinee <- expr
  reserved "of"
  alternatives <- Tok.braces lexer (alternative `sepEndBy1` Tok.semi lexer)
  pure (Case scrutinee alternatives)
  where
    alternative = Alternative <$> patternP <*> (op "->" *> expr)

patternP :: Parser Pattern
patternP = try (parens (pure (ConstructorPattern "Unit" [])))
       <|> (ConstructorPattern <$> upperIdentifier lexer <*> many patternField)
       <|> (DefaultPattern <$> patternField)

patternField :: Parser (Maybe String)
patternField = (Nothing <$ Tok.lexeme lexer (char '_' <* notFollowedBy (alphaNum <|> oneOf "_'")))
           <|> (Just <$> lowerIdentifier lexer)

doExpr :: Parser Expr
doExpr = do
  reserved "do"
  statements <- Tok.braces lexer (statement `sepEndBy1` Tok.semi lexer)
  case reverse statements of
    DoThen result : rest -> pure (Do (reverse rest) result)
    _ -> fail "a do block must end with an expression"
  where
    statement = try (DoBind <$> patternP <*> (op "<-" *> expr))
            <|> try localLet
            <|> (DoThen <$> expr)
    localLet = do
      reserved "let"
      name <- lowerIdentifier lexer
      annotation' <- optionMaybe (op ":" *> annotation)
      op "="
      value <- expr
      -- A let/in expression is an action, not a do-local declaration.
      lookAhead (void (Tok.semi lexer) <|> void (symbol "}"))
      pure (DoLet name annotation' value)

atom :: Parser Expr
atom = parens (option (Constructor "Unit") expr)
   <|> doExpr
   <|> (BoolLit True <$ (reserved "true" <|> reserved "True"))
   <|> (BoolLit False <$ (reserved "false" <|> reserved "False"))
   <|> (IntLit <$> Tok.integer lexer)
   <|> (StringLit <$> Tok.stringLiteral lexer)
   <|> (Constructor <$> upperIdentifier lexer)
   <|> (Var <$> lowerIdentifier lexer)

annotation :: Parser Annotation
annotation = do
  vars <- option [] (reserved "exists" *> many1 identifier <* op ".")
  when (nub vars /= vars) (fail "duplicate existential variable")
  Annotation vars <$> typ

typ :: Parser Type
typ = quantified <|> (Qualified <$> context <*> typ) <|> chainr1 typeApp (Arrow <$ op "->")

quantified :: Parser Type
quantified = do
  reserved "forall"
  bs <- many1 typeBinder
  op "."
  t <- typ
  pure (foldr (\(f,n,b) body -> Forall f n b body) t bs)
  where
    typeBinder = parens (do
      n <- identifier
      mb <- optionMaybe $ do
        ((\k -> (Flexible,if k == Star then Bottom else BottomKind k)) <$> (op ":" *> kindParser lexer))
          <|> (do
            f <- (Flexible <$ (op ">=" <|> op ">")) <|> (Rigid <$ op "=")
            b <- typ
            pure (f,b))
      pure $ case mb of
        Nothing -> (Flexible,n,Bottom)
        Just (f,b) -> (f,n,b))
      <|> ((\n -> (Flexible,n,Bottom)) <$> identifier)

typeApp :: Parser Type
typeApp = foldl1 apply <$> many1 typeAtom
  where
    apply (Con c ts) t = Con c (ts ++ [t])
    apply f t = TypeApp f t

typeAtom :: Parser Type
typeAtom = parens (option (Con "Unit" []) typ)
       <|> (Bottom <$ (reserved "bot" <|> void (symbol "⊥")))
       <|> do
         n <- identifier
         pure $ case n of
           c:_ | isUpper c -> Con n []
           _ -> TVar n
