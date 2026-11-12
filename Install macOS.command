#!/bin/bash
set -e
cd "$(dirname "$0")"
exec /bin/bash installer/bootstrap_macos.sh "$@"
