#!/usr/bin/env bash
set -euo pipefail
umask 077
ulimit -v 262144
ulimit -f 8192
ulimit -c 0
export LC_ALL=C
d="$PWD/evidence"
mkdir -p "$d"
exec > "$d/probe.log" 2>&1
echo "scope=owned synthetic process only; no compiler build or benchmark"
echo "effective_uid=$(id -u)"
test "$(id -u)" -ne 0
test "$(awk '/MemAvailable:/{print $2}' /proc/meminfo)" -ge 3145728
test "$(df -Pk "$d" | awk 'END{print $4}')" -ge 5242880
cat /proc/sys/kernel/perf_event_paranoid || true
p="$(command -v perf || true)"
if [ -z "$p" ]; then echo 'STOP: no installed perf'; exit 21; fi
# No perf install, capabilities, sysctl writes, sudo or system-wide sampling.
readlink -f "$p"
"$p" --version
cd "$d"
cat > probe.c <<'EOF'
#include <stdint.h>
#include <time.h>
#include <stdio.h>
__attribute__((noinline)) static uint64_t patricia_probe_work(uint64_t x) {
  for (int i=0;i<200000;++i) x=(x ^ (x>>19))*6364136223846793005ULL+1;
  return x;
}
int main(void){uint64_t x=1;clock_t t=clock();while(clock()-t<CLOCKS_PER_SEC)x=patricia_probe_work(x);printf("%llu\n",(unsigned long long)x);return 0;}
EOF
cc -O1 -g -fno-omit-frame-pointer probe.c -o probe
nm -an probe | grep 'patricia_probe_work'
"$p" record -o probe.data -e cpu-clock:u -F 49 -m 8 --no-buildid-cache -- ./probe
"$p" script -i probe.data -F comm,dso,sym > symbols.txt
grep 'patricia_probe_work' symbols.txt
echo 'PASS: unprivileged user-space CPU sampling and symbol decoding on synthetic target only'
