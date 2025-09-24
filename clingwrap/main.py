import click
import datetime
import importlib
import os
import random
import sys
import tempfile
import yaml
import zipfile

from oslo_concurrency import processutils


class Job:
    def __init__(self, **kwargs):
        self.id = random.randint(0, 100000)
        self.name = kwargs['name']
        self.type = kwargs['type']
        self.destination = kwargs.get('destination')
        self._log = kwargs['log']
        self._zipped = kwargs['zipped']

        self.log(f'Created job named "{self.name}" with destination {self.destination}')

    def log(self, s):
        log_string = f'{datetime.datetime.now()} [{self.type} job id {self.id:6d}] {s}\n'

        sys.stdout.write(log_string)
        sys.stdout.flush()
        self._log.write(log_string)
        self._log.flush()

    def execute(self):
        self.log('Executing')
        d = self._execute_inner()
        self._zipped.writestr(self.destination, d)
        self.log(f'Wrote {len(d)} bytes to {self.destination}')
        return []


class FileJob(Job):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.source = kwargs['source']
        self.log(f'Job has source {self.source}')

    def _execute_inner(self):
        if os.path.exists(self.source):
            self.log(f'Source {self.source} exists')
            try:
                with open(self.source) as f:
                    return f.read()
            except Exception as e:
                self.log(f'Exception while reading {self.source}: {e}')
                return f'--- file {self.source} exception: {e} ---'
        else:
            self.log(f'Source {self.source} does not exist')
            return f'--- file {self.source} was absent ---'


class DirectoryJob(Job):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.source = kwargs['source']
        self.log(f'Job has source {self.source}')

    def execute(self):
        self.log('Executing')
        jobname = f'Generated FileJob for directory {self.source}'
        for root, _, files in os.walk(self.source):
            for file in files:
                j = {
                    'type': 'file',
                    'name': jobname,
                    'source': os.path.join(root, file),
                    'destination': os.path.join(self.destination, root, file)
                }
                self.log(f'Yielding job {j}')
                yield j


class ShellJob(Job):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command = kwargs['command']
        self.log(f'Job has command {self.command}')

    def _execute_inner(self):
        stdout = ''
        stderr = ''

        try:
            stdout, stderr = processutils.execute(self.command, shell=True)
            return (
                f'# {self.command}\n\n'
                f'----- stdout -----\n{stdout.rstrip()}\n\n'
                f'----- stderr -----\n{stderr.rstrip()}'
            )

        except Exception as e:
            self.log(f'Received exception while running shell command: {e}')
            return (
                f'# {self.command}\n\n'
                f'----- stdout -----\n\n'
                f'----- stderr -----\n\n'
                f'----- exception -----\n{e}\n'
            )


class ShellEmitterJob(Job):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command = kwargs['command']
        self.log(f'Job has command {self.command}')

    def execute(self):
        self.log('Executing')
        try:
            stdout, stderr = processutils.execute(self.command, shell=True)
            if stdout:
                self.log(f'Received stdout while generating jobs: {stdout}')
            if stderr:
                self.log(f'Received stderr while generating jobs: {stderr}')

            parsed = yaml.load(stdout, Loader=yaml.SafeLoader)
            self.log(f'YAML parsed ok and produced {len(parsed)} commands')
            for y in parsed:
                self.log(f'Yielding job {y}')
                yield y

        except Exception as e:
            self.log(f'Received exception while running shell_emmiter command: {e}')
            return (
                f'# {self.command}\n\n'
                f'----- stdout -----\n\n'
                f'----- stderr -----\n\n'
                f'----- exception -----\n{e}\n'
            )


JOB_MAP = {
    'directory': DirectoryJob,
    'file': FileJob,
    'shell': ShellJob,
    'shell_emitter': ShellEmitterJob,
}


def rehydrate_job(**kwargs):
    return JOB_MAP.get(kwargs['type']['class'])(**kwargs)


@click.group()
@click.pass_context
def cli(ctx):
    ...


@click.command()
@click.option('--target', help='The name of the target configuration to use')
@click.option('--output', help='The path and file to write the output to')
@click.pass_context
def gather(ctx, target=None, output=None):
    if not output:
        print('Please specify an output location with --output.')
        sys.exit(1)

    # Collect our commands from the target file or stdin
    cmds = ''
    if target:
        if os.path.exists(target):
            # Target is a file path
            with open(target) as f:
                cmds = f.read()

        elif target.find('/') != -1:
            print('Target configuration names should contain paths')
            sys.exit(1)

        else:
            # Target might also be the _name_ of a configuration we ship as an
            # example.
            with importlib.resources.path('clingwrap', 'examples') as data_path:
                target_path = os.path.join(data_path, f'{target}.cwd')
                if not os.path.exists(target_path):
                    print('Target path {target_path} does not exist')
                    sys.exit(1)

                with open(target_path) as f:
                    cmds = f.read()

    else:
        print('Reading command from stdin, send EOF to start processing')
        cmds = sys.stdin.read()

    # Parse commands
    queued = yaml.load(cmds, Loader=yaml.SafeLoader)

    # Read and execute commands
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipped:
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='clingwrap') as td:
            log_file = os.path.join(td, 'clingwrap.log')

            with open(log_file, 'w') as log:
                def log_write(job_type, job_id, s):
                    log_string = f'{datetime.datetime.now()} ['
                    if job_type:
                        log_string += f'{job_type} job id {job_id:6d}'
                    log_string += f'] {s}\n'

                    sys.stdout.write(log_string)
                    sys.stdout.flush()
                    log.write(log_string)
                    log.flush()

                while queued:
                    kwargs = queued.pop()
                    log_write(None, None, f'Considering job {kwargs}')

                    kwargs['log'] = log
                    kwargs['zipped'] = zipped
                    job = JOB_MAP.get(kwargs['type'])(**kwargs)

                    try:
                        for newjob in job.execute():
                            newjob['log'] = log
                            newjob['zipped'] = zipped
                            queued.append(newjob)
                    except Exception as e:
                        log_write(
                            job['type'],
                            job['id'],
                            f'Exception while executing job: {e}')

            with open(log_file) as log:
                zipped.writestr('clingwrap.log', log.read())


cli.add_command(gather)
