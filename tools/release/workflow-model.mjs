// Parse the document once; assertions and mutations operate on YAML values.
// Actionlint validates Actions syntax separately. Shell bodies are tested by
// executing them with recording commands, never by matching display names.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';

export function parseWorkflow(text) {
  const result = spawnSync('python3', ['-B', 'tools/testing/workflow_yaml.py'],
    {input: text, encoding: 'utf8', timeout: 10000, maxBuffer: 8 * 1024 * 1024});
  assert.equal(result.status, 0, result.stderr || String(result.error));
  return JSON.parse(result.stdout);
}
export const readWorkflow = name => parseWorkflow(fs.readFileSync(`.github/workflows/${name}.yml`, 'utf8'));
export const job = (workflow, name) => {
  assert.ok(workflow.jobs?.[name], `Missing ${name} job`);
  return workflow.jobs[name];
};
export const steps = job => job.steps || [];
export const commandSteps = (job, command) => steps(job).filter(step => step.run?.includes(command));
export function commandStep(job, command) {
  const matches = commandSteps(job, command);
  assert.equal(matches.length, 1, `Exactly one step executes ${command}`);
  return matches[0];
}
export function actionSteps(job, action) {
  return steps(job).filter(step => step.uses?.split('@')[0] === action);
}
export function actionStep(job, action) {
  const matches = actionSteps(job, action);
  assert.equal(matches.length, 1, `Exactly one ${action} action`);
  return matches[0];
}
export const list = value => value === undefined ? [] : Array.isArray(value) ? value : [value];
export const paths = step => String(step.with?.path || '').trim().split(/\s*\n\s*/);
export function expression(value, context = {}) {
  if (typeof value !== 'string') return value;
  const source = value.trim().replace(/^\$\{\{\s*|\s*\}\}$/g, '')
    .replaceAll('github.event.pull_request.labels.*.name',
      'github.event.pull_request.labels.map(label => label.name)');
  const globals = {
    contains: (values, value) => values.includes(value),
    format: (pattern, ...values) => pattern.replace(/\{(\d+)\}/g, (_, i) => values[i]),
    fromJSON: JSON.parse, toJSON: JSON.stringify, always: () => true, failure: () => false,
    success: () => true, cancelled: () => false, inputs: {}, ...context,
  };
  return Function(...Object.keys(globals), `return (${source});`)(...Object.values(globals));
}
export const selected = (step, context = {}) => step.if === undefined || !!expression(step.if, context);
export const render = (value, context) => String(value).replace(/\$\{\{(.*?)\}\}/gs,
  (_, source) => String(expression(source, context)));
export const clone = value => structuredClone(value);
export function reformatted(workflow) {
  const changed = clone(workflow);
  for (const entry of Object.values(changed.jobs)) {
    for (const [index, step] of steps(entry).entries()) {
      if (step.name) step.name = `Display name ${index}`;
      if (step.run) step.run = '# A harmless comment\n' + step.run;
    }
  }
  // JSON is valid YAML: quoted keys/scalars, flow collections, different order
  // and arbitrary indentation must preserve the same workflow contracts.
  const reverse = value => Array.isArray(value) ? value.map(reverse) : value && typeof value === 'object'
    ? Object.fromEntries(Object.entries(value).reverse().map(([key, item]) => [key, reverse(item)])) : value;
  return parseWorkflow(JSON.stringify(reverse(changed), null, 4));
}
