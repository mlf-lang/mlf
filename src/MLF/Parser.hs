module MLF.Parser (parseProgram, parseModule, parseExpr, parseAnnotation) where

import Control.Monad (void, when)
import Data.List (intercalate, nub)
import Text.Parsec
import Text.Parsec.Expr (Assoc (..), Operator (..), buildExpressionParser)
import Text.Parsec.String (Parser)
import qualified Text.Parsec.Token as Tok
import Text.Parsec.Language (emptyDef)
import MLF.Syntax
import MLF.Data.Parser (sourceDeclaration, upperIdentifier, lowerIdentifier, doubleLiteral)
import MLF.Module.Syntax
import MLF.Kind
import qualified MLF.Data as D
import qualified MLF.Primitive as P
import qualified MLF.Layout as Layout
import qualified MLF.Surface as Surface

lexer :: Tok.TokenParser ()
lexer = Tok.makeTokenParser emptyDef
  { Tok.commentLine = "--"
  , Tok.commentStart = "{-", Tok.commentEnd = "-}", Tok.nestedComments = True
  , Tok.identStart = letter
  , Tok.identLetter = alphaNum <|> oneOf "_'"
  , Tok.reservedNames = ["data","class","instance","where","case","of","do","let","rec","in","if","then","else","forall","exists","true","false","True","False","bot","module","import"]
  , Tok.reservedOpNames = ["\\", "->", "<-", ".", ":", "=", ">=", ">", "|", "=>",
      "+", "-", "*", "/", "%", "++", "==", "/=", "<", "<=", "&&", "||"]
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
parseExpr = parseLayout False expr

parseLayout :: Bool -> Parser a -> FilePath -> String -> Either String a
parseLayout program parser file input = do
  (source,positions) <- Layout.layoutSource program file input
  either (Left . Layout.originalError positions) Right
    (parse (Tok.whiteSpace lexer *> parser <* eof) file source)

parseProgram :: FilePath -> String -> Either String Program
parseProgram file input = do
  m <- parseModule file input
  when (sourceModuleName m /= Nothing || not (null (sourceImports m)))
    (Left "use parseModule and module-aware compilation for module declarations or imports")
  standaloneProgram m

parseModule :: FilePath -> String -> Either String SourceModule
parseModule file = parseLayout True sourceModule file
  where
    sourceModule = do
      header <- optionMaybe $ do
        reserved "module"
        name <- moduleName
        exports <- optionMaybe (Tok.parens lexer (exportItem True `sepEndBy` Tok.comma lexer))
        reserved "where"
        pure (name,exports)
      Tok.braces lexer $ do
        imports <- many (importDeclaration <* separator)
        (ds,values,body) <- contents
        when (header /= Nothing && body /= Nothing)
          (fail "named modules contain declarations only; define main for the entry point")
        pure (SourceModule file (fst <$> header) (header >>= snd) imports
          [d | DataTop d <- ds] [c | ClassTop c <- ds] [i | InstanceTop i <- ds] values body)
    separator = void (Tok.semi lexer) <|> void (lookAhead (symbol "}"))
    contents = do
      ds <- many (topDeclaration <* (void (Tok.semi lexer) <|> void (lookAhead (symbol "}"))))
      values <- either fail pure (groupValues [v | ValueTop v <- ds])
      body <- optionMaybe expr
      pure (ds,values,body)

moduleName :: Parser String
moduleName = intercalate "." <$> (upperIdentifier lexer `sepBy1` symbol ".")

qualified :: Parser String -> Parser String
qualified final = do
  prefix <- many (try (upperIdentifier lexer <* symbol "."))
  name <- final
  pure (intercalate "." (prefix ++ [name]))

upperReference, lowerReference :: Parser String
upperReference = qualified (upperIdentifier lexer
  <|> ("True" <$ reserved "True") <|> ("False" <$ reserved "False"))
lowerReference = try (qualified (lowerIdentifier lexer))

exportItem :: Bool -> Parser Export
exportItem exporting =
  (if exporting then ExportModule <$> (reserved "module" *> moduleName) else parserZero)
  <|> (ExportValue <$> (if exporting then lowerReference else lowerIdentifier lexer))
  <|> (ExportType <$> (if exporting then upperReference else upperIdentifier lexer) <*> members)
  where
    members = option Abstract (Tok.parens lexer
      ((AllMembers <$ symbol "..") <|> (Members <$> (member `sepEndBy` Tok.comma lexer))))
    member = identifier <|> ("True" <$ reserved "True") <|> ("False" <$ reserved "False")

importDeclaration :: Parser Import
importDeclaration = do
  reserved "import"
  qualifiedOnly <- option False (True <$ reserved "qualified")
  name <- moduleName
  alias <- optionMaybe (reserved "as" *> moduleName)
  selection <- option Everything
    ((Hiding <$> (reserved "hiding" *> items)) <|> (Only <$> items))
  pure (Import name qualifiedOnly alias selection)
  where items = Tok.parens lexer (exportItem False `sepEndBy` Tok.comma lexer)

data Top = DataTop D.DataDecl | ClassTop ClassDecl | InstanceTop InstanceDecl | ValueTop Value

data Value = Signature String Annotation | Equation String [Pattern] (Maybe Annotation) Expr

topDeclaration :: Parser Top
topDeclaration = (DataTop <$> sourceDeclaration lexer) <|> (ClassTop <$> classDecl)
  <|> (InstanceTop <$> instanceDecl) <|> (ValueTop <$> valueDeclaration)

-- Signatures precede their equation immediately. Only the header backtracks:
-- once '=' has been read, a malformed body must remain a declaration error.
valueDeclaration :: Parser Value
valueDeclaration = try (Signature <$> lowerIdentifier lexer <*> (op ":" *> annotation)
    <* lookAhead (Tok.semi lexer)) <|> equation

equation :: Parser Value
equation = do
  (name,args,a) <- bindingHead
  Equation name args a <$> expr

groupValues :: [Value] -> Either String [(String,Maybe Annotation,Expr)]
groupValues declarations = do
  values <- collect Nothing declarations
  let names = [n | (n,_,_) <- values]
  when (nub names /= names) (Left "function equations must be contiguous; duplicate value declaration")
  pure values
  where
    collect Nothing [] = pure []
    collect (Just (n,_)) [] = Left ("signature without a definition: " ++ n)
    collect (Just _) (Signature n _:_) = Left ("duplicate signature for " ++ n)
    collect Nothing (Signature n a:rest) = collect (Just (n,a)) rest
    collect signature (Equation n ps inline b:rest) = do
      a <- case signature of
        Nothing -> pure inline
        Just (signedName,ty) -> do
          when (signedName /= n) (Left ("expected a definition of " ++ signedName))
          when (inline /= Nothing) (Left ("duplicate signature for " ++ n))
          pure (Just ty)
      let same (Equation name _ _ _) = name == n
          same _ = False
          (more,remaining) = span same rest
          rows = (ps,b) : [(args,rhs) | Equation _ args _ rhs <- more]
      when (any (\v -> case v of Equation _ _ annotation' _ -> annotation' /= Nothing; _ -> False) more)
        (Left ("duplicate signature for " ++ n))
      when (not (null more) && null ps) (Left "multiple equations require function parameters")
      when (any ((/= length ps) . length . fst) rows) (Left "function equations have different arities")
      ((n,a,Surface.function rows):) <$> collect Nothing remaining

bindingHead :: Parser (String, [Pattern], Maybe Annotation)
bindingHead = do
  (name,args,a) <- try $ do
    name <- lowerIdentifier lexer
    args <- many patternAtom
    a <- optionMaybe (op ":" *> annotation)
    op "="
    pure (name,args,a)
  let names = concatMap Surface.patternVariables args
  when (nub names /= names) (fail "duplicate function parameter")
  pure (name,args,a)

valueBlock :: Parser [(String,Maybe Annotation,Expr)]
valueBlock = do
  values <- Tok.braces lexer (valueDeclaration `sepEndBy1` Tok.semi lexer) <|> ((:[]) <$> equation)
  either fail pure (groupValues values)

bindLocal :: Bool -> [(String,Maybe Annotation,Expr)] -> Expr -> Parser Expr
bindLocal recursive values body
  | recursive = (\ds -> LetRec ds body) <$> either fail pure (Surface.recursiveValues values)
  | otherwise = pure (foldr (\(n,a,e) b -> Let n (maybe e (Ann e) a) b) body values)

parameter :: Parser (String, Kind)
parameter = parens ((,) <$> lowerIdentifier lexer <*> (op ":" *> kindParser lexer))
        <|> ((\n -> (n,Star)) <$> lowerIdentifier lexer)

predicate :: Parser Predicate
predicate = Predicate <$> upperReference <*> many1 typeAtom

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
  name <- upperReference
  headType <- many1 typeAtom
  reserved "where"
  declarations <- Tok.braces lexer (valueDeclaration `sepEndBy` Tok.semi lexer)
  methods <- case traverse simple declarations of
    Just ms -> pure ms
    Nothing -> do
      values <- either fail pure (groupValues declarations)
      pure [(n,maybe e (Ann e) a) | (n,a,e) <- values]
  pure (InstanceDecl vars givens name headType methods)
  where
    simple (Equation n [] a e) = Just (n,maybe e (Ann e) a)
    simple _ = Nothing

parseAnnotation :: String -> Either String Annotation
parseAnnotation input = either (Left . show) Right (parse (Tok.whiteSpace lexer *> annotation <* eof) "<type>" input)

expr :: Parser Expr
expr = do
  e <- buildExpressionParser operators operand
  option e (Ann e <$> (op ":" *> annotation))
  where
    operand = letExpr <|> lambda <|> caseExpr <|> ifExpr <|> (foldl1 App <$> many1 atom)
    operators =
      [ [Prefix (negateValue <$ op "-"), Prefix (positiveValue <$ op "+")]
      , [binary "*" (primitive2 P.MulInt) AssocLeft,
         binary "/" (primitive2 P.QuotInt) AssocLeft,
         binary "%" (primitive2 P.RemInt) AssocLeft]
      , [binary "+" (primitive2 P.AddInt) AssocLeft,
         binary "-" (primitive2 P.SubInt) AssocLeft]
      , [binary "++" (primitive2 P.ConcatString) AssocRight]
      , [binary "==" (primitive2 P.EqInt) AssocNone,
         binary "/=" (\a b -> notValue (primitive2 P.EqInt a b)) AssocNone,
         binary "<" (primitive2 P.LtInt) AssocNone,
         binary "<=" (\a b -> notValue (primitive2 P.LtInt b a)) AssocNone,
         binary ">" (flip (primitive2 P.LtInt)) AssocNone,
         binary ">=" (\a b -> notValue (primitive2 P.LtInt a b)) AssocNone]
      , [binary "&&" (\a b -> conditional a b (BoolLit False)) AssocRight]
      , [binary "||" (\a b -> conditional a (BoolLit True) b) AssocRight]
      ]
    binary name f associativity = Infix (f <$ op name) associativity
    notValue a = conditional a (BoolLit False) (BoolLit True)
    negateValue (IntLit n) = IntLit (negate n)
    negateValue (DoubleLit n) = DoubleLit (negate n)
    negateValue a = primitive2 P.SubInt (IntLit 0) a
    positiveValue a@(IntLit _) = a
    positiveValue a@(DoubleLit _) = a
    positiveValue a = primitive2 P.AddInt (IntLit 0) a

-- Built-in syntax carries primitive identities, so a local binding named
-- addInt or ifThenElse cannot capture a generated operation.
primitive2 :: P.Primitive -> Expr -> Expr -> Expr
primitive2 p a b = App (App (Primitive p) a) b

conditional :: Expr -> Expr -> Expr -> Expr
conditional condition yes no = App (primitive2 P.IfThenElse condition yes) no

ifExpr :: Parser Expr
ifExpr = conditional <$> (reserved "if" *> expr)
  <*> (reserved "then" *> expr) <*> (reserved "else" *> expr)

letExpr :: Parser Expr
letExpr = do
  reserved "let"
  recursive <- option False (True <$ reserved "rec")
  values <- valueBlock
  reserved "in"
  body <- expr
  bindLocal recursive values body

lambda :: Parser Expr
lambda = do
  void (symbol "\\" <|> symbol "λ")
  args <- many1 patternAtom
  void (symbol "->" <|> symbol ".")
  body <- expr
  let names = concatMap Surface.patternVariables args
  when (nub names /= names) (fail "duplicate pattern variable")
  pure (Surface.function [(args,body)])

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
patternP = try (do
    name <- upperReference
    fields <- many patternAtom
    pure (constructorPattern name fields))
  <|> patternAtom

constructorPattern :: String -> [Pattern] -> Pattern
constructorPattern "True" [] = BoolPattern True
constructorPattern "False" [] = BoolPattern False
constructorPattern name fields
  | all variable fields = ConstructorPattern name [n | DefaultPattern n <- fields]
  | otherwise = NestedPattern name fields
  where
    variable (DefaultPattern _) = True
    variable _ = False

patternAtom :: Parser Pattern
patternAtom = parens (option (ConstructorPattern "Unit" []) $ do
      p <- patternP
      a <- optionMaybe (op ":" *> annotation)
      case (p,a) of
        (_,Nothing) -> pure p
        (DefaultPattern (Just n),Just ty) -> pure (AnnotatedPattern n ty)
        _ -> fail "only variable patterns can be annotated")
  <|> (BoolPattern True <$ (reserved "true" <|> reserved "True"))
  <|> (BoolPattern False <$ (reserved "false" <|> reserved "False"))
  <|> (IntPattern <$> try (Tok.integer lexer))
  <|> (StringPattern <$> Tok.stringLiteral lexer)
  <|> ((\n -> ConstructorPattern n []) <$> upperReference)
  <|> (DefaultPattern <$> patternField)

patternField :: Parser (Maybe String)
patternField = (Nothing <$ Tok.lexeme lexer (char '_' <* notFollowedBy (alphaNum <|> oneOf "_'")))
           <|> (Just <$> lowerIdentifier lexer)

doExpr :: Parser Expr
doExpr = do
  reserved "do"
  statements <- concat <$> Tok.braces lexer (statement `sepEndBy1` Tok.semi lexer)
  case reverse statements of
    DoThen result : rest -> pure (Do (reverse rest) result)
    _ -> fail "a do block must end with an expression"
  where
    statement = try ((:[]) <$> (DoBind <$> patternP <*> (op "<-" *> expr)))
            <|> try localLet
            <|> ((:[]) <$> (DoThen <$> expr))
    localLet = do
      reserved "let"
      recursive <- option False (True <$ reserved "rec")
      values <- valueBlock
      -- A let/in expression is an action, not a do-local declaration.
      lookAhead (void (Tok.semi lexer) <|> void (symbol "}"))
      if recursive
        then (\ds -> [DoLetRec ds]) <$> either fail pure (Surface.recursiveValues values)
        else pure [DoLet n a e | (n,a,e) <- values]

atom :: Parser Expr
atom = parens (option (Constructor "Unit") expr)
   <|> doExpr
   <|> (BoolLit True <$ (reserved "true" <|> reserved "True"))
   <|> (BoolLit False <$ (reserved "false" <|> reserved "False"))
   -- Signs are expression operators. Otherwise x-1 would parse as x (-1).
   <|> (DoubleLit <$> (notFollowedBy (oneOf "+-") *> doubleLiteral lexer))
   <|> (IntLit <$> Tok.natural lexer)
   <|> (StringLit <$> Tok.stringLiteral lexer)
   <|> (Var <$> lowerReference)
   <|> (Constructor <$> upperReference)

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
       <|> (TVar <$> lowerIdentifier lexer)
       <|> ((\n -> Con n []) <$> upperReference)
