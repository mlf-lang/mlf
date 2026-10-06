module MLF.Parser (parseExpr, parseAnnotation) where

import Control.Monad (void, when)
import Data.Char (isUpper)
import Data.List (nub)
import Text.Parsec
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok
import Text.Parsec.Language (emptyDef)
import MLF.Syntax

lexer :: Tok.TokenParser ()
lexer = Tok.makeTokenParser emptyDef
  { Tok.commentLine = "--"
  , Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True
  , Tok.identStart = letter
  , Tok.identLetter = alphaNum <|> oneOf "_'"
  , Tok.reservedNames = ["let","in","forall","exists","true","false","True","False","bot"]
  , Tok.reservedOpNames = ["\\", "->", ".", ":", "=", ">=", ">"]
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

parseAnnotation :: String -> Either String Annotation
parseAnnotation input = either (Left . show) Right (parse (Tok.whiteSpace lexer *> annotation <* eof) "<type>" input)

expr :: Parser Expr
expr = letExpr <|> lambda <|> do
  e <- foldl1 App <$> many1 atom
  option e (Ann e <$> (op ":" *> annotation))

letExpr :: Parser Expr
letExpr = do
  reserved "let"
  x <- identifier
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
    binder = parens ((,) <$> identifier <*> optionMaybe (op ":" *> annotation))
          <|> ((\n -> (n, Nothing)) <$> identifier)

atom :: Parser Expr
atom = parens expr
   <|> (BoolLit True <$ (reserved "true" <|> reserved "True"))
   <|> (BoolLit False <$ (reserved "false" <|> reserved "False"))
   <|> (IntLit <$> Tok.integer lexer)
   <|> (Var <$> identifier)

annotation :: Parser Annotation
annotation = do
  vars <- option [] (reserved "exists" *> many1 identifier <* op ".")
  when (nub vars /= vars) (fail "duplicate existential variable")
  Annotation vars <$> typ

typ :: Parser Type
typ = quantified <|> chainr1 typeApp (Arrow <$ op "->")

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
        f <- (Flexible <$ (op ">=" <|> op ">")) <|> (Rigid <$ op "=")
        b <- typ
        pure (f,b)
      pure $ case mb of
        Nothing -> (Flexible,n,Bottom)
        Just (f,b) -> (f,n,b))
      <|> ((\n -> (Flexible,n,Bottom)) <$> identifier)

typeApp :: Parser Type
typeApp = do
  t <- typeAtom
  case t of
    Con c [] -> Con c <$> many typeAtom
    _ -> pure t

typeAtom :: Parser Type
typeAtom = parens typ
       <|> (Bottom <$ (reserved "bot" <|> void (symbol "⊥")))
       <|> do
         n <- identifier
         pure $ case n of
           c:_ | isUpper c -> Con n []
           _ -> TVar n
