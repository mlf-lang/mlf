// Project a workflow's registered invocation onto its actual adapter command
// for the existing argument, guard, and retention controls. Direct framework
// references can also be asserted on the unprojected workflow.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const catalog = new Map();
const declarations = JSON.parse(fs.readFileSync('tests/test-catalog.json', 'utf8'));
for (const manifest of declarations.external_adapters) {
  for (const [suite, spec] of Object.entries(JSON.parse(fs.readFileSync(manifest, 'utf8')))) {
    assert.ok(!catalog.has(suite), 'Duplicate registered suite: ' + suite);
    catalog.set(suite, spec);
  }
}

const formerNoBytecodeFlag = new Set([
  'tools/release/test-suite-build-receipts.py',
  'tools/shared/test_figure12_direct.py',
  'tools/shared/test_framework_direct.py',
  'tools/shared/test_guest_framework.py',
  'tools/shared/test_guest_state_laws.py',
  'tools/shared/test_native_library.py',
]);

export function projectAdapterCommands(text) {
  return text.replace(/\bpython3? -B tools\/testing\/run\.py (?:--inherit-process-group )?([a-z0-9-]+)((?: --python-optimization| --report [^\s]+)*)(?: --(?=\s))?/g,
    (_, suite, options) => {
      const spec = catalog.get(suite);
      assert.ok(spec, 'Unknown workflow test adapter: ' + suite);
      const command = [...spec.command];
      if (command[0] === 'python' || command[0] === 'python3') {
        if (formerNoBytecodeFlag.has(command[2]) && command[1] === '-B') command.splice(1, 1);
        if (options.includes('--python-optimization')) command.splice(1, 0, '-O');
      } else if (command[0] === 'bash' && command[1] === 'tools/release/source-smoke.sh') {
        command.shift();
      }
      return command.join(' ');
    });
}
