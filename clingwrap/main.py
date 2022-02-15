import click
import io
import json
import logging
import os
import re
import sys
import yaml
import zipfile

from oslo_concurrency import processutils

logging.basicConfig(level=logging.INFO)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

# Read simple command blocks from stdin and execute them. Command blocks are JSON with
# one command per line and look like this:
#
# {"type": "file", "source": "/var/log/syslog"}
#
# Possible command fields:
#     'type': one of 'command', 'file', or 'directory'
#     'source': either the soure filename or command to execute
#     'destination': where to place the file in the bucket, optional for files


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
    # {"type": "file", "source": "/var/log/syslog"}
    def __init__(self, definition):
        super(FileJob, self).__init__(definition)

    def verb(self):
        return 'file'

    def execute(self):
        if os.path.exists(self.definition.get('file')):
            self.read_flo = open(self.definition.get('file'), 'rb')


class DirectoryJob(Job):
    # {"type": "directory", "source": "/var/log/syslog"}, "exclude": "hd[ac-z]"
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
                    'destination': p
                }


class CommandJob(Job):
    # {"type": "command", "source": "pip3 list", "destination": "commands/pip3-list"}
    def __init__(self, definition):
        super(CommandJob, self).__init__(definition)

    def verb(self):
        return 'shell'

    def execute(self):
        stdout, stderr = processutils.execute(
            self.definition.get('shell'), shell=True)
        self.read_flo = io.StringIO(
            '# %s\n\n----- stdout -----\n%s\n\n----- stderr -----\n%s'
            % (self.definition.get('shell'), stdout.rstrip(), stderr.rstrip()))


class CommandEmitterJob(Job):
    # {"type": "commandEmitter", "source": "...thing which outputs commands..."}
    def __init__(self, definition):
        super(CommandEmitterJob, self).__init__(definition)

    def verb(self):
        return 'shell_emitter'

    def execute(self):
        stdout, _ = processutils.execute(
            self.definition.get('shell_emitter'), shell=True)
        self.commands = stdout.rstrip().split('\n')

    def items(self):
        for cmd in self.commands:
            cmd = cmd.rstrip()
            if cmd:
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
    print(parsed_commands)

    # Read and execute commands
    queued = parsed_commands.get('commands')
    while queued:
        print('Queued commands: %d' % len(queued))
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
