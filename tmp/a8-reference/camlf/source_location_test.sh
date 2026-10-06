echo "Source code printing for different parsing sources."
echo "Each test should print 1 on success, and 0 on failure"
echo

# The code is horribly non-factorized, it's basically a shell script
# copy-pasted 4 times with slight variations. I'm not a bash coder,
# improvements welcome.

ocamlbuild -quiet main.d.byte || (echo "test failed : main.d.byte does not build"; exit 2)

echo "Correct source location for the '-expr' input :"
echo `rm dot/*; DEBUG_ALL="1" ./main.d.byte -expr "1+1" > /dev/null; grep -F "[app]" dot/01*.dot | grep -F "+" | wc -l`

echo "Correct source location for the '--toplevel' input"
echo `rm dot/*; echo "1 + 1;;" | DEBUG_ALL="1" ./main.d.byte -t > /dev/null; grep -F "[app]" dot/01*.dot | grep -F "+" | wc -l`

echo "Correct source location for the '-' (stdin) input"
echo `rm dot/*; echo "1 + 1;;" | DEBUG_ALL="1" ./main.d.byte - > /dev/null; grep -F "[app]" dot/01*.dot | grep -F "+" | wc -l`

echo "Correct source location for the 'file' (files as command-line parameters) input :"
echo "1 + 1;;" > /tmp/loc_test.mlf
echo `rm dot/*; DEBUG_ALL="1" ./main.d.byte /tmp/loc_test.mlf > /dev/null; grep -F "[app]" dot/01*.dot | grep -F "+" | wc -l`
