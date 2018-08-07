from txconnpool.pool import PooledClientFactory, Pool

from divvy.twisted_client import DivvyProtocol


class PooledDivvyProtocol(DivvyProtocol):
    factory = None

    def connectionMade(self):
        """
        Notify our factory that we're ready to accept connections.
        """
        super(PooledDivvyProtocol, self).connectionMade()

        if self.factory.deferred is not None:
            self.factory.deferred.callback(self)
            self.factory.deferred = None


class DivvyClientFactory(PooledClientFactory):
    protocol = PooledDivvyProtocol


class DivvyPool(Pool):
    clientFactory = DivvyClientFactory

    def checkRateLimit(self, **kwargs):
        return self.performRequest('checkRateLimit', **kwargs)
