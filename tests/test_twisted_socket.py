import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.defer import maybeDeferred
from twisted.internet.protocol import Factory, ClientCreator
from twisted.protocols.basic import LineReceiver
from twisted.trial import unittest
from twisted.test.proto_helpers import StringTransportWithDisconnection
from twisted.internet.error import ConnectError, ConnectionLost
from twisted.internet.defer import TimeoutError

from divvy import twisted_client
from divvy.protocol import Translator

log.startLogging(sys.stdout)


class DivvyServerProtocol(LineReceiver):
    delimiter = "\n"
    
    def connectionMade(self):
        self.factory.clients.add(self.transport)
        
    def clientConnectionLost(self, _):
        self.factory.clients.remove(self.transport)
        
    def lineReceived(self, line):
        self.sendLine(self.factory.result.strip())

    
class DivvyServerFactory(Factory):
    protocol = DivvyServerProtocol
    result = b'OK true 575 60\n'
    clients = set()
    
    def shutdown(self):
        for client in set(self.clients):
            client.loseConnection()

    def crash(self):
        for client in set(self.clients):
            client.abortConnection()


class RemoteDivvyProtocolTest(unittest.TestCase):
    def setUp(self):
        self.factory = DivvyServerFactory()
        self.listeningPort = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        addr = self.listeningPort.getHost()
        self.port = addr.port
        self.host = addr.host
        self.client = twisted_client.DivvyClient(self.host, self.port, timeout=1)
        self.translator = Translator()
        
    def tearDown(self):
        self.client.close()
        #self.client.connection.stopTrying()
        #if self.client.connection.protocol.transport:
        #    self.client.connection.protocol.transport.loseConnection()
        return self.listeningPort.stopListening()

    def testSimpleSuccesfullRequest(self):
        response = self.translator.parse_reply(self.factory.result)
        d = self.client.check_rate_limit()
        d.addCallback(self.assertEqual, response)
        return d
    
    def testServerCrash(self):
        d = self.testSimpleSuccesfullRequest()
        d.addCallback(lambda _: self.factory.crash())
        d.addCallback(lambda _: self.client.check_rate_limit())
        self.assertFailure(d, ConnectionLost)
        return d
            
    def testCrashRecovery(self):
        d = self.testServerCrash()
        d.addErrback(lambda _: task.deferLater(reactor, 1, lambda: None))
        d.addCallback(lambda _: self.testSimpleSuccesfullRequest())
        d.addErrback(lambda _: task.deferLater(reactor, 4, lambda: None))
        d.addCallback(lambda _: self.testSimpleSuccesfullRequest())
        return d
            
    def testServerShutdown(self):
        d = self.testSimpleSuccesfullRequest()
        d.addCallback(lambda _: self.factory.shutdown())
        d.addCallback(lambda _: self.listeningPort.stopListening())
        d.addCallback(lambda _: self.client.check_rate_limit())
        return self.assertFailure(d, ConnectionLost)
            
    def testServerResume(self):
        def restartListeningCb(_):
            self.listeningPort = reactor.listenTCP(self.port, self.factory, interface=self.host)
            
        d = self.testServerShutdown()
        d.addCallback(restartListeningCb)
        d.addErrback(lambda _: task.deferLater(reactor, 1, lambda: None))
        d.addCallback(lambda _: self.testSimpleSuccesfullRequest())
        d.addErrback(lambda _: task.deferLater(reactor, 4, lambda: None))
        d.addCallback(lambda _: self.testSimpleSuccesfullRequest())
        return d
            
