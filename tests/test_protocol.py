from collections import namedtuple
from unittest import TestCase

from divvy.exceptions import InputError, ParseError, ServerError
from divvy.protocol import Response, Translator


class BuildTest(TestCase):
    def setUp(self):
        self.t = Translator()

    def test_no_arguments(self):
        output = self.t.build_hit()
        self.assertEqual(b'HIT\n', output)

    def test_single_argument(self):
        output = self.t.build_hit(method="GET")
        self.assertEqual(b'HIT "method"="GET"\n', output)

    def test_multiple_arguments(self):
        output = self.t.build_hit(path="/cookies", method="GET")
        self.assertEqual(b'HIT "method"="GET" "path"="/cookies"\n', output)

    def test_coerced_arguments(self):
        output = self.t.build_hit(b=True, f=3.1416, i=-65535)
        self.assertEqual(b'HIT "b"="True" "f"="3.1416" "i"="-65535"\n', output)

    def test_special_keys(self):
        kwargs = {'Arg+1': 1, 'arg-*': '*'}
        output = self.t.build_hit(**kwargs)
        self.assertEqual(b'HIT "Arg+1"="1" "arg-*"="*"\n', output)

    def test_encoding(self):
        output = self.t.build_hit(happy_face=u'\U0001f604')
        self.assertEqual(b'HIT "happy_face"="\xf0\x9f\x98\x84"\n', output)

    def test_invalid_key(self):
        kwargs = {'Arg 3': 3}
        self.assertRaises(InputError, self.t.build_hit, **kwargs)

    def test_invalid_value(self):
        self.assertRaises(InputError, self.t.build_hit, method="GET PUT")


class ParseTest(TestCase):
    def setUp(self):
        self.t = Translator()

    def testSuccess(self):
        r = self.t.parse_reply(b'OK true 575 60\n')
        self.assertIsInstance(r, Response)
        self.assertTrue(r.is_allowed)
        self.assertEqual(575, r.current_credit)
        self.assertEqual(60, r.next_reset_seconds)

    def testFailure(self):
        r = self.t.parse_reply(b'OK false 0 13\n')
        self.assertIsInstance(r, Response)
        self.assertFalse(r.is_allowed)
        self.assertEqual(0, r.current_credit)
        self.assertEqual(13, r.next_reset_seconds)

    def testServerError(self):
        try:
            reply = b'ERR unknown-command "Unrecognized command: GETBACK"\n'
            r = self.t.parse_reply(reply)
            self.fail("parse_reply should have thrown a ServerError")
        except ServerError as e:
            self.assertEqual("unknown-command", e.error_code)
            self.assertEqual("Unrecognized command: GETBACK", e.message)

    def testInvalidMessage(self):
        self.assertRaises(ParseError, self.t.parse_reply, b'foo true 550 50\n')
        self.assertRaises(ParseError, self.t.parse_reply, b'OK foo 550 50\n')
        self.assertRaises(ParseError, self.t.parse_reply, b'OK true foo 50\n')
        self.assertRaises(ParseError, self.t.parse_reply, b'OK true 550 foo\n')
