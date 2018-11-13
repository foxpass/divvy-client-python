from twisted.trial import unittest
from twisted.test import proto_helpers
from twisted.internet import task
from twisted.internet.defer import TimeoutError

from divvy.protocol import Translator
from divvy.twisted_client import DivvyProtocol, DivvyFactory
from divvy import twisted_client


class DivvyProtocolTest(unittest.TestCase):
   
    def setUp(self):
        self.clock = task.Clock()
        twisted_client.reactor = self.clock
        self.transport = proto_helpers.StringTransport()
        self.factory = DivvyFactory(timeout=30)
        self.protocol = self.factory.buildProtocol(('127.0.0.1', 0))
        self.protocol.makeConnection(self.transport)
        self.translator = Translator()
        
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

    
