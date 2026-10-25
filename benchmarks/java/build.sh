#!/bin/bash
# Compile DevStone.java against Devs-Suite-Facade (DEVSJAVA).
# DEVSJAVA_HOME defaults to ../../../Devs-Suite-Facade (sibling checkout, built with `mvn package`).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DEVSJAVA_HOME=${DEVSJAVA_HOME:-$HERE/../../../Devs-Suite-Facade}
JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/jdk-17}
M2=${M2:-$HOME/.m2/repository}
CP="$DEVSJAVA_HOME/target/DEVS-Suite-facade-1.0.jar"
CP="$CP:$(ls "$M2"/org/apache/commons/commons-lang3/*/commons-lang3-*.jar | head -1)"
CP="$CP:$(ls "$M2"/org/apache/commons/commons-math3/*/commons-math3-*.jar | head -1)"
echo "$CP:$HERE/out" > "$HERE/classpath.txt"
"$JAVA_HOME/bin/javac" -nowarn -cp "$CP" -d "$HERE/out" "$HERE/DevStone.java" "$HERE/RLBench.java" 2>&1 | grep -v '^Note' || true
