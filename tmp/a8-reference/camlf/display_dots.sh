cd dot
rm *.png
for f in *.dot; do echo $f; dot -Tpng $f -O; done
cd ..
display dot/*.png
