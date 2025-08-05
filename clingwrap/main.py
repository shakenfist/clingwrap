import click
import io
import logging
import os
import random
import re
from shakenfist_utilities import logs
import sys
import yaml
import zipfile

from oslo_concurrency import processutils


LOG = logs.setup_console(__name__)


class UnsupportedJobException(Exception):
    pass


class Job(object):
    def __init__(self, definition):
        self.definition = definition
        self.destination = self.definition.get('destination')
        self.read_flo = None

    def items(self):
        return []

    def execute(self):
        pass

    def cleanup(self):
        if self.read_flo:
            self.read_flo.close()


class FileJob(Job):
    def __init__(self, definition):
        super(FileJob, self).__init__(definition)

    def verb(self):
        return 'file'

    def execute(self):
        source = self.definition.get('source')
        if os.path.exists(source):
            self.read_flo = open(source, 'rb')
        else:
            self.read_flo = io.StringIO('--- file %s was absent ---' % source)


class DirectoryJob(Job):
    def __init__(self, definition):
        super(DirectoryJob, self).__init__(definition)
        if 'exclude' in definition:
            self.exclude = re.compile(definition['exclude'])
        else:
            self.exclude = None

    def verb(self):
        return 'directory'

    def items(self, path=None):
        if not path:
            path = self.definition.get('directory')

        if not os.path.exists(path):
            return

        for ent in os.listdir(path):
            p = os.path.join(path, ent)
            if os.path.isdir(p):
                for result in self.items(p):
                    yield result
            else:
                if self.exclude:
                    if self.exclude.match(ent):
                        continue
                yield {
                    'name': 'Emitted file archival (%s)' % p,
                    'file': p,
                    'destination': p.lstrip('/')
                }


class CommandJob(Job):
    def __init__(self, definition):
        super(CommandJob, self).__init__(definition)

    def verb(self):
        return 'shell'

    def execute(self):
        stdout = ''
        stderr = ''

        try:
            stdout, stderr = processutils.execute(
                self.definition.get('shell'), shell=True)
            self.read_flo = io.StringIO(
                '# %s\n\n----- stdout -----\n%s\n\n----- stderr -----\n%s'
                % (self.definition.get('shell'), stdout.rstrip(), stderr.rstrip()))
        except Exception as e:
            self.read_flo = io.StringIO(
                '# %s\n\n----- stdout -----\n%s\n\n----- stderr -----\n%s'
                '\n\n----- exception -----\n%s'
                % (self.definition, stdout.rstrip(), stderr.rstrip(), e))


class CommandEmitterJob(Job):
    def __init__(self, definition):
        super(CommandEmitterJob, self).__init__(definition)
        self.commands = None

    def verb(self):
        return 'shell_emitter'

    def execute(self):
        stdout = ''
        stderr = ''

        try:
            stdout, stderr = processutils.execute(
                self.definition.get('shell_emitter'), shell=True)
            self.commands = stdout.rstrip()
        except Exception as e:
            jobid = random.randint(1, 32000)
            self.read_flo = io.StringIO(
                '# %s\n\n----- stdout -----\n%s\n\n----- stderr -----\n%s'
                '\n\n----- exception -----\n%s'
                % (self.definition, stdout.rstrip(), stderr.rstrip(), e))
            self.destination = '_errors/%05d' % jobid
            self.commands = ''

    def items(self):
        if self.commands:
            parsed_commands = yaml.load(self.commands, Loader=yaml.SafeLoader)
            for cmd in parsed_commands.get('commands'):
                yield(cmd)


JOBS = [FileJob, DirectoryJob, CommandJob, CommandEmitterJob]


@click.group()
@click.option('--verbose/--no-verbose', default=False)
@click.pass_context
def cli(ctx, verbose=None):
    if verbose:
        LOG.setLevel(logging.DEBUG)


@click.command()
@click.option('--target', help='The name of the target configuration to use')
@click.option('--output', help='The path and file to write the output to')
@click.pass_context
def gather(ctx, target=None, output=None):
    if not target:
        print('Please specify a target to collect with --target.')
        sys.exit(1)
    if not output:
        print('Please specify an output location with --output.')
        sys.exit(1)

    zipped = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)

    # Collect our commands from the target file or stdin
    cmds = ''
    if target:
        with open(target) as f:
            cmds = f.read()
    else:
        cmds = sys.stdin.read()

    # Parse commands
    parsed_commands = yaml.load(cmds, Loader=yaml.SafeLoader)

    # Read and execute commands
    queued = parsed_commands.get('commands')
    while queued:
        c = queued.pop()

        job = None
        for j in JOBS:
            candidate_job = j(c)
            if candidate_job.verb() in c:
                job = candidate_job
                break
            candidate_job.cleanup()

        if not job:
            raise UnsupportedJobException(c)

        job.execute()
        if job.read_flo:
            zipped.writestr(job.destination, job.read_flo.read())
        for i in job.items():
            queued.append(i)

        job.cleanup()

    zipped.close()


cli.add_command(gather)
