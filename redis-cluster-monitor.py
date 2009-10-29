#!/usr/bin/env python

# redis-cluster-monitor.py
#
# - A simple monitoring script for a cluster of Redis instances.
#   The goal is to always have one master and 0 or more slaves, 
#   even when the master goes offline for some reason.
# - To use, setup your cluster with a single master and 0 or
#   more slaves, then run this script on a host outside the cluster.
# - The script will auto-determine the master/slave state of each Redis instance
#   by connecting to each at startup.
#
# Brian Hammond <brian at fictorial dot com>
# Created Oct. 2009
#
# License: MIT
# Warranty: None

import logging

## Configuration:

CONNECTION_TIMEOUT = 5
DEFAULT_CHECK_DELAY = 5
LOG_FILENAME = '/tmp/redis-cluster-monitor.out'
LOGGER_NAME = 'redis-cluster-monitor'
LOG_LEVEL = logging.INFO

## End of configuration.

import redis, socket, re, sys, random, time, logging.handlers

logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(LOG_LEVEL)
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=(1 << 32), backupCount=5)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

DEFAULT_PORT = 6379   # Redis' default port.

class RedisInstanceException(Exception):
  pass
  
class RedisClusterException(Exception):
  pass

class RedisInstance(object):
  ROLE_MASTER, ROLE_SLAVE = range(2)
  STATUS_UP, STATUS_DOWN = range(2)

  def __init__(self, host, port=DEFAULT_PORT, role=None):
    self.host = host
    self.port = int(port)
    self.role = role
    self.status = None
    
  def _connect(self):
    try:
      logger.debug("connecting to redis instance %s ...", self)
      r = redis.Redis(self.host, self.port, CONNECTION_TIMEOUT)
      r.connect()
      logger.debug("... %s is up.", self)
      self.status = RedisInstance.STATUS_UP
      return r
    except redis.ConnectionError:
      logger.warning("... %s is down!", self)
      self.status = RedisInstance.STATUS_DOWN
      raise
      
  def fetch_state_from_redis_instance(self):
    try:
      r = self._connect()
      role = r.info()['role']
      logger.info('%s is a %s.' % (self, role))
      if role == 'master':
        self.role = RedisInstance.ROLE_MASTER
      elif role == 'slave':
        self.role = RedisInstance.ROLE_SLAVE
      else:
        raise RedisInstanceException('unknown role in redis instance %s' % self)
    except redis.ConnectionError:
      raise RedisInstanceException('cannot fetch state from redis instance %s - redis and/or host is down.' % self)

  def ping(self):
    try:
      self._connect()
    except redis.ConnectionError:
      pass
    return self.status
    
  def is_master(self):
    return self.role == RedisInstance.ROLE_MASTER
    
  def is_slave(self):
    return self.role == RedisInstance.ROLE_SLAVE
    
  def is_up(self):
    return self.status == RedisInstance.STATUS_UP

  def is_down(self):
    return self.status == RedisInstance.STATUS_DOWN
    
  def set_as_master(self):
    connect_error = "cannot make %s the master as %s is not up!" % (self, self)
    if not self.is_up():
      raise RedisInstanceException(connect_error)
    try:
      self._commit_master_slave_status()
      self.role = RedisInstance.ROLE_MASTER
    except redis.ConnectionError:
      raise RedisInstanceException(connect_error)

  def make_slave_of(self, master):
    connect_error = "cannot make %s a slave of %s as %s is not up!" % (self, str(master), self)
    if not self.is_up():
      raise RedisInstanceException(connect_error)
    try:
      self._commit_master_slave_status(master)
      self.role = RedisInstance.ROLE_SLAVE
    except redis.ConnectionError:
      raise RedisInstanceException(connect_error)
      
  def _commit_master_slave_status(self, master=None):
    r = self._connect()
    # NB redis.py doesn't know about SLAVEOF (yet).
    if master:
      logger.info("commiting SLAVE status for %s as slave of %s" % (self, str(master)))
      r._write('SLAVEOF %s %d\r\n' % (master.host, master.port))
    else:
      logger.info("commiting MASTER status for %s" % self)
      r._write('SLAVEOF NO ONE\r\n')  # I am Spartacus!
    response = r.get_response()
    if response != "OK":
      raise RedisInstanceException("unexpected response '%s' from Redis instance!" % response)
    
  def __str__(self):
    return "%s:%d" % (self.host, self.port)
    
