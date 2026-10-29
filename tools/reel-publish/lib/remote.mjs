// ssh/scp to MyContabo. Arguments go through execFile, never a local shell.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);
const HOST = 'MyContabo';

export async function ssh(remoteCmd, { input, timeout = 15 * 60 * 1000 } = {}) {
  const child = run('ssh', ['-o', 'BatchMode=yes', HOST, remoteCmd], { timeout, maxBuffer: 16 * 1024 * 1024 });
  if (input !== undefined) {
    child.child.stdin.end(input);
  }
  const { stdout } = await child;
  return stdout;
}

export async function scp(localPath, remotePath) {
  await run('scp', ['-q', '-o', 'BatchMode=yes', localPath, `${HOST}:${remotePath}`], { timeout: 30 * 60 * 1000 });
}
