-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceEquality where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Primitive as P;
  eqSourceString :: SourceString -> SourceString -> Bool;
  eqSourceString a b = case a of {
    ScalarString x -> case b of { ScalarString y -> eqString x y; _ -> False };
    CharString x -> case b of { CharString y -> L.eqList eqInt x y; _ -> False }
  };
  eqBool :: Bool -> Bool -> Bool;
  eqBool a b = if a then b else L.not b;
  eqTriple :: forall a b c. (a -> a -> Bool) ->
                            (b -> b -> Bool) ->
                            (c -> c -> Bool) -> (,,) a b c -> (,,) a b c -> Bool;
  eqTriple ea eb ec ((,,) a b c) ((,,) x y z) = (ea a x && (eb b y && ec c z));
  eqField :: Field -> Field -> Bool;
  eqField a b =
    case a of {
      Parameter x0 ->
        case b of {
          Parameter y0 -> eqString x0 y0;
          _ -> False
        };
      Function x0 x1 ->
        case b of {
          Function y0 y1 -> (eqField x0 y0 && eqField x1 y1);
          _ -> False
        };
      Applied x0 x1 ->
        case b of {
          Applied y0 y1 -> (eqString x0 y0 && L.eqList eqField x1 y1);
          _ -> False
        };
      Application x0 x1 ->
        case b of {
          Application y0 y1 -> (eqField x0 y0 && eqField x1 y1);
          _ -> False
        };
      Quantified x0 x1 x2 ->
        case b of {
          Quantified y0 y1 y2 -> (eqString x0 y0 && (L.eqKind x1 y1 && eqField x2 y2));
          _ -> False
        }
    };
  eqConstructorDecl :: ConstructorDecl -> ConstructorDecl -> Bool;
  eqConstructorDecl a b =
    case a of {
      ConstructorDecl x0 x1 ->
        case b of {
          ConstructorDecl y0 y1 -> (eqString x0 y0 && L.eqList eqField x1 y1)
        }
    };
  eqDataDecl :: DataDecl -> DataDecl -> Bool;
  eqDataDecl a b =
    case a of {
      DataDecl x0 x1 x2 ->
        case b of {
          DataDecl y0 y1 y2 ->
            (eqString x0 y0 && (L.eqList eqString x1 y1 && L.eqList eqConstructorDecl x2 y2));
          _ -> False
        };
      DataDeclK x0 x1 x2 ->
        case b of {
          DataDeclK y0 y1 y2 ->
            (eqString x0 y0 &&
             (L.eqList (L.eqPair eqString L.eqKind) x1 y1 && L.eqList eqConstructorDecl x2 y2));
          _ -> False
        }
    };
  eqSType :: SType -> SType -> Bool;
  eqSType a b =
    case a of {
      STVar x0 ->
        case b of {
          STVar y0 -> eqString x0 y0;
          _ -> False
        };
      SBottom ->
        case b of {
          SBottom -> True;
          _ -> False
        };
      SBottomKind x0 ->
        case b of {
          SBottomKind y0 -> L.eqKind x0 y0;
          _ -> False
        };
      SArrow x0 x1 ->
        case b of {
          SArrow y0 y1 -> (eqSType x0 y0 && eqSType x1 y1);
          _ -> False
        };
      SCon x0 x1 ->
        case b of {
          SCon y0 y1 -> (eqString x0 y0 && L.eqList eqSType x1 y1);
          _ -> False
        };
      STypeApp x0 x1 ->
        case b of {
          STypeApp y0 y1 -> (eqSType x0 y0 && eqSType x1 y1);
          _ -> False
        };
      SForall x0 x1 x2 x3 ->
        case b of {
          SForall y0 y1 y2 y3 ->
            (L.eqFlag x0 y0 && (eqString x1 y1 && (eqSType x2 y2 && eqSType x3 y3)));
          _ -> False
        };
      SQualified x0 x1 ->
        case b of {
          SQualified y0 y1 -> (L.eqList eqSPredicate x0 y0 && eqSType x1 y1);
          _ -> False
        }
    };
  eqSAnnotation :: SAnnotation -> SAnnotation -> Bool;
  eqSAnnotation a b =
    case a of {
      SAnnotation x0 x1 ->
        case b of {
          SAnnotation y0 y1 -> (L.eqList eqString x0 y0 && eqSType x1 y1)
        }
    };
  eqRecursiveMode :: RecursiveMode -> RecursiveMode -> Bool;
  eqRecursiveMode a b =
    case a of {
      InferRecursive ->
        case b of {
          InferRecursive -> True;
          _ -> False
        };
      CheckRecursive annotation ->
        case b of {
          CheckRecursive other -> eqSAnnotation annotation other;
          _ -> False
        }
    };
  eqSExpr :: SExpr -> SExpr -> Bool;
  eqSExpr a b =
    case a of {
      SVar x0 ->
        case b of {
          SVar y0 -> eqString x0 y0;
          _ -> False
        };
      SConstructor x0 ->
        case b of {
          SConstructor y0 -> eqString x0 y0;
          _ -> False
        };
      SLam x0 x1 x2 ->
        case b of {
          SLam y0 y1 y2 -> (eqString x0 y0 && (L.eqMaybe eqSAnnotation x1 y1 && eqSExpr x2 y2));
          _ -> False
        };
      SApp x0 x1 ->
        case b of {
          SApp y0 y1 -> (eqSExpr x0 y0 && eqSExpr x1 y1);
          _ -> False
        };
      SLet x0 x1 x2 ->
        case b of {
          SLet y0 y1 y2 -> (eqString x0 y0 && (eqSExpr x1 y1 && eqSExpr x2 y2));
          _ -> False
        };
      SAnn x0 x1 ->
        case b of {
          SAnn y0 y1 -> (eqSExpr x0 y0 && eqSAnnotation x1 y1);
          _ -> False
        };
      SSignature x0 x1 ->
        case b of {
          SSignature y0 y1 -> (eqSExpr x0 y0 && eqSAnnotation x1 y1);
          _ -> False
        };
      SIntLit x0 ->
        case b of {
          SIntLit y0 -> eqInt x0 y0;
          _ -> False
        };
      SDoubleLit x0 ->
        case b of {
          SDoubleLit y0 -> eqDouble x0 y0;
          _ -> False
        };
      SBoolLit x0 ->
        case b of {
          SBoolLit y0 -> eqBool x0 y0;
          _ -> False
        };
      SStringLit x0 ->
        case b of {
          SStringLit y0 -> eqString x0 y0;
          _ -> False
        };
      SPrimitive x0 ->
        case b of {
          SPrimitive y0 -> P.eqPrimitive x0 y0;
          _ -> False
        };
      SCase x0 x1 ->
        case b of {
          SCase y0 y1 -> (eqSExpr x0 y0 && L.eqList eqSAlternative x1 y1);
          _ -> False
        };
      SSourceDefinition body ->
        case b of {
          SSourceDefinition body2 -> eqSExpr body body2;
          _ -> False
        };
      SCallSite label span body ->
        case b of {
          SCallSite label2 span2 body2 ->
            (eqString label label2 && (eqSourceSpan span span2 && eqSExpr body body2));
          _ -> False
        };
      SSharedBind pattern action continuation bindMethod failure ->
        case b of {
          SSharedBind pattern2 action2 continuation2 bindMethod2 failure2 ->
            (eqSPattern pattern pattern2 && (eqSExpr action action2 &&
             (eqSExpr continuation continuation2 && (eqSExpr bindMethod bindMethod2 &&
              eqSExpr failure failure2))));
          _ -> False
        };
      SDo x0 x1 ->
        case b of {
          SDo y0 y1 -> (L.eqList eqSStatement x0 y0 && eqSExpr x1 y1);
          _ -> False
        };
      SEquations x0 ->
        case b of {
          SEquations y0 -> L.eqList (L.eqPair (L.eqList eqSPattern) eqSExpr) x0 y0;
          _ -> False
        };
      SLetRec x0 x1 ->
        case b of {
          SLetRec y0 y1 ->
            (L.eqList (eqTriple eqString eqRecursiveMode eqSExpr) x0 y0 && eqSExpr x1 y1);
          _ -> False
        };
      SWanted x0 x1 ->
        case b of {
          SWanted y0 y1 -> (eqString x0 y0 && L.eqList (L.eqPair eqEvidenceRole eqString) x1 y1);
          _ -> False
        };
      SChecked x0 x1 ->
        case b of {
          SChecked y0 y1 -> (eqSType x0 y0 && eqSExpr x1 y1);
          _ -> False
        }
    };
  eqSPattern :: SPattern -> SPattern -> Bool;
  eqSPattern a b =
    case a of {
      SConstructorPattern x0 x1 ->
        case b of {
          SConstructorPattern y0 y1 -> (eqString x0 y0 && L.eqList (L.eqMaybe eqString) x1 y1);
          _ -> False
        };
      SDefaultPattern x0 ->
        case b of {
          SDefaultPattern y0 -> L.eqMaybe eqString x0 y0;
          _ -> False
        };
      SNestedPattern x0 x1 ->
        case b of {
          SNestedPattern y0 y1 -> (eqString x0 y0 && L.eqList eqSPattern x1 y1);
          _ -> False
        };
      SAnnotatedPattern x0 x1 ->
        case b of {
          SAnnotatedPattern y0 y1 -> (eqString x0 y0 && eqSAnnotation x1 y1);
          _ -> False
        };
      SIntPattern x0 ->
        case b of {
          SIntPattern y0 -> eqInt x0 y0;
          _ -> False
        };
      SStringPattern x0 ->
        case b of {
          SStringPattern y0 -> eqString x0 y0;
          _ -> False
        };
      SOverloadedStringPattern x0 x1 x2 ->
        case b of {
          SOverloadedStringPattern y0 y1 y2 ->
            (eqSourceString x0 y0 && (eqString x1 y1 && eqString x2 y2));
          _ -> False
        };
      SAsPattern n pattern ->
        case b of {
          SAsPattern n2 pattern2 -> (eqString n n2 && eqSPattern pattern pattern2);
          _ -> False
        };
      SLazyPattern pattern ->
        case b of { SLazyPattern pattern2 -> eqSPattern pattern pattern2; _ -> False };
      SBoolPattern x0 ->
        case b of {
          SBoolPattern y0 -> eqBool x0 y0;
          _ -> False
        }
    };
  eqSAlternative :: SAlternative -> SAlternative -> Bool;
  eqSAlternative a b =
    case a of {
      SAlternative x0 x1 ->
        case b of {
          SAlternative y0 y1 -> (eqSPattern x0 y0 && eqSExpr x1 y1)
        }
    };
  eqSStatement :: SStatement -> SStatement -> Bool;
  eqSStatement a b =
    case a of {
      SDoBind x0 x1 ->
        case b of {
          SDoBind y0 y1 -> (eqSPattern x0 y0 && eqSExpr x1 y1);
          _ -> False
        };
      SDoThen x0 ->
        case b of {
          SDoThen y0 -> eqSExpr x0 y0;
          _ -> False
        };
      SDoLet x0 x1 x2 ->
        case b of {
          SDoLet y0 y1 y2 -> (eqString x0 y0 && (L.eqMaybe eqSAnnotation x1 y1 && eqSExpr x2 y2));
          _ -> False
        };
      SDoLetRec x0 ->
        case b of {
          SDoLetRec y0 -> L.eqList (eqTriple eqString eqRecursiveMode eqSExpr) x0 y0;
          _ -> False
        }
    };
  eqSPredicate :: SPredicate -> SPredicate -> Bool;
  eqSPredicate a b =
    case a of {
      SPredicate x0 x1 ->
        case b of {
          SPredicate y0 y1 -> (eqString x0 y0 && L.eqList eqSType x1 y1)
        }
    };
  eqSClassDecl :: SClassDecl -> SClassDecl -> Bool;
  eqSClassDecl a b =
    case a of {
      SClassDecl x0 x1 x2 x3 ->
        case b of {
          SClassDecl y0 y1 y2 y3 ->
            (eqString x0 y0 &&
             (L.eqList (L.eqPair eqString L.eqKind) x1 y1 &&
              (L.eqList eqSPredicate x2 y2 && L.eqList (L.eqPair eqString eqSType) x3 y3)))
        }
    };
  eqSInstanceDecl :: SInstanceDecl -> SInstanceDecl -> Bool;
  eqSInstanceDecl a b =
    case a of {
      SInstanceDecl x0 x1 x2 x3 x4 ->
        case b of {
          SInstanceDecl y0 y1 y2 y3 y4 ->
            (L.eqList (L.eqPair eqString L.eqKind) x0 y0 &&
             (L.eqList eqSPredicate x1 y1 &&
              (eqString x2 y2 &&
               (L.eqList eqSType x3 y3 && L.eqList (L.eqPair eqString eqSExpr) x4 y4))))
        }
    };
  eqEvidenceRole :: EvidenceRole -> EvidenceRole -> Bool;
  eqEvidenceRole a b =
    case a of {
      GivenEvidence ->
        case b of {
          GivenEvidence -> True;
          _ -> False
        };
      SuperclassEvidence ->
        case b of {
          SuperclassEvidence -> True;
          _ -> False
        };
      InstanceEvidence ->
        case b of {
          InstanceEvidence -> True;
          _ -> False
        }
    };
  eqSProgram :: SProgram -> SProgram -> Bool;
  eqSProgram a b =
    case a of {
      SProgram x0 x1 ->
        case b of {
          SProgram y0 y1 -> (L.eqList eqDataDecl x0 y0 && eqSExpr x1 y1);
          _ -> False
        };
      SClassProgram x0 x1 x2 x3 ->
        case b of {
          SClassProgram y0 y1 y2 y3 ->
            (L.eqList eqDataDecl x0 y0 &&
             (L.eqList eqSClassDecl x1 y1 && (L.eqList eqSInstanceDecl x2 y2 && eqSExpr x3 y3)));
          _ -> False
        }
    };
  eqSourceModule :: SourceModule -> SourceModule -> Bool;
  eqSourceModule a b =
    case a of {
      SourceModule x0 x1 x2 x3 x4 x5 x6 x7 x8 x9 ->
        case b of {
          SourceModule y0 y1 y2 y3 y4 y5 y6 y7 y8 y9 ->
            (eqString x0 y0 &&
             (L.eqMaybe eqString x1 y1 &&
              (L.eqMaybe (L.eqList eqExport) x2 y2 &&
               (L.eqList eqImport x3 y3 &&
                (L.eqList eqDataDecl x4 y4 &&
                 (L.eqList eqSClassDecl x5 y5 &&
                  (L.eqList eqSInstanceDecl x6 y6 &&
                   (L.eqList (eqTriple eqString (L.eqMaybe eqSAnnotation) eqSExpr) x7 y7 &&
                    (L.eqMaybe eqSExpr x8 y8 && eqSourceSyntax x9 y9)))))))))
        }
    };
  eqImport :: Import -> Import -> Bool;
  eqImport a b =
    case a of {
      Import x0 x1 x2 x3 ->
        case b of {
          Import y0 y1 y2 y3 ->
            (eqString x0 y0 && (eqBool x1 y1 && (L.eqMaybe eqString x2 y2 && eqSelection x3 y3)))
        }
    };
  eqSelection :: Selection -> Selection -> Bool;
  eqSelection a b =
    case a of {
      Everything ->
        case b of {
          Everything -> True;
          _ -> False
        };
      Only x0 ->
        case b of {
          Only y0 -> L.eqList eqExport x0 y0;
          _ -> False
        };
      Hiding x0 ->
        case b of {
          Hiding y0 -> L.eqList eqExport x0 y0;
          _ -> False
        }
    };
  eqExport :: Export -> Export -> Bool;
  eqExport a b =
    case a of {
      ExportValue x0 ->
        case b of {
          ExportValue y0 -> eqString x0 y0;
          _ -> False
        };
      ExportType x0 x1 ->
        case b of {
          ExportType y0 y1 -> (eqString x0 y0 && eqMembers x1 y1);
          _ -> False
        };
      ExportModule x0 ->
        case b of {
          ExportModule y0 -> eqString x0 y0;
          _ -> False
        }
    };
  eqMembers :: Members -> Members -> Bool;
  eqMembers a b =
    case a of {
      Abstract ->
        case b of {
          Abstract -> True;
          _ -> False
        };
      AllMembers ->
        case b of {
          AllMembers -> True;
          _ -> False
        };
      Members x0 ->
        case b of {
          Members y0 -> L.eqList eqString x0 y0;
          _ -> False
        }
    };
  eqPreludeMode :: PreludeMode -> PreludeMode -> Bool;
  eqPreludeMode a b =
    case a of {
      ImplicitPrelude ->
        case b of {
          ImplicitPrelude -> True;
          _ -> False
        };
      NoImplicitPrelude ->
        case b of {
          NoImplicitPrelude -> True;
          _ -> False
        }
    };
  eqType :: SType -> SType -> Bool;
  eqType a b = eqSType a b;
  eqAnnotation :: SAnnotation -> SAnnotation -> Bool;
  eqAnnotation a b = eqSAnnotation a b;
  eqPattern :: SPattern -> SPattern -> Bool;
  eqPattern a b = eqSPattern a b;
  eqExpr :: SExpr -> SExpr -> Bool;
  eqExpr a b = eqSExpr a b;
  eqSourceSpan :: SourceSpan -> SourceSpan -> Bool;
  eqSourceSpan (SourceSpan p m f sl sc el ec) (SourceSpan p2 m2 f2 sl2 sc2 el2 ec2) =
    (eqString p p2 && (eqString m m2 && (eqString f f2 &&
      (eqInt sl sl2 && (eqInt sc sc2 && (eqInt el el2 && eqInt ec ec2))))));
  eqSourceSyntax :: SourceSyntax -> SourceSyntax -> Bool;
  eqSourceSyntax a b =
    case a of {
      LegacyEmlfV1 ->
        case b of {
          LegacyEmlfV1 -> True;
          _ -> False
        };
      MetadataSyntax ->
        case b of {
          MetadataSyntax -> True;
          _ -> False
        };
      SharedHaskellV1 ->
        case b of {
          SharedHaskellV1 -> True;
          _ -> False
        }
    }
}
