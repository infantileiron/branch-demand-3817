import os
import redis

QUEUE='demand:runs'


def connect():
    return redis.Redis.from_url(os.environ['REDIS_URL'])


def enqueue(run_id):
    connect().rpush(QUEUE,int(run_id))


def take(timeout=3):
    item=connect().blpop(QUEUE,timeout=timeout)
    if not item:return None
    return int(item[1])
