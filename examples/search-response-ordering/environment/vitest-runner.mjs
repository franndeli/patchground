import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rename, rm, lstat, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = '/workspace';
const final = '/results/junit.xml';
const self = fileURLToPath(import.meta.url);

async function child(destination, files) {
  const { startVitest } = await import('vitest/node');
  let completed;
  const reporter = {
    onTestModuleCollected(module) {
      for (const test of module.children.allTests()) {
        const retry = test.options.retry;
        const count = typeof retry === 'number' ? retry : retry?.count ?? 0;
        if (count > 0 || (test.options.repeats ?? 0) > 0) {
          throw Error('Retries and repeats are unsupported');
        }
      }
    },
    onTestRunEnd(modules, errors, reason) {
      const cases = [];
      let trustworthy = errors.length === 0 && reason !== 'interrupted';
      for (const module of modules) {
        if (module.errors().length) trustworthy = false;
        for (const suite of module.children.allSuites()) {
          if (suite.errors().length) trustworthy = false;
        }
        for (const test of module.children.allTests()) {
          const state = test.result().state;
          if (!['passed', 'failed', 'skipped'].includes(state)) trustworthy = false;
          cases.push({ file: module.relativeModuleId, name: test.fullName, state });
        }
      }
      completed = { trustworthy, cases };
    },
  };
  const ctx = await startVitest([], {
    root, config: false, watch: false, run: true,
    include: files.length ? files : ['**/*.test.ts'], exclude: ['**/node_modules/**', '**/.git/**'],
    reporters: [reporter], environment: 'node', pool: 'forks', maxWorkers: 1,
    fileParallelism: false, isolate: true, retry: 0, allowOnly: false, maxConcurrency: 1,
    passWithNoTests: false, testTimeout: 5000, hookTimeout: 5000,
    sequence: { shuffle: false },
  }, {
    configFile: false, envDir: false, cacheDir: '/tmp/patchground-vite',
    resolve: { alias: { vitest: '/opt/patchground/node_modules/vitest/dist/index.js' } },
  });
  await ctx.close();
  if (!completed || ctx.state.getUnhandledErrors().length) return;
  await writeFile(destination, JSON.stringify(completed), { flag: 'wx' });
}

function escape(value) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&apos;').replaceAll("\n", "&#10;")
    .replaceAll("\r", "&#13;").replaceAll("\t", "&#9;");
}

async function parent() {
  await rm(final, { force: true });
  const temporary = await mkdtemp(path.join(tmpdir(), 'patchground-vitest-'));
  try {
    const receipt = path.join(temporary, 'receipt.json');
    const args = process.argv.slice(2);
    const files = args.length ? args.slice(1) : [];
    if (args.length && (args[0] !== '--files' || !files.length)) return;
    for (const file of files) {
      const parts = file.split('/');
      if (!file.endsWith('.test.ts') || parts.some(part =>
        !/^[\p{L}\p{N}_. -]+$/u.test(part) || ['.', '..', '.git', 'node_modules'].includes(part))) return;
    }
    if (new Set(files).size !== files.length) return;
    for (const file of files) {
      const full = path.join(root, file);
      if (!(await lstat(full)).isFile() || !(await realpath(full)).startsWith(root + '/')) return;
    }
    const code = await new Promise((resolve, reject) => {
      const process = spawn(globalThis.process.execPath, [self, '--child', receipt, ...files], {
        stdio: 'ignore', env: { ...globalThis.process.env, CI: 'true' },
      });
      process.once('error', reject);
      process.once('exit', (code, signal) => resolve(signal ? null : code));
    });
    const result = JSON.parse(await readFile(receipt, 'utf8'));
    if (!result.trustworthy || !result.cases.length) return;
    const failed = result.cases.some(test => test.state === 'failed');
    if (code !== (failed ? 1 : 0)) return;
    const seen = new Set();
    result.cases.sort((a, b) => {
      const left = `${a.file}::${a.name}`;
      const right = `${b.file}::${b.name}`;
      return left < right ? -1 : left > right ? 1 : 0;
    });
    const cases = result.cases.map(test => {
      if (!test.file || path.posix.isAbsolute(test.file) || test.file.split('/').includes('..')
          || test.file.includes('\\') || !test.file.endsWith('.test.ts') || !test.name
          || !test.file.isWellFormed() || !test.name.isWellFormed()
          || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/u.test(test.file + test.name)) throw Error('unsafe identity');
      const id = `${test.file}::${test.name}`;
      if (seen.has(id)) throw Error('duplicate identity');
      seen.add(id);
      const status = test.state === 'failed' ? '<failure message="test failed"/>'
        : test.state === 'skipped' ? '<skipped/>' : '';
      return `<testcase classname="${escape(test.file)}" name="${escape(test.name)}">${status}</testcase>`;
    });
    const staging = '/results/.patchground-junit.xml';
    await writeFile(staging, `<?xml version="1.0" encoding="UTF-8"?><testsuites><testsuite name="vitest">${cases.join('')}</testsuite></testsuites>`);
    await rename(staging, final);
    process.exitCode = failed ? 1 : 0;
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

try {
  if (process.argv[2] === '--child') await child(process.argv[3], process.argv.slice(4));
  else { process.exitCode = 1; await parent(); }
} catch {
  process.exitCode = 1;
}
