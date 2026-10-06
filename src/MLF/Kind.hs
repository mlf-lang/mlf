module MLF.Kind (Kind (..), prettyKind, applyKind, kindParser) where

import Text.Parsec
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok

data Kind = Star | KArrow Kind Kind deriving (Eq, Ord, Show)

prettyKind :: Kind -> String
prettyKind Star = "*"
prettyKind (KArrow a b) = left a ++ " -> " ++ prettyKind b
  where
    left Star = "*"
    left k = "(" ++ prettyKind k ++ ")"

applyKind :: Kind -> Kind -> Either String Kind
applyKind (KArrow domain result) argument
  | domain == argument = Right result
  | otherwise = Left ("kind mismatch: expected " ++ prettyKind domain ++ ", got " ++ prettyKind argument)
applyKind Star _ = Left "invalid type constructor arity: a type of kind * cannot be applied"

kindParser :: Tok.TokenParser () -> Parser Kind
kindParser lexer = chainr1 atom (KArrow <$ Tok.reservedOp lexer "->")
  where atom = (Star <$ Tok.symbol lexer "*") <|> Tok.parens lexer (kindParser lexer)
