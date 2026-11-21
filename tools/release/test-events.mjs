import fs from 'node:fs';

export function releaseTestEvent(suite, event) {
  if (process.env.MLF_TEST_SUITE === suite && process.env.MLF_TEST_EVENTS) {
    fs.appendFileSync(process.env.MLF_TEST_EVENTS, JSON.stringify(event) + '\n');
  }
}

export function releaseTestCase(suite, id, action) {
  releaseTestEvent(suite, {start: id});
  try {
    action();
    releaseTestEvent(suite, {id, status: 'pass'});
  } catch (error) {
    releaseTestEvent(suite, {id, status: 'fail', detail: String(error)});
    throw error;
  }
}
