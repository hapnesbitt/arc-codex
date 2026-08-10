import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, symlink } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const NEXT = path.join(FRONTEND, 'node_modules', 'next', 'dist', 'bin', 'next');
const ROUTE = '/api/internal/revalidate-library';
const TEST_SECRET = 'library-route-test-secret-not-production';

async function freePort() {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  assert.notEqual(address, null);
  assert.equal(typeof address, 'object');
  const port = address.port;
  server.close();
  await once(server, 'close');
  return port;
}

async function startNext(secret) {
  const directory = await mkdtemp(path.join(tmpdir(), 'arc-library-route-'));
  await symlink(path.join(FRONTEND, '.next'), path.join(directory, '.next'), 'dir');
  const port = await freePort();
  const environment = {
    ...process.env,
    HOSTNAME: '127.0.0.1',
    NEXT_TELEMETRY_DISABLED: '1',
  };
  delete environment.LIBRARY_REVALIDATE_SECRET;
  if (secret !== undefined) environment.LIBRARY_REVALIDATE_SECRET = secret;

  const child = spawn(
    process.execPath,
    [NEXT, 'start', directory, '-H', '127.0.0.1', '-p', String(port)],
    { env: environment, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk.toString(); });
  child.stderr.on('data', (chunk) => { output += chunk.toString(); });

  const base = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Next exited before becoming ready (${child.exitCode}): ${output}`);
    }
    try {
      await fetch(`${base}${ROUTE}`, { signal: AbortSignal.timeout(500) });
      return { base, child, directory, output: () => output };
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  child.kill('SIGTERM');
  throw new Error(`Next did not become ready: ${output}`);
}

async function stopNext(server) {
  if (server.child.exitCode === null) {
    server.child.kill('SIGTERM');
    await Promise.race([
      once(server.child, 'exit'),
      new Promise((resolve) => setTimeout(resolve, 5_000)),
    ]);
  }
  if (server.child.exitCode === null) server.child.kill('SIGKILL');
  await rm(server.directory, { recursive: true, force: true });
}

function assertNoStore(response) {
  assert.match(response.headers.get('cache-control') ?? '', /(?:^|,)\s*no-store\b/i);
}

test('route fails closed when the server-side secret is missing', async () => {
  const server = await startNext(undefined);
  try {
    const response = await fetch(`${server.base}${ROUTE}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${TEST_SECRET}` },
    });
    const body = await response.text();
    assert.equal(response.status, 503);
    assertNoStore(response);
    assert.equal(body.includes(TEST_SECRET), false);
  } finally {
    await stopNext(server);
  }
});

test('route enforces POST and bearer authentication without reflecting tokens', async () => {
  const server = await startNext(TEST_SECRET);
  try {
    const getResponse = await fetch(`${server.base}${ROUTE}`, {
      headers: { Authorization: `Bearer ${TEST_SECRET}` },
    });
    assert.equal(getResponse.status, 405);

    const missingResponse = await fetch(`${server.base}${ROUTE}`, { method: 'POST' });
    assert.equal(missingResponse.status, 401);
    assertNoStore(missingResponse);

    const wrongToken = 'definitely-the-wrong-test-token';
    const wrongResponse = await fetch(`${server.base}${ROUTE}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${wrongToken}` },
    });
    const wrongBody = await wrongResponse.text();
    assert.equal(wrongResponse.status, 401);
    assertNoStore(wrongResponse);
    assert.equal(wrongBody.includes(wrongToken), false);

    const correctResponse = await fetch(`${server.base}${ROUTE}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${TEST_SECRET}` },
    });
    const correctBody = await correctResponse.text();
    assert.equal(correctResponse.status, 200);
    assertNoStore(correctResponse);
    assert.deepEqual(JSON.parse(correctBody), { revalidated: true, path: '/library' });
    assert.equal(correctBody.includes(TEST_SECRET), false);
  } finally {
    await stopNext(server);
  }
});
