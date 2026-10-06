-- | Parser for the explicit, identity-bearing notation emitted by X.Pretty.
module MLF.X.Parser (parseTerm, parseType, parseComputation) where

import Control.Monad (void)
import Data.Char (isDigit, isUpper)
import Text.Parsec
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok
import Text.Parsec.Language (emptyDef)
import MLF.X.Syntax
import MLF.X.Type

lexer :: Tok.TokenParser ()
lexer = Tok.makeTokenParser emptyDef
  { Tok.commentLine = "--"
  , Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True
  , Tok.identStart = letter
  , Tok.identLetter = alphaNum <|> oneOf "_'"
  , Tok.reservedNames = ["let","in","forall","true","false","bot","id","hyp","inner","outer","elim","intro"]
  , Tok.reservedOpNames = ["\\", "/\\", "->", ".", ":", "=", ">=", ";"]
  }

identifier :: Parser String
identifier = Tok.identifier lexer
reserved :: String -> Parser ()
reserved = Tok.reserved lexer
op :: String -> Parser ()
op = Tok.reservedOp lexer
parens :: Parser a -> Parser a
parens = Tok.parens lexer

parseAll :: Parser a -> FilePath -> String -> Either String a
parseAll parser file input = either (Left . show) Right
  (parse (Tok.whiteSpace lexer *> parser <* eof) file input)

parseTerm :: FilePath -> String -> Either String Term
parseTerm = parseAll term
parseType :: String -> Either String Type
parseType = parseAll typ "<xMLF type>"
parseComputation :: String -> Either String Computation
parseComputation = parseAll computation "<xMLF computation>"

typeVariable :: Parser TyVar
typeVariable = do
  s <- identifier
  case s of
    prefix:ds | prefix `elem` "az", not (null ds), all isDigit ds -> do
      n <- decimal ds
      pure (TyVar (if prefix == 'z' then -n else n))
    _ -> fail "expected a type identity such as a12 (or z12 for a fresh negative identity)"

decimal :: String -> Parser Int
decimal s = case reads s :: [(Integer,String)] of
  [(n,"")] | n >= 0 && n <= toInteger (maxBound :: Int) -> pure (fromInteger n)
  _ -> fail "identity is outside the supported integer range"

termVariable :: Parser Name
termVariable = do
  s <- identifier
  case span isDigit (reverse s) of
    (digits,'_':hint) | not (null digits), not (null hint) ->
      (`Name` reverse hint) <$> decimal (reverse digits)
    _ -> fail "expected a term identity such as x_12"

typ :: Parser Type
typ = quantified <|> chainr1 typeApplicationP (Arrow <$ op "->")
  where
    quantified = do
      reserved "forall"
      (a,b) <- parens ((,) <$> typeVariable <*> (op ">=" *> typ))
        <|> ((\a -> (a,Bot)) <$> typeVariable)
      op "."
      Forall a b <$> typ
    typeApplicationP = do
      a <- typeAtom
      case a of Con c [] -> Con c <$> many typeAtom; _ -> pure a
    typeAtom = parens typ <|> (Bot <$ reserved "bot") <|> do
      s <- lookAhead identifier
      case s of
        c:_ | isUpper c -> (`Con` []) <$> identifier
        _ -> Var <$> typeVariable

term :: Parser Term
term = letP <|> typeAbsP <|> absP <|> (foldl1 App <$> many1 postfix)
  where
    letP = do
      reserved "let"
      n <- termVariable
      op "="
      a <- term
      reserved "in"
      Let n a <$> term
    typeAbsP = do
      op "/\\"
      (a,b) <- parens ((,) <$> typeVariable <*> (op ">=" *> typ))
      op "->"
      TypeAbs a b <$> term
    absP = do
      op "\\"
      (n,t) <- parens ((,) <$> termVariable <*> (op ":" *> typ))
      op "->"
      Abs n t <$> term
    postfix = do
      a <- atom
      ps <- many (Tok.brackets lexer computation)
      pure (foldl TypeApp a ps)
    atom = parens term
      <|> (BoolTerm True <$ reserved "true")
      <|> (BoolTerm False <$ reserved "false")
      <|> (IntTerm <$> Tok.integer lexer)
      <|> (VarTerm <$> termVariable)

computation :: Parser Computation
computation = chainl1 primitive (Then <$ op ";")
  where
    primitive = parens computation
      <|> (Refl <$ reserved "id")
      <|> (Bottom <$> (reserved "bot" *> parens typ))
      <|> (Hyp <$> (reserved "hyp" *> parens typeVariable))
      <|> (Inner <$> (reserved "inner" *> parens computation))
      <|> (reserved "outer" *> parens (do
            a <- typeVariable
            void (Tok.comma lexer)
            Outer a <$> computation))
      <|> (Elim <$ reserved "elim")
      <|> (Intro <$> (reserved "intro" *> parens typeVariable))

