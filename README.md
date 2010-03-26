# redis-cluster-monitor

---

UPDATE: please note that this is just a toy. A proper "redis-cluster" is on the
official Redis roadmap.  There's also the [twine
project](http://github.com/alexgenaud/twine) to consider.

---

Redis supports master-slave (1:N) replication but does not support *automatic*
failover. That is, if the master "goes down" for any reason, your sysadmin
(read: you) has to reconfigure one of the Redis slaves to be the new master.

One could use monit or God or whatever alongside redis-cli to check if a host is
up, then send the other hosts a SLAVEOF command to reconfigure the cluster
around a new master.

I created a Python script that does this instead. It only took an hour to do so
no big loss. OK, I didn't think of using redis-cli initially :)

Perhaps this project could at least be a part of the infrastructure (perhaps in
concept only) for the forthcoming "redis-cluster" project.

The [original mailing list thread](http://groups.google.com/group/redis-db/browse_thread/thread/497ee813c9960a50)
discusses the origins of this project a bit.

## Requirements

You must have already installed the Redis Python client.

A cluster of Redis instances :)

## Usage

1. Configure your redis cluster with one master and 0 or more slaves.
1. Run on a host outside this cluster:

        python redis-cluster-monitor.py ip1:port ip2:port ... ipN:port

## Example

Here's a sample cluster running all on the same host for simplicity's sake.

    $ egrep '^(port|slaveof) ' *.conf
    redis-master.conf:port 6379
    redis-slave1.conf:port 6380
    redis-slave1.conf:slaveof 127.0.0.1 6379
    redis-slave2.conf:port 6380
    redis-slave2.conf:slaveof 127.0.0.1 6379

Fire up the master:

    $ ./redis-server redis-master.conf 
    29 Oct 20:45:27 - Server started, Redis version 1.050
    29 Oct 20:45:27 - DB loaded from disk
    29 Oct 20:45:27 - The server is now ready to accept connections on port 6379

Fire up the first slave:

    $ ./redis-server redis-slave1.conf 
    29 Oct 20:45:47 - Server started, Redis version 1.050
    29 Oct 20:45:47 - DB loaded from disk
    29 Oct 20:45:47 - The server is now ready to accept connections on port 6380
    29 Oct 20:45:48 . DB 0: 2 keys (0 volatile) in 4 slots HT.
    29 Oct 20:45:48 . 0 clients connected (0 slaves), 3280 bytes in use, 0 shared objects
    29 Oct 20:45:48 - Connecting to MASTER...
    29 Oct 20:45:49 - Receiving 35 bytes data dump from MASTER
    29 Oct 20:45:49 - MASTER <-> SLAVE sync succeeded

Fire up the second slave:

    $ ./redis-server redis-slave2.conf 
    29 Oct 20:46:15 - Server started, Redis version 1.050
    29 Oct 20:46:15 - DB loaded from disk
    29 Oct 20:46:15 - The server is now ready to accept connections on port 6381
    29 Oct 20:46:16 . DB 0: 2 keys (0 volatile) in 4 slots HT.
    29 Oct 20:46:16 . 0 clients connected (0 slaves), 3280 bytes in use, 0 shared objects
    29 Oct 20:46:16 - Connecting to MASTER...
    29 Oct 20:46:16 - Receiving 35 bytes data dump from MASTER
    29 Oct 20:46:16 - MASTER <-> SLAVE sync succeeded

Fire up the monitor which will auto-determine the role of each host in the cluster.
Watch as (by default) every 5 seconds it checks on the cluster:

    $ python redis-cluster-watcher.py 127.0.0.1:6379 127.0.0.1:6380 127.0.0.1:6381
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    
Kill the master on port 6379.  Watch the monitor's output:

    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    INFO:redis-cluster-monitor:2 slave(s) with 127.0.0.1:6379 as master.
    WARNING:redis-cluster-monitor:... 127.0.0.1:6379 is down!
    INFO:redis-cluster-monitor:picking new master from slaves: 127.0.0.1:6380, 127.0.0.1:6381
    INFO:redis-cluster-monitor:master is offline; picked new master to be 127.0.0.1:6381
    INFO:redis-cluster-monitor:commiting MASTER status for 127.0.0.1:6381
    INFO:redis-cluster-monitor:making existing slave 127.0.0.1:6380 a slave of 127.0.0.1:6381
    INFO:redis-cluster-monitor:commiting SLAVE status for 127.0.0.1:6380 as slave of 127.0.0.1:6381
    INFO:redis-cluster-monitor:1 slave(s) with 127.0.0.1:6381 as master.
    WARNING:redis-cluster-monitor:... 127.0.0.1:6379 is down!
    INFO:redis-cluster-monitor:1 slave(s) with 127.0.0.1:6381 as master.
    ...
    WARNING:redis-cluster-monitor:... 127.0.0.1:6379 is down!
    INFO:redis-cluster-monitor:1 slave(s) with 127.0.0.1:6381 as master.

## Issues?

Please let me know if you find any issues. 

There's likely to be some corner cases as I just started this project.

## Hang on a second!

Right, you might be wondering how this is useful since you still have a single
write-master and N read-slaves in a cluster but most if not all Redis client
libraries require a single host:port to connect to. If the master goes down in
the cluster another will be brought up but your client will have no idea that
this happened.

Exactly.

So, this isn't useful *yet* in practice. You need a smarter client library that
is "cluster-aware". I'll be patching the Python Redis client to this end soon.
The long term goal is a redis-cluster project where all these smarts will live.

## License

MIT

## Copyright

Copyright (C) 2009 Fictorial LLC.
