from unittest import TestCase
from twisted.trial import unittest
from twisted.test import proto_helpers

from divvy.protocol import Translator
from divvy.twisted_client import DivvyProtocol, DivvyFactory


class DivvyProtocolTest(TestCase):
   
    def setUp(self):
        self.transport = proto_helpers.StringTransport()
        self.factory = DivvyFactory(None)
        self.protocol = self.factory.buildProtocol(('127.0.0.1', 0))
        self.protocol.makeConnection(self.transport)
        self.translator = Translator()

    def test_no_arguments(self):
        d = self.factory.checkRateLimit({})
        txData = self.transport.value()
        self.assertEqual(txData, b'HIT\n')
        self.transport.clear()
        rxData = b'OK true 575 60\n'
        response = self.translator.parse_reply(rxData)
        d.addCallback(self.assertEqual, response)
        self.protocol.dataReceived(rxData)
        return d
