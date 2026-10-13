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
import MLF.Data.Parser (declaration, upperIdentifier, doubleLiteral)
import MLF.Kind
import MLF.Primitive (lookupTargetPrimitive)

lexer :: Tok.TokenParser ()
lexer = Tok.makeTokenParser emptyDef
  { Tok.commentLine = "--"
  , Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True
  , Tok.identStart = letter
  , Tok.identLetter = alphaNum <|> oneOf "_'"
  , Tok.reservedNames = ["data","construct","primitive","case","return","of","let","letrec","in","forall","true","false","True","False","bot","id","hyp","inner","outer","elim","intro"]
  , Tok.reservedOpNames = ["\\", "/\\", "->", ".", ":", "=", ">=", ";", "|"]
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
parseTerm = parseAll $ do
  ds <- many (declaration lexer <* Tok.semi lexer)
  body <- term
  pure (if null ds then body else WithData ds body)
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
    typeApplicationP = foldl1 apply <$> many1 typeAtom
    typeAtom = parens typ <|> (reserved "bot" *> option Bot (bottomKind <$> Tok.brackets lexer (kindParser lexer))) <|> do
      s <- lookAhead identifier
      case s of
        c:_ | isUpper c -> (`Con` []) <$> identifier
        _ -> Var <$> typeVariable

term :: Parser Term
term = letP <|> recP <|> typeAbsP <|> absP <|> caseP <|> (foldl1 App <$> many1 postfix)
  where
    recP = do
      reserved "letrec"
      bs <- Tok.braces lexer (binding `sepEndBy1` Tok.semi lexer)
      reserved "in"
      LetRec bs <$> term
    binding = (,,) <$> termVariable <*> (op ":" *> typ) <*> (op "=" *> term)
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
    caseP = do
      reserved "case"
      scrutinee <- term
      reserved "return"
      result <- typ
      reserved "of"
      Case scrutinee result <$> Tok.braces lexer (alternative `sepEndBy1` Tok.semi lexer)
    alternative = Alternative <$> patternP <*> (op "->" *> term)
    patternP = (ConstructorPattern <$> upperIdentifier lexer <*> many patternField)
           <|> (DefaultPattern <$> patternField)
    patternField = (Nothing <$ Tok.lexeme lexer (char '_' <* notFollowedBy (alphaNum <|> oneOf "_'")))
               <|> (Just <$> termVariable)
    postfix = do
      a <- atom
      ps <- many (Tok.brackets lexer computation)
      pure (foldl TypeApp a ps)
    atom = parens term
      <|> (BoolTerm True <$ reserved "true")
      <|> (BoolTerm False <$ reserved "false")
      <|> (DoubleTerm <$> (specialDoubleLiteral <|> doubleLiteral lexer))
      <|> (IntTerm <$> Tok.integer lexer)
      <|> (StringTerm <$> Tok.stringLiteral lexer)
      <|> (reserved "primitive" *> (do
        name <- identifier
        p <- maybe (fail ("unknown primitive: " ++ name)) pure (lookupTargetPrimitive name)
        Primitive p <$> parens (typ `sepBy` Tok.comma lexer)))
      <|> (reserved "construct" *> (Constructor <$> upperIdentifier lexer <*> parens (typ `sepBy` Tok.comma lexer)))
      <|> (VarTerm <$> termVariable)

-- The target printer also serializes deliberately invalid literals used by
-- verifier clients. Preserve those values so the independent checker makes
-- the rejection decision; the source language still rejects non-finite input.
specialDoubleLiteral :: Parser Double
specialDoubleLiteral = try $ do
  sign <- option id ((negate <$ op "-") <|> (id <$ op "+"))
  value <- (0 / 0 <$ reserved "NaN") <|> (1 / 0 <$ reserved "Infinity")
  pure (sign value)

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
      <|> (reserved "intro" *> parens (do
            a <- typeVariable
            option (Intro a) (IntroKind a <$> (op ":" *> kindParser lexer))))
