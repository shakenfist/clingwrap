Clingwrap
=========

Clingwrap is a simple debugging tool which collects information about the state of
a system and stores that information in a zip file for later analysis. It was
originally implemented for the Shaken Fist (https://shakenfist.com) project, but is
more generally useful than that.

Clingwrap takes a configuration file (see examples/shakenfist-ci-failure.cwd for an
example), and processes the list of commands in that file to produce the zip file
of debugging output. The commands are specified in a simple YAML format, where
a configuration file looks like this:

```
--
commands:
  - name: Kernel version and architecture
    destination: _commands/uname
    shell: uname -a

  - name: Installed system OS packages and versions
    destination: _commands/dpkg
    shell: dpkg -l
```

Possible commands are:

*file commands*: which record the contents of a file. For example:

```
  - name: syslog
    destination: var/log/syslog
    file: /var/log/syslog
```

*directory commands*: which record all files in a given directory hierarchy, with a
possible simple exclusion regexp. For example:

```
  - name: Shaken Fist instances
    destination: /srv/shakenfist/instances
    directory: /srv/shakenfist/instances
    exclude: "hd[ac-z]"
```

*shell commands*: which take a command line or script and execute them in a shell. A
valid configuration is:

```
  - name: Kernel version and architecture
    destination: _commands/uname
    shell: uname -a
```

*shell_emitter commands*: which run a shell script which emits further commands to
execute. This is useful for finding objects and then storing information about them.
A valid example is:

```
  - name: Network namespaces
    shell_emitter: |
      for item in `find /var/run/netns -type f | sed 's/.*\///'`
      do
        echo "commands:
      - name: Network interfaces (namespace $item)
        destination: _commands/netns-$item/ip-link
        shell: ip netns exec $item ip link

      - name: Network addresses (namespace $item)
        destination: _commands/netns-$item/ip-link
        shell: ip netns exec $item ip addr

      - name: Network routes (namespace $item)
        destination: _commands/netns-$item/ip-link
        shell: ip netns exec $item ip route
      "
      done
```