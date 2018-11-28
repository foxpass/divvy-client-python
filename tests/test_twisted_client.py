from twisted.trial import unittest
from twisted.test import proto_helpers
from twisted.internet import task
from twisted.internet.defer import TimeoutError

from divvy import twisted_client
from divvy.protocol import Translator


class DivvyProtocolTest(unittest.TestCase):
   
    def setUp(self):
        self.savedReactor = twisted_client.reactor
        self.clock = task.Clock()
        twisted_client.reactor = self.clock
        self.transport = proto_helpers.StringTransport()
        self.factory = twisted_client.DivvyFactory(timeout=30)
        self.protocol = self.factory.buildProtocol(('127.0.0.1', 0))
        self.protocol.makeConnection(self.transport)
        self.translator = Translator()

    def tearDown(self):
        twisted_client.reactor = self.savedReactor
        
    def test_checkRateLimit(self):
        # tx
        d = self.factory.checkRateLimit({})
        txData = self.transport.value()
        self.assertEqual(txData, b'HIT\n')
        
        # rx
        self.transport.clear()
        rxData = b'OK true 575 60\n'
        response = self.translator.parse_reply(rxData)
        d.addCallback(self.assertEqual, response)
        self.protocol.dataReceived(rxData)
        return d

    def test_timeout(self):
        d = self.factory.checkRateLimit({})
        self.clock.advance(self.factory.timeout)
        return self.assertFailure(d, TimeoutError)

    
