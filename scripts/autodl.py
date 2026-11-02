"""AutoDL 同步工具。密码只从被 Git 忽略的本地配置读取。"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import time

import paramiko

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/root/autodl-tmp/visdrone-codex'
LOCAL = ROOT / '.local'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def connect():
    lines = (ROOT / 'autodl配置.txt').read_text(encoding='utf-8-sig').splitlines()
    command = next(line[line.index('ssh '):] for line in lines if 'ssh ' in line)
    args = shlex.split(command)
    user, host = next(a for a in args if '@' in a).split('@', 1)
    port = int(args[args.index('-p') + 1]) if '-p' in args else 22
    password = re.sub(r'^(?:密码|password)\s*[:：]\s*', '', lines[-1].strip(), flags=re.I)
    LOCAL.mkdir(exist_ok=True)
    known = LOCAL / 'known_hosts'
    client = paramiko.SSHClient()
    if known.exists():
        client.load_host_keys(str(known))
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=30,
                   allow_agent=False, look_for_keys=False)
    client.save_host_keys(str(known))
    return client


def run(client, command):
    _, out, err = client.exec_command(command)
    channel = out.channel
    while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
        if channel.recv_ready():
            print(channel.recv(65536).decode(errors='replace'), end='', flush=True)
        if channel.recv_stderr_ready():
            print(channel.recv_stderr(65536).decode(errors='replace'), end='', flush=True)
        time.sleep(0.05)
    status = channel.recv_exit_status()
    if status:
        raise RuntimeError(f'Remote command failed, exit={status}')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def upload(client, path, remote):
    with client.open_sftp() as sftp:
        try:
            offset = sftp.stat(remote).st_size
        except FileNotFoundError:
            offset = 0
        size = path.stat().st_size
        if offset > size:
            raise RuntimeError('Remote partial file is larger than local archive')
        last = time.monotonic()
        with path.open('rb') as src, sftp.open(remote, 'ab' if offset else 'wb') as dst:
            dst.set_pipelined(True)
            src.seek(offset)
            while block := src.read(1024 * 1024):
                dst.write(block)
                offset += len(block)
                if time.monotonic() - last > 20:
                    print(f'上传 {offset / 1e6:.0f}/{size / 1e6:.0f} MB', flush=True)
                    last = time.monotonic()
    digest = sha(path)
    run(client, f'echo {shlex.quote(digest + "  " + remote)} | sha256sum -c -')


def sync(client):
    if git('status', '--porcelain').strip():
        raise RuntimeError('请先将代码改动提交到本地 Git，再同步训练版本。')
    revision = git('rev-parse', 'HEAD').decode().strip()
    archive = LOCAL / f'{revision}.tar'
    subprocess.run(['git', 'archive', '--format=tar', '-o', str(archive), revision], cwd=ROOT, check=True)
    with tarfile.open(archive, 'r') as tf:
        hashes = {}
        for member in tf.getmembers():
            if member.isfile():
                hashes[member.name] = hashlib.sha256(tf.extractfile(member).read()).hexdigest()
    with tarfile.open(archive, 'a') as tf:
        content = json.dumps({'commit': revision, 'files': hashes}, indent=2, ensure_ascii=False).encode()
        info = tarfile.TarInfo('SOURCE_MANIFEST.json'); info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    destination = f'{REMOTE}/releases/{revision}'
    remote_archive = f'{REMOTE}/incoming/{revision}.tar'
    upload(client, archive, remote_archive)
    run(client, f'if [ ! -d {destination} ]; then mkdir -p {destination}; tar -xf {remote_archive} -C {destination}; fi; '
                f'ln -sfn {REMOTE}/shared/dataset {destination}/dataset; '
                f'ln -sfn {REMOTE}/shared/pretrained_weights {destination}/pretrained_weights; '
                f'ln -sfn {REMOTE}/shared/outputs {destination}/outputs; '
                f'ln -sfn {destination} {REMOTE}/current; echo VERSION={revision}')


def assets(client):
    files = sorted(p for folder in ('dataset', 'pretrained_weights') for p in (ROOT / folder).rglob('*') if p.is_file())
    manifest = [{'path': p.relative_to(ROOT).as_posix(), 'size': p.stat().st_size, 'sha256': sha(p)} for p in files]
    content = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(content).hexdigest()
    archive = LOCAL / f'assets-{digest}.tar'
    if not archive.exists():
        print(f'归档 {len(files)} 个资源文件', flush=True)
        with tarfile.open(archive, 'w') as tf:
            for p in files:
                tf.add(p, arcname=p.relative_to(ROOT).as_posix(), recursive=False)
            info = tarfile.TarInfo('ASSET_MANIFEST.json'); info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    remote_archive = f'{REMOTE}/incoming/{archive.name}'
    upload(client, archive, remote_archive)
    run(client, f'if [ ! -f {REMOTE}/shared/.assets-{digest} ]; then '
                f'tar -xf {remote_archive} -C {REMOTE}/shared && touch {REMOTE}/shared/.assets-{digest}; fi; '
                f'du -sh {REMOTE}/shared/dataset {REMOTE}/shared/pretrained_weights')


def download(client):
    destination = ROOT / 'outputs' / 'server'
    with client.open_sftp() as sftp:
        import stat
        def walk(remote, local):
            local.mkdir(parents=True, exist_ok=True)
            for entry in sftp.listdir_attr(remote):
                target = local / entry.filename
                source = remote + '/' + entry.filename
                if stat.S_ISDIR(entry.st_mode):
                    walk(source, target)
                elif stat.S_ISREG(entry.st_mode):
                    sftp.get(source, str(target))
        walk(REMOTE + '/shared/outputs', destination)
    print(f'结果下载至 {destination}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'sync', 'upload-assets', 'exec', 'download-results'])
    parser.add_argument('command', nargs='?')
    args = parser.parse_args()
    with connect() as client:
        run(client, f'mkdir -p {REMOTE}/incoming {REMOTE}/releases {REMOTE}/shared/outputs')
        if args.action == 'sync': sync(client)
        elif args.action == 'upload-assets': assets(client)
        elif args.action == 'download-results': download(client)
        elif args.action == 'exec':
            if not args.command: parser.error('exec 需要远程命令')
            run(client, args.command)
        else:
            run(client, f'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; df -h /root/autodl-tmp; readlink {REMOTE}/current || true')


if __name__ == '__main__':
    main()
