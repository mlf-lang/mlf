ocamlbuild xmlf_main.cmo gmlf_main.cmo xTest.cmo gTest.cmo
cd _build

echo "modules..."
ocamlfind ocamldoc -package camomile -package kaputt -I pprint `grep -oe "[^\"]*.cmo" ../top.ml | sed s/.cmo/.ml/g | sed s,pprint,pprint/pprint,` xmlf_main.ml gmlf_main.ml gTest.ml xTest.ml -dot
cat ocamldoc.out | grep -ve "^  rotate=" | grep -ve "^  size=" > ../doc_modules.dot

# echo "types..."
# ocamlfind ocamldoc -package camomile -package kaputt -I pprint `grep -oe "[^\"]*.cmo" ../top.ml | sed s/.cmo/.ml/g | sed s,pprint,pprint/pprint,` -dot -dot-types -dot-reduce
# cat ocamldoc.out | grep -ve "^  rotate=" | grep -ve "^  size=" > ../doc_types.dot

cd ..
