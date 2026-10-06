module MLF.Data.Parser (declaration, upperIdentifier, lowerIdentifier) where

import Data.Char (isLower, isUpper)
import Text.Parsec
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok
import MLF.Data
import MLF.Kind

upperIdentifier :: Tok.TokenParser () -> Parser String
upperIdentifier lexer = do
  n <- lookAhead (Tok.identifier lexer)
  case n of
    c:_ | isUpper c -> Tok.identifier lexer
    _ -> unexpected "lowercase constructor name"

lowerIdentifier :: Tok.TokenParser () -> Parser String
lowerIdentifier lexer = do
  n <- lookAhead (Tok.identifier lexer)
  case n of
    c:_ | isLower c -> Tok.identifier lexer
    _ -> unexpected "uppercase variable name"

-- Field applications and arrows are parenthesized in a constructor's argument
-- list, following the ordinary prefix data declaration syntax.
declaration :: Tok.TokenParser () -> Parser DataDecl
declaration lexer = do
  Tok.reserved lexer "data"
  n <- upperName
  ps <- many parameter
  Tok.reservedOp lexer "="
  cs <- constructor `sepBy1` Tok.reservedOp lexer "|"
  pure (if all ((== Star) . snd) ps then DataDecl n (map fst ps) cs else DataDeclK n ps cs)
  where
    -- Declaration parameters are schematic source names even in xMLF. In
    -- particular, names such as "id" are not target computation keywords here.
    name = Tok.lexeme lexer $ try $ do
      n <- (:) <$> letter <*> many (alphaNum <|> oneOf "_'")
      if n `elem` ["data","class","instance","where","case","of","let","in","forall","exists","true","false","bot"]
        then unexpected ("reserved word " ++ n) else pure n
    upperName = do
      n <- lookAhead name
      case n of c:_ | isUpper c -> name; _ -> unexpected "lowercase constructor name"
    lowerName = do
      n <- lookAhead name
      case n of c:_ | isLower c -> name; _ -> unexpected "uppercase variable name"
    constructor = ConstructorDecl <$> upperName <*> many atom
    parameter = Tok.parens lexer ((,) <$> lowerName <*> (Tok.reservedOp lexer ":" *> kindParser lexer))
            <|> ((\n -> (n,Star)) <$> lowerName)
    typ = quantified <|> chainr1 application (Function <$ Tok.reservedOp lexer "->")
    quantified = do
      Tok.reserved lexer "forall"
      bs <- many1 parameter
      Tok.reservedOp lexer "."
      b <- typ
      pure (foldr (uncurry Quantified) b bs)
    application = foldl1 apply <$> many1 atom
    apply (Applied c args) a = Applied c (args ++ [a])
    apply f a = Application f a
    atom = Tok.parens lexer typ
       <|> ((`Applied` []) <$> upperName)
       <|> (Parameter <$> lowerName)