class RedisCluster(object):
  def __init__(self, name="Default Cluster"):
    self.name = name
    self.instances = dict()

  def add(self, instance):
    if len(self.instances_by_role(RedisInstance.ROLE_MASTER)) > 0 and instance.role == RedisInstance.ROLE_MASTER:
      raise Exception("only one master is allowed")
    self.instances[instance] = instance
    
  def remove(self, instance):
    del self.instances[instance]
    
  def instances_by_role(self, role):
    return [instance for instance in self.instances.values() if instance.role == role]
    
  def get_master(self):
    self._validate()
    return self.instances_by_role(RedisInstance.ROLE_MASTER)[0]
    
  def get_slaves(self):
    n_slaves = self._validate()
    if n_slaves == 0:
      return []
    return self.instances_by_role(RedisInstance.ROLE_SLAVE)
      
  def _validate(self):
    n_masters = len(self.instances_by_role(RedisInstance.ROLE_MASTER))
    if n_masters == 0:
      raise RedisClusterException("no master defined")
    if n_masters > 1:
      raise RedisClusterException("more than one master defined")
    n_slaves = len(self.instances_by_role(RedisInstance.ROLE_SLAVE))
    if n_slaves == 0:
      logger.warning("no slaves defined in cluster; are you sure this is correct?")
    return n_slaves
    
class RedisClusterMonitor(object):
  def __init__(self, cluster):
    self.cluster = cluster
    
  def check(self):
    "Run one iteration of checking all hosts and reconfigure them as needed."
    
    self.cluster._validate()
    
    logging.info("checking cluster...")
        
    for instance in self.cluster.instances:
      instance.ping()
        
    # is the master offline?
    
    current_master = self.cluster.get_master()
    if current_master.is_down():
      new_master = self._pick_new_master()
      logger.info("master is offline; picked new master to be %s" % str(new_master))
      self._promote_to_master(new_master)
    
    logging.info("... clustering checking complete.")
    
  def _pick_new_master(self):
    slaves = [slave for slave in self.cluster.get_slaves() if slave.is_up()]
    logger.info("picking new master from slaves: %s" % ', '.join(map(str, slaves)))
    return random.Random().choice(slaves)
    
  def _promote_to_master(self, new_master):
    """
    Before we make any existing instances slaves, set the new master.
    Demote the current master to slave.
    Reconfigure the other slaves to be slaves of the new master.
    """
    
    current_master = self.cluster.get_master()
    current_master.role = None
    
    new_master.set_as_master()
        
    if current_master.is_up():
      logger.info("making current master %s a slave of %s" % (str(current_master), str(new_master)))
      current_master.make_slave_of(new_master)
      
    for existing_slave in self.cluster.get_slaves():
      logger.info("making existing slave %s a slave of %s" % (str(existing_slave), str(new_master)))
      existing_slave.make_slave_of(new_master)
      
  def check_forevermore(self, delay_between_checks=DEFAULT_CHECK_DELAY):
    logger.info("entering checking loop... delay=%ds" % delay_between_checks)
    while True:
      try:
        self.check()
        logger.info('%d slave(s) with %s as master.' % \
          (len(self.cluster.get_slaves()), self.cluster.get_master()))
      except RedisInstanceException, e:
        logger.error("caught exception %s", e)
      time.sleep(delay_between_checks)

def autoconfigure_cluster_from(host_specs):
  cluster = RedisCluster()
  for spec in host_specs:
    ip, port = spec.split(":")
    if not port:
      port = DEFAULT_PORT
    instance = RedisInstance(ip, port)
    logger.debug("about to fetch state for instance %s ..." % instance)
    instance.fetch_state_from_redis_instance()
    cluster.add(instance)
  return cluster
  
if __name__ == '__main__':
  host_specs = sys.argv[1:]
  if len(host_specs) == 0:
    print "USAGE: %s ip1:port ip2:port ... ipN:port" % sys.argv[0]
    sys.exit(1)
      
  for host_spec in host_specs:
    try: 
      ip, port = host_spec.split(":")
      socket.inet_aton(ip)
    except socket.error:
      print "invalid ip in %s" % host_spec
      sys.exit()

  cluster = autoconfigure_cluster_from(host_specs)
  monitor = RedisClusterMonitor(cluster)
  monitor.check_forevermore()
