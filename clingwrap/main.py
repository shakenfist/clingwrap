import io
import json
import os
import re
import sys
import zipfile

from oslo_concurrency import processutils

# Read simple command blocks from stdin and execute them. Command blocks are JSON with
# one command per line and look like this:
#
# {"type": "file", "source": "/var/log/syslog"}
#
# Possible command fields:
#     'type': one of 'command', 'file', or 'directory'
#     'source': either the soure filename or command to execute
#     'destination': where to place the file in the bucket, optional for files


class Job(object):
    def __init__(self, definition):
        self.definition = definition

        self.type = self.definition['type']
        self.source = self.definition['source']
        self.destination = self.definition.get('destination', self.source)

        self.read_flo = None

    def items(self):
        return []

    def cleanup(self):
        if self.read_flo:
            self.read_flo.close()


class FileJob(Job):
    # {"type": "file", "source": "/var/log/syslog"}
    def __init__(self, definition):
        super(FileJob, self).__init__(definition)
        self.read_flo = open(definition['source'], 'rb')


class DirectoryJob(Job):
    # {"type": "directory", "source": "/var/log/syslog"}, "exclude": "hd[ac-z]"
    def __init__(self, definition):
        super(DirectoryJob, self).__init__(definition)
        if 'exclude' in definition:
            self.exclude = re.compile(definition['exclude'])
        else:
            self.exclude = None

    def items(self, path=None):
        if not path:
            path = self.source

        for ent in os.listdir(path):
            p = os.path.join(path, ent)
            if os.path.isdir(p):
                for result in self.items(p):
                    yield result
            else:
                if self.exclude:
                    if self.exclude.match(ent):
                        continue
                yield '{"type": "file", "source": "%s"}' % p


class CommandJob(Job):
    # {"type": "command", "source": "pip3 list", "destination": "commands/pip3-list"}
    def __init__(self, definition):
        super(CommandJob, self).__init__(definition)
        stdout, stderr = processutils.execute(
            self.definition['source'], shell=True)
        self.read_flo = io.StringIO(
            '# %s\n\n----- stdout -----\n%s\n\n----- stderr -----\n%s'
            % (self.definition['source'], stdout.rstrip(), stderr.rstrip()))


class CommandEmitterJob(Job):
    # {"type": "commandEmitter", "source": "...thing which outputs commands..."}
    def __init__(self, definition):
        super(CommandEmitterJob, self).__init__(definition)
        stdout, _ = processutils.execute(
            self.definition['source'], shell=True)
        self.commands = stdout.rstrip().split('\n')

    def items(self):
        for cmd in self.commands:
            cmd = cmd.rstrip()
            if cmd:
                yield(cmd)


JOBS = {
    'file': FileJob,
    'directory': DirectoryJob,
    'command': CommandJob,
    'commandEmitter': CommandEmitterJob,
}


def cli():
    zipped = zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED)

    # Read and execute commands
    queued = sys.stdin.readlines()
    while queued:
        print('Queued commands: %d' % len(queued))
        item = queued.pop()
        print('>> %s' % item.rstrip())

        c = json.loads(item.rstrip())
        j = JOBS[c['type']](c)

        if j.read_flo:
            zipped.writestr(j.destination, j.read_flo.read())
        for i in j.items():
            queued.append(i)

        j.cleanup()

    zipped.close()
