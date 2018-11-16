import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.defer import maybeDeferred
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.basic import LineReceiver
from twisted.trial import unittest
from twisted.test.proto_helpers import StringTransportWithDisconnection
from twisted.internet.error import ConnectError, ConnectionLost, ConnectionClosed
from twisted.internet.defer import TimeoutError

from divvy import twisted_client
from divvy.protocol import Translator


class DivvyServerProtocol(LineReceiver):
    """Mock a divvy server for test purposes
    """
    delimiter = "\n"
    
    def connectionMade(self):
        if not self.factory.running:
            self.transport.abortConnection()
        
    def clientConnectionLost(self, _):
        self.factory.clients.remove(self.transport)
        
    def lineReceived(self, line):
        if not self.factory.running:
            self.transport.abortConnection()
            return
        self.sendLine(self.factory.result.strip())

    
class DivvyServerFactory(Factory):
    """Manage connections and clients
    """
    protocol = DivvyServerProtocol
    result = b'OK true 575 60\n'
    clients = set()
    running = True
    
    def shutdown(self):
        self.running = False
        for client in self.clients:
            client.loseConnection()

    def crash(self):
        self.running = False
        for client in self.clients:
            client.abortConnection()

    def resume(self):
        self.running = True


class RemoteDivvyProtocolTest(unittest.TestCase):
        
    def setUp(self):
        self.host="127.0.0.1"
        self.factory = DivvyServerFactory()
        self.listeningPort = reactor.listenTCP(0, self.factory, interface=self.host)
        self.addCleanup(self.listeningPort.stopListening)
        self.port = self.listeningPort.getHost().port
        self.translator = Translator()
        self.client = None

    def tearDown(self):
        if self.client:
            self.client.disconnect()
        self.listeningPort.stopListening
        reactor.disconnectAll()
        for p in reactor.getDelayedCalls():
            p.cancel()
            
    def _getClientConnection(self):
        """Get a new client connection
        """
        self.client = twisted_client.DivvyClient(self.host, self.port, timeout=1.0)
        return self.client.connection.deferred

    def _makeRequest(self, d):
        """Make a request and check if the response is correct
        """
        response = self.translator.parse_reply(self.factory.result)
        d.addCallback(lambda _: self.client.check_rate_limit())
        d.addCallback(self.assertEqual, response)
        return d

    def _pause(self, _, duration):
        return task.deferLater(reactor, duration, lambda: None)
    
    def testConnectionMade(self):
        """Validates the setup only
        """
        d = self._getClientConnection()
        d.addCallback(lambda _: self.client.disconnect())
        return d

    def testSimpleRequest(self):
        """Connect, send request and check response
        """
        d = self._getClientConnection()
        self._makeRequest(d)
        return d
    
    def testMultipleRequests(self):
        """Send multiple request as fast as possible and check results
        """
        response = self.translator.parse_reply(self.factory.result)
        d = self._getClientConnection()
        for _ in range(1000):
            d.addCallback(lambda _: self.client.check_rate_limit())
            d.addCallback(self.assertEqual, response)
        return d
    
    def testConnectionLost(self):
        """Check immediate failure if connection is down
        """
        d = self._getClientConnection()
        d.addCallback(lambda _: self.factory.crash())
        d.addCallback(lambda _: self.client.check_rate_limit())
        d.addTimeout(0.01, reactor)
        self.assertFailure(d, ConnectionClosed)
        return d
            
    def testReconnectionOnConnectionLost(self):
        """Verify if reconnect and get a sucessful reponse after resuming 
        a connection lost
        """
        d = self.testConnectionLost()
        d.addCallback(lambda _: self.factory.resume())
        d.addCallback(lambda _: self.client.connection.deferred)
        self._makeRequest(d)
        return d
    
    def testServerShutdown(self):
        """Check immediate failure on server shutdown
        """
        d = self.testSimpleRequest()
        d.addCallback(lambda _: self.factory.shutdown())
        d.addCallback(lambda _: self.listeningPort.stopListening())
        d.addCallback(lambda _: self.client.check_rate_limit())
        d.addTimeout(0.01, reactor)
        return self.assertFailure(d, ConnectionClosed)
            
    def testReconnectionOnServerResume(self):
        """Check reconnection and sucessful request after resuming server
        """
        def resume(_):
            self.listeningPort = reactor.listenTCP(self.port, self.factory, interface=self.host)
            self.factory.resume()
            return self.client.connection.deferred
        d = self.testServerShutdown()
        d.addCallback(resume)
        self._makeRequest(d)
        return d
            
