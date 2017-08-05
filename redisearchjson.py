from redisearch import Client as RSClient
from redisearch import NumericField, TextField
from rejson import Client as RJClient
from rejson import Path
from rejson.client import BasePipeline
from redis import ConnectionPool

class Client(RJClient, RSClient):

    def __init__(self, url, idx, *args, **kwargs):
        pool = ConnectionPool(RJClient).from_url(url)
        RJClient.__init__(self, connection_pool=pool)
        RSClient.__init__(self, idx, conn=self)

    def pipeline(self, transaction=True, shard_hint=None):
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.

        Overridden in order to provide the right client through the pipeline.
        """
        p = Pipeline(
            connection_pool=self.connection_pool,
            response_callbacks=self.response_callbacks,
            transaction=transaction,
            shard_hint=shard_hint)
        return p


class Pipeline(BasePipeline, Client):
    "Pipeline for ReJSONClient"
