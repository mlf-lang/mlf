// Usage: node tools/release/measure-ci.mjs RUN.json JOBS.json [LOG_DIRECTORY]
// Inputs are unmodified GitHub REST responses and the run's downloaded logs.
import fs from 'node:fs';
import path from 'node:path';
const [runFile, jobsFile, logDirectory] = process.argv.slice(2);
if (!runFile || !jobsFile) throw new Error('RUN.json JOBS.json [LOG_DIRECTORY] required');
const run = JSON.parse(fs.readFileSync(runFile));
const response = JSON.parse(fs.readFileSync(jobsFile));
const jobs = Array.isArray(response) ? response.flatMap(page => page.jobs) : response.jobs;
const seconds = (start, end) => Math.max(0, (Date.parse(end) - Date.parse(start)) / 1000);
const sum = rows => rows.reduce((total, row) => total + row, 0);
const logs = logDirectory ? fs.readdirSync(logDirectory).filter(name => name.endsWith('.txt')) : [];
const rows = jobs.map(job => {
  const file = logs.find(name => name.replace(/^\d+_/, '').replace(/\.txt$/, '') === job.name);
  const text = file ? fs.readFileSync(path.join(logDirectory, file), 'utf8') : '';
  const lines = text.split('\n').flatMap(line => {
    const match = line.match(/^(\d{4}-\d\d-\d\dT\S+Z) (.*)$/);
    return match ? [{time: Date.parse(match[1]) / 1000, text: match[2]}] : [];
  });
  const stages = [];
  const starts = new Map();
  for (const line of lines) {
    const start = line.text.match(/^CI_STAGE_START (\S+) (\d+)$/);
    if (start) starts.set(start[1], Number(start[2]));
    const end = line.text.match(/^CI_STAGE_END (\S+) (\d+) (\d+)$/);
    if (end && starts.has(end[1])) {
      stages.push({name:end[1],start:starts.get(end[1]),end:Number(end[2]),seconds:Number(end[2])-starts.get(end[1]),exit_code:Number(end[3])});
      starts.delete(end[1]);
    }
  }
  const steps = (job.steps || []).filter(step => step.started_at && step.completed_at && step.conclusion !== 'skipped')
    .map(step => ({name:step.name,seconds:seconds(step.started_at,step.completed_at),start:Date.parse(step.started_at)/1000,end:Date.parse(step.completed_at)/1000}));
  const qualification = stages.find(stage => stage.name === 'qualification') || steps.find(step => step.name === 'Run complete native compiler group');
  let candidateRebuild = 0, testBuilds = 0, preparation = 0;
  const portFixtures = [];
  if (qualification) {
    const active = lines.filter(line => line.time >= qualification.start && line.time < qualification.end);
    // Root test commands historically rebuilt both required tools first. Use
    // the first real child command, ignoring later tail/collection duplicates.
    const firstChild = active.find(line => line.text.startsWith('+ '));
    if (firstChild && active.some(line => line.time < firstChild.time && line.text === 'Building executable mlf-compiler:mlfpkg')) {
      candidateRebuild = firstChild.time - qualification.start;
    }
    const finish = active.find(line => /^Compiler package \S+ passed$/.test(line.text));
    const primary = finish ? active.filter(line => line.time <= finish.time) : active;
    let building;
    for (const line of primary) {
      if (/^\+ .* --manifest .*\/tests\/mlf-package.json .* build --target /.test(line.text) || /^\+ .* --timeout .*next-stage.* build --target emlf$/.test(line.text)) building = line.time;
      if (building !== undefined && /^build passed; report: /.test(line.text)) { testBuilds += line.time-building; building = undefined; }
    }
    const fixtures = primary.filter(line => /^Building checked port target /.test(line.text));
    if (fixtures.length) {
      const last = primary.find(line => line.time > fixtures.at(-1).time && /^\+ clang .*\/runtime\.o$/.test(line.text));
      for (let i=0; i<fixtures.length; ++i) {
        const end = fixtures[i+1]?.time ?? last?.time;
        if (end !== undefined) portFixtures.push({fixture:fixtures[i].text.replace('Building checked port target ',''),seconds:end-fixtures[i].time});
      }
      preparation = sum(portFixtures.map(row => row.seconds));
    }
  }
  const build = sum(steps.filter(step => /^(Build current compiler|Bootstrap and self-build|Bootstrap native Linux|Build the .* candidate|Build the macOS qualification|Build shared qualification)/.test(step.name)).map(step=>step.seconds)) + candidateRebuild + testBuilds;
  const qualificationSeconds = (qualification?.seconds || 0) + sum(steps.filter(step=>step.name==='Qualify exact Windows candidate and independent oracles').map(step=>step.seconds));
  const packaging = sum(steps.filter(step=>/^(Verify six groups|Package and relocate|Check all three packaged)/.test(step.name)).map(step=>step.seconds));
  const artifacts = sum(stages.filter(stage=>stage.name==='artifact-import' || stage.name==='evidence').map(stage=>stage.seconds)) + sum(steps.filter(step=>/artifact@|Download digest-checked|Verify and archive|Export checked LLVM/.test(step.name)).map(step=>step.seconds));
  return {id:job.id,name:job.name,conclusion:job.conclusion,runner:job.runner_name,queue_seconds:seconds(job.created_at,job.started_at),runner_seconds:seconds(job.started_at,job.completed_at),build_seconds:build,test_seconds:Math.max(0,qualificationSeconds-candidateRebuild-testBuilds),packaging_seconds:packaging,artifact_seconds:artifacts,candidate_rebuild_seconds:candidateRebuild,test_prerequisite_build_seconds:testBuilds,port_preparation_seconds:preparation,port_fixtures:portFixtures,steps,stages};
});
console.log(JSON.stringify({run:run.id,url:run.html_url,source:run.head_sha,status:run.status,conclusion:run.conclusion,wall_seconds:seconds(run.created_at,run.updated_at),aggregate_runner_seconds:sum(rows.map(row=>row.runner_seconds)),aggregate_queue_seconds:sum(rows.map(row=>row.queue_seconds)),aggregate_build_seconds:sum(rows.map(row=>row.build_seconds)),aggregate_test_seconds:sum(rows.map(row=>row.test_seconds)),aggregate_packaging_seconds:sum(rows.map(row=>row.packaging_seconds)),aggregate_artifact_seconds:sum(rows.map(row=>row.artifact_seconds)),measurement_notes:['Runner time is started_at to completed_at, not billed OS-weighted minutes.','Queue time is job created_at to started_at; parallel queues must not be summed into wall time.','Test executable and fresh self-host builds are separated using primary log command boundaries; other small C builds remain within test time.','Port preparation includes all independent checks and is included in test time.','Composite stage markers have one-second resolution; legacy log boundaries have subsecond resolution.','Setup, dependency installation, cleanup and unclassified overhead explain the remaining runner time.','Workflow updated_at can include final bookkeeping after its last job.'],jobs:rows},null,2));
