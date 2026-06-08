#!/bin/bash
# Test that the submit command can import registry module

echo "Testing submit command registry import..."

# Simulate the environment that will exist when tools are installed
export PYTHONPATH="/home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent/tools/registry/lib:$PYTHONPATH"

# Test Python import
python3 <<'EOF'
import sys
try:
    from registry import registry
    print("✓ registry module imports successfully")
    print(f"  Registry class: {type(registry)}")
    print(f"  Registry env_file: {registry.env_file}")
except ImportError as e:
    print(f"✗ Failed to import registry: {e}")
    sys.exit(1)
EOF

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✓ Submit command will work correctly"
    echo "  The registry module is properly installed in tools/registry/lib/"
else
    echo ""
    echo "✗ Submit command will fail"
    echo "  Please ensure tools/registry/lib/registry.py exists"
fi

exit $exit_code
