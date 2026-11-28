// Run workflow routing in Bash with explicit recording stand-ins. FD 3 keeps
// the call log independent of stdout redirection and pipelines in the script.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';

export function shellCalls(script, {stubs = '', env = {}, cwd, fail = null,
  variables = [], commands = ['python3'], shell} = {}) {
  const variableFields = variables.map(name => `"\${${name}-}"`).join(' ');
  const recorder = String.raw`record() {
  printf '%s\0' "$#" "$@" ` + variableFields + String.raw` >&3
  if [ "$(printf '%s\037' "$@")" = "$MLF_WORKFLOW_FAIL_ARGUMENTS" ]; then return 73; fi
}
`;
  const defaults = commands.map(command => `${command}() { record ${command} "$@"; }`).join('\n');
  // Actions' unspecified Linux/macOS shell supplies only -e. Explicit bash
  // additionally supplies pipefail; -u belongs to the script, never the runner.
  assert.ok(shell === undefined || shell === 'bash');
  const flags = shell === 'bash' ? ['-eo', 'pipefail'] : ['-e'];
  const result = spawnSync('/bin/bash', ['--noprofile', '--norc', ...flags, '-c',
    recorder + defaults + '\n' + stubs + '\n' + script], {
    encoding: 'utf8', timeout: 5000, cwd,
    stdio: ['pipe', 'pipe', 'pipe', 'pipe'],
    env: {PATH: '/nonexistent', RUNNER_TEMP: '/workflow-test', ...env,
      MLF_WORKFLOW_FAIL_ARGUMENTS: fail === null ? '' : fail.join('\x1f') + '\x1f'},
  });
  assert.equal(result.error, undefined);
  const raw = result.output[3];
  const tokens = raw ? raw.slice(0, -1).split('\0') : [];
  const calls = [];
  while (tokens.length) {
    const count = Number(tokens.shift());
    assert.ok(Number.isInteger(count) && count > 0 && count <= tokens.length,
      'Every recorded invocation has a complete argument boundary');
    const argv = tokens.splice(0, count);
    const environment = Object.fromEntries(variables.map(name => [name, tokens.shift()]));
    calls.push({argv, ...environment});
  }
  return {status: result.status, stdout: result.stdout, stderr: result.stderr, calls};
}
export function successfulCalls(script, options) {
  const result = shellCalls(script, options);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, '');
  return result.calls;
}
export function requireFailurePropagation(script, options, calls) {
  for (const call of calls) {
    const result = shellCalls(script, {...options, fail: call.argv});
    assert.equal(result.status, 73, 'A failed command must fail the step: ' + call.argv.join(' '));
    const matching = result.calls.findIndex(candidate => JSON.stringify(candidate.argv) === JSON.stringify(call.argv));
    assert.ok(matching >= 0, 'The failing command must execute');
    assert.equal(matching, result.calls.length - 1, 'A failed command must stop later work');
  }
}

export const shellCommand = argv => argv.map(value => "'" + value.replaceAll("'", "'\"'\"'") + "'").join(' ');
